"""Report reuse must stay fresh, isolated and identical to the detailed calculations."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import json
import os

import pytest
from sqlalchemy import select

from app.modules.identity.auth import Principal, current_principal
from app.modules.reporting import analytics
from app.modules.reporting.cache import ReportCache
from app.persistence.models import Period
from test_analytics import install_reference
from test_api_worker import upload, drain
import test_api_worker

system = test_api_worker.system


def test_cache_coalesces_requests_and_returns_independent_results():
    cache, ready, release, start = ReportCache(), Event(), Event(), Barrier(4)
    builds = []

    def build():
        builds.append(1)
        ready.set()
        assert release.wait(5)
        return {'values': [1, 2]}

    def request():
        start.wait(timeout=5)
        return cache.get_or_compute('same', build)

    with ThreadPoolExecutor(max_workers=4) as pool:
        requests = [pool.submit(request) for _ in range(4)]
        assert ready.wait(5)
        # A slow report never holds the global lock against unrelated reports.
        assert cache.get_or_compute('other', lambda: {'value': 3}) == {'value': 3}
        release.set()
        results = [request.result(timeout=5) for request in requests]
    assert len(builds) == 1
    results[0]['values'].append(99)
    assert results[1] == cache.get_or_compute('same', build) == {'values': [1, 2]}


def test_cache_does_not_keep_failures_or_exceed_its_limits():
    cache = ReportCache(max_entries=2, max_bytes=40)
    calls = []

    def build(key):
        calls.append(key)
        return {'value': key}

    for key in ('a', 'b', 'a', 'c', 'a', 'b'):
        cache.get_or_compute(key, lambda: build(key))
    assert calls == ['a', 'b', 'c', 'b']
    with pytest.raises(ValueError):
        cache.get_or_compute('failed', lambda: int('invalid'))
    assert cache.get_or_compute('failed', lambda: {'value': 1}) == {'value': 1}
    for _ in range(2):
        cache.get_or_compute('huge', lambda: build('x' * 80))
    assert calls.count('x' * 80) == 2


def test_unchanged_reports_are_reused_but_file_changes_and_deletion_are_seen(system, tmp_path, monkeypatch):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    original = analytics.paid_taxes
    calls = []

    def calculate(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(analytics, 'paid_taxes', calculate)
    params = {'source': 'reference', 'year': 2026}
    first = client.get('/api/v1/reports/analytics', params=params).json()
    second = client.get('/api/v1/reports/analytics', params=params).json()
    assert first == second
    assert len(calls) == 1
    stat = settings.analytics_reference_file.stat()
    data['tables']['551'][0]['valor_dolares'] = '1.1'
    # Replacement with identical size/mtime must still invalidate the JSON/report caches.
    replacement = settings.analytics_reference_file.with_suffix('.new')
    replacement.write_text(json.dumps(data), encoding='utf-8')
    os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    replacement.replace(settings.analytics_reference_file)
    assert settings.analytics_reference_file.stat().st_size == stat.st_size
    changed = client.get('/api/v1/reports/analytics', params=params).json()
    assert changed['totals']['tradeUsd'] == 1.3
    assert changed['snapshotId'] != first['snapshotId']
    assert len(calls) == 2
    settings.analytics_reference_file.unlink()
    assert client.get('/api/v1/reports/analytics', params=params).status_code == 404


def test_cache_keys_include_currency_range_and_filters(system, tmp_path):
    _, client, settings = system
    install_reference(settings, tmp_path)
    for currency in ('USD', 'MXN'):
        for month, operation in ((1, '1'), (2, '2')):
            params = dict(source='reference', year=2026, currency=currency,
                          startMonth=month, endMonth=month, operation=operation)
            report = client.get('/api/v1/reports/analytics', params=params).json()
            assert report['currency'] == currency
            assert report['coverage']['availableMonths'] == [month]
            assert report['appliedFilters']['operation'] == operation
            assert report['totals']['declarations'] == 1


def test_reuse_never_bypasses_scope_or_permission_checks(system, tmp_path):
    app, client, settings = system
    install_reference(settings, tmp_path)
    for endpoint in ('analytics', 'analytics/months'):
        path = '/api/v1/reports/' + endpoint
        params = {'source': 'reference', 'year': 2026}
        assert client.get(path, params=params).status_code == 200
        app.dependency_overrides[current_principal] = lambda: Principal('other', 'Other', frozenset({'Reader'}), 'other')
        assert client.get(path, params=params).status_code == 404
        app.dependency_overrides[current_principal] = lambda: Principal('user', 'User', frozenset(), 'local')
        assert client.get(path, params=params).status_code == 403
        app.dependency_overrides.clear()
        response = client.get(path, params=params)
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'


def test_published_cache_tracks_worker_publication_version_and_removed_months(system):
    app, client, settings = system
    params = {'year': 2026}
    assert client.get('/api/v1/reports/analytics', params=params).json()['coverage']['availableMonths'] == []
    upload(client)
    drain(app, settings)
    assert client.get('/api/v1/reports/analytics', params=params).json()['totals']['declarations'] == 1
    assert client.get('/api/v1/reports/analytics/months', params=params).json()['monthly'][3]['available']
    with app.state.session_factory() as session:
        april = session.scalar(select(Period).where(Period.month == 4))
        april.version += 1
        april.active_run_id = None
        session.commit()
    assert client.get('/api/v1/reports/analytics', params=params).json()['coverage']['availableMonths'] == []
    assert not client.get('/api/v1/reports/analytics/months', params=params).json()['monthly'][3]['available']


@pytest.mark.parametrize('currency', ['USD', 'MXN'])
@pytest.mark.parametrize('missing_table', [None, '551', '501', '701'])
def test_light_monthly_metrics_match_the_full_report_including_missing_tables(system, tmp_path, currency, missing_table):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    if missing_table:
        data['periods'][0]['tables'].pop(missing_table)
        settings.analytics_reference_file.write_text(json.dumps(data), encoding='utf-8')
    params = {'source': 'reference', 'year': 2026, 'currency': currency}
    light = client.get('/api/v1/reports/analytics/months', params=params).json()
    assert len(light['monthly']) == 12
    assert 'partTaxes' not in light and 'breakdowns' not in light
    for month in (1, 2, 3):
        full = client.get('/api/v1/reports/analytics', params=params | {'startMonth': month, 'endMonth': month}).json()
        selected = light['monthly'][month - 1]
        assert selected['available'] == bool(full['coverage']['availableMonths'])
        assert selected['metrics'] == {key: full['totals'][key] for key in selected['metrics']}


def test_comparison_skips_pn_matching_and_refreshes_when_its_source_changes(system, tmp_path, monkeypatch):
    _, client, settings = system
    data = install_reference(settings, tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail('Monthly comparison must not calculate PN attribution.')

    monkeypatch.setattr(analytics, 'paid_taxes', forbidden)
    params = {'source': 'reference', 'year': 2026}
    first = client.get('/api/v1/reports/analytics/months', params=params).json()
    assert first['monthly'][0]['metrics']['tradeUsd'] == 0.3
    data['tables']['551'][0]['valor_dolares'] = '5.1'
    settings.analytics_reference_file.write_text(json.dumps(data), encoding='utf-8')
    changed = client.get('/api/v1/reports/analytics/months', params=params).json()
    assert changed['monthly'][0]['metrics']['tradeUsd'] == 5.3
