import hashlib
import struct

from app.modules.identity.auth import Principal, current_principal
from app.modules.reporting import project_maps
from test_api_worker import system as system


def test_catalog_preserves_only_the_six_map_pages(system):
    _, client, _ = system
    response = client.get('/api/v1/project-maps')
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['sourceFile'] == 'Fixed Asset ID Process & Progress - 11 August 2026.pptx'
    assert catalog['date'] == '2026-08-11'
    assert len(catalog['sourceSha256']) == 64
    assert [p['slide'] for p in catalog['pages']] == [3, 4, 5, 6, 7, 8]
    assert len({p['id'] for p in catalog['pages']}) == 6
    assert all(p['es'] and p['en'] and p['text'] for p in catalog['pages'])
    assert all(p['width'] == 2880 and p['height'] == 1620 for p in catalog['pages'])
    assert 'ADD SCREENSHOT' not in response.text
    assert response.headers['cache-control'] == 'no-store'


def test_all_maps_and_thumbnails_are_real_distinct_pngs(system):
    _, client, _ = system
    images = []
    for page in client.get('/api/v1/project-maps').json()['pages']:
        for thumbnail in (False, True):
            response = client.get(f"/api/v1/project-maps/{page['id']}/image", params={'thumbnail': thumbnail})
            assert response.status_code == 200
            assert response.headers['content-type'] == 'image/png'
            assert response.headers['cache-control'] == 'no-store'
            assert response.content.startswith(b'\x89PNG\r\n\x1a\n')
            assert struct.unpack('>II', response.content[16:24]) == ((320, 180) if thumbnail else (2880, 1620))
            images.append(hashlib.sha256(response.content).hexdigest())
    assert len(set(images)) == 12


def test_map_routes_require_identity_roles_and_scope(system):
    app, client, settings = system
    for principal, expected in [
        (Principal('reader', 'Reader', frozenset({'Reader'}), settings.scope_id), 200),
        (Principal('none', 'None', frozenset(), settings.scope_id), 403),
        (Principal('other', 'Other', frozenset({'Reader'}), 'other-scope'), 404),
    ]:
        app.dependency_overrides[current_principal] = lambda: principal
        assert client.get('/api/v1/project-maps').status_code == expected
        assert client.get('/api/v1/project-maps/plant-1/image').status_code == expected
    app.dependency_overrides.clear()
    app.state.settings = settings.model_copy(update={'auth_mode': 'entra'})
    assert client.get('/api/v1/project-maps').status_code == 401
    assert client.get('/api/v1/project-maps/plant-1/image').status_code == 401


def test_unknown_maps_and_filesystem_paths_are_not_exposed(system):
    _, client, _ = system
    for name in ['unknown-map', 'manifest.json', '..%2Fmanifest.json']:
        assert client.get(f'/api/v1/project-maps/{name}/image').status_code == 404
    assert client.get('/resources/project-maps/plant-1.png').status_code == 404


def test_missing_map_returns_controlled_unavailable_error(system, monkeypatch, tmp_path):
    _, client, _ = system
    client.get('/api/v1/project-maps')
    monkeypatch.setattr(project_maps, 'RESOURCE_DIR', tmp_path)
    assert client.get('/api/v1/project-maps/plant-1/image').status_code == 503
