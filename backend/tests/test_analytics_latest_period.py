"""The quick filter uses real source periods, independently of report ranges."""
from datetime import datetime
import json

from app.modules.identity.auth import Principal, current_principal
from app.modules.reporting import analytics
from app.persistence.models import Period, Run
import test_api_worker
from test_api_worker import drain, upload

system = test_api_worker.system


def reference(settings, tmp_path, periods, scope='local'):
    settings.analytics_reference_file = tmp_path / 'latest-period-reference.json'
    settings.analytics_reference_file.write_text(json.dumps({
        'schemaVersion': 1, 'scopeId': scope,
        'periods': [{'year': year, 'month': month} for year, month in periods],
        'tables': {}, 'sources': [],
    }), encoding='utf-8')


def source(client, source_id):
    response = client.get('/api/v1/reports/analytics/options')
    assert response.status_code == 200, response.text
    return next(item for item in response.json()['sources'] if item['id'] == source_id)


def test_reference_latest_period_is_chronological_and_source_specific(system, tmp_path, monkeypatch):
    _, client, settings = system
    reference(settings, tmp_path, [(2026, 2), (2025, 12), (2026, 1), (2024, 9)])
    monkeypatch.setattr(analytics, 'published_dataset', lambda *args: (_ for _ in ()).throw(
        AssertionError('Options must not load business rows')))
    assert source(client, 'reference') == {
        'id': 'reference', 'years': [2026, 2025, 2024], 'latestPeriod': {'year': 2026, 'month': 2},
    }
    assert source(client, 'published') == {'id': 'published', 'years': [], 'latestPeriod': None}
    assert client.get('/api/v1/reports/analytics/options').json()['defaultSource'] == 'reference'


def test_empty_and_foreign_reference_sources_do_not_invent_a_latest_month(system, tmp_path):
    _, client, settings = system
    assert source(client, 'published')['latestPeriod'] is None
    reference(settings, tmp_path, [])
    assert source(client, 'reference') == {'id': 'reference', 'years': [], 'latestPeriod': None}
    reference(settings, tmp_path, [(2028, 12)], scope='other')
    assert client.get('/api/v1/reports/analytics/options').json()['sources'] == [
        {'id': 'published', 'years': [], 'latestPeriod': None},
    ]


def test_latest_published_period_excludes_inactive_pending_annual_and_other_scope_runs(system):
    app, client, _ = system
    with app.state.session_factory() as session:
        cases = [
            (2026, 1, 'local', 'local', 'monthly', 'published', True, datetime(2026, 10, 14)),
            (2026, 9, 'local', 'local', 'monthly', 'published', True, datetime(2026, 10, 1)),
            (2025, 12, 'local', 'local', 'monthly', 'published', True, datetime(2026, 10, 14)),
            (2026, 10, 'local', 'local', 'monthly', 'published', False, datetime(2026, 10, 14)),
            (2026, 11, 'local', 'local', 'monthly', 'pending', True, datetime(2026, 10, 14)),
            (2026, 12, 'local', 'local', 'annual', 'published', True, datetime(2026, 10, 14)),
            (2027, 1, 'local', 'other', 'monthly', 'published', True, datetime(2026, 10, 14)),
            (2027, 2, 'other', 'other', 'monthly', 'published', True, datetime(2026, 10, 14)),
        ]
        for index, (year, month, period_scope, run_scope, kind, publication, active, created) in enumerate(cases):
            run = Run(scope_id=run_scope, year=year, kind=kind, publication_status=publication,
                      input_fingerprint=f'latest-test-{index}', created_at=created)
            session.add(run)
            session.flush()
            session.add(Period(scope_id=period_scope, year=year, month=month,
                               name=f'{year}-{month}', active_run_id=run.id if active else None))
        session.commit()
    assert source(client, 'published') == {
        'id': 'published', 'years': [2026, 2025], 'latestPeriod': {'year': 2026, 'month': 9},
    }
    app.dependency_overrides[current_principal] = lambda: Principal('other', 'Other', frozenset({'Reader'}), 'other')
    assert source(client, 'published') == {
        'id': 'published', 'years': [2027], 'latestPeriod': {'year': 2027, 'month': 2},
    }


def test_options_track_successful_publication_and_year_rollover_without_report_calculation(system):
    app, client, settings = system
    first = upload(client, period='Diciembre_2026')
    assert first.status_code == 202, first.text
    assert source(client, 'published')['latestPeriod'] is None
    drain(app, settings)
    assert source(client, 'published')['latestPeriod'] == {'year': 2026, 'month': 12}
    second = upload(client, period='Enero_2027')
    assert second.status_code == 202, second.text
    assert source(client, 'published')['latestPeriod'] == {'year': 2026, 'month': 12}
    drain(app, settings)
    assert source(client, 'published') == {
        'id': 'published', 'years': [2027, 2026], 'latestPeriod': {'year': 2027, 'month': 1},
    }
