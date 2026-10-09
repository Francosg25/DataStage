from uuid import uuid4

import pytest

from app.modules.identity.auth import Principal, current_principal
import test_api_worker
from test_api_worker import ASC, drain, upload

system = test_api_worker.system


def test_nested_zip_and_reupload_historical_file_replaces_active_month(system):
    app, client, settings = system
    first = upload(client, {'root/subfolder/data_501.asc': ASC})
    assert first.status_code == 202
    drain(app, settings)
    second = upload(client, {'root/subfolder/data_501.asc': ASC.replace('6000001', '6000002') + '\n'})
    drain(app, settings)
    assert second.json()['id'] != first.json()['id']
    third = upload(client, {'root/subfolder/data_501.asc': ASC})
    assert third.status_code == 202
    assert third.json()['id'] not in {first.json()['id'], second.json()['id']}
    drain(app, settings)
    month = client.get('/api/v1/periods').json()[0]
    assert month['activeRunId'] == third.json()['id']
    assert client.get('/api/v1/data/501').json()['total'] == 1


@pytest.mark.parametrize('reason_field', [{}, {'reason': None}, {'reason': 'Legacy client reason'}])
def test_bulk_delete_counts_shared_annual_once_and_is_scope_protected(system, reason_field):
    app, client, settings = system
    upload(client)
    drain(app, settings)
    upload(client, period='Mayo_2026')
    drain(app, settings)
    annual = client.post('/api/v1/annual-runs', json={'anio': 2026, 'rangoNombre': 'Ene-May'}, headers={'Idempotency-Key': str(uuid4())})
    assert annual.status_code == 202
    drain(app, settings)
    ids = [p['id'] for p in client.get('/api/v1/periods').json()]
    preview = client.post('/api/v1/periods/bulk-deletion-preview', json={'periodIds': ids})
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert p['impact']['annualRuns'] == 1
    assert p['impact']['monthlyRuns'] == 2
    assert p['impact']['businessRows'] == 2
    body = {'periodIds': ids, 'expectedToken': p['token'], 'confirmation': p['confirmation'], **reason_field}
    app.dependency_overrides[current_principal] = lambda: Principal('reader', 'Reader', frozenset({'Reader'}), 'local')
    assert client.post('/api/v1/periods/bulk-delete', json=body).status_code == 403
    app.dependency_overrides[current_principal] = lambda: Principal('admin', 'Admin', frozenset({'Admin'}), 'another-scope')
    assert client.post('/api/v1/periods/bulk-delete', json=body).status_code == 404
    app.dependency_overrides.clear()
    assert client.post('/api/v1/periods/bulk-delete', json=body | {'confirmation': 'wrong'}).status_code == 400
    assert len(client.get('/api/v1/periods').json()) == 2
    deleted = client.post('/api/v1/periods/bulk-delete', json=body)
    assert deleted.status_code == 200, deleted.text
    assert client.get('/api/v1/periods').json() == []
    assert client.get('/api/v1/data/501').json()['total'] == 0
    events = client.get('/api/v1/audit').json()['items']
    deleted_events = [e for e in events if e['action'] == 'period.deleted']
    assert len(deleted_events) == 2
    assert all(e['actor'] and e['details']['period'] and e['details']['runIds'] for e in deleted_events)
    assert all(e['details']['reason'] == reason_field.get('reason') for e in deleted_events)


def test_bulk_delete_rejects_changed_or_duplicate_selection(system):
    app, client, settings = system
    upload(client)
    drain(app, settings)
    ids = [p['id'] for p in client.get('/api/v1/periods').json()]
    assert client.post('/api/v1/periods/bulk-deletion-preview', json={'periodIds': ids * 2}).status_code == 400
    p = client.post('/api/v1/periods/bulk-deletion-preview', json={'periodIds': ids}).json()
    upload(client, {'changed_501.asc': ASC + '\n'})
    drain(app, settings)
    response = client.post('/api/v1/periods/bulk-delete', json={'periodIds': ids, 'expectedToken': p['token'], 'confirmation': p['confirmation']})
    assert response.status_code == 409
    assert len(client.get('/api/v1/periods').json()) == 1


def test_single_month_deletion_accepts_no_reason_but_requires_confirmation(system):
    app, client, settings = system
    upload(client)
    drain(app, settings)
    period_id = client.get('/api/v1/periods').json()[0]['id']
    preview = client.get(f'/api/v1/periods/{period_id}/deletion-preview').json()
    body = {
        'expectedVersion': preview['version'],
        'confirmation': preview['periodName'],
        **{f'expected{k[0].upper()}{k[1:]}': preview[k]
           for k in ('monthlyRuns', 'annualRuns', 'businessRows', 'documents')},
    }
    url = f'/api/v1/periods/{period_id}'
    assert client.request('DELETE', url, json=body | {'confirmation': 'wrong'}).status_code == 400
    assert len(client.get('/api/v1/periods').json()) == 1
    response = client.request('DELETE', url, json=body)
    assert response.status_code == 200, response.text
    assert client.get('/api/v1/periods').json() == []
    event = next(e for e in client.get('/api/v1/audit').json()['items'] if e['action'] == 'period.deleted')
    assert event['details']['reason'] is None

