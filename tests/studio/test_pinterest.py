import pytest
from studio.config import Settings
from studio.store import Store
from studio.pinterest import search_board, safe_pin_image


def test_theme_is_translated_to_scene_query_before_board_filter(tmp_path, monkeypatch):
    settings = Settings(Store(tmp_path))
    settings.store.save_settings({'pinterest_board_id':'123', 'llm_base_url':'https://director.example/v1','llm_model':'vision'})
    monkeypatch.setattr(settings, 'secret', lambda _: 'test-only')
    class Response:
        ok=True
        def json(self):
            return {'choices':[{'message':{'content':'{"query":"cozinha apartamento Brasil luz natural"}'}}]}
    monkeypatch.setattr('studio.director.requests.post', lambda *a, **kw: Response())
    monkeypatch.setattr('studio.pinterest.api_get', lambda *a, **kw: {'items':[{'id':'99','title':'Cozinha brasileira','media':{'images':{'600x':{'url':'https://i.pinimg.com/example.jpg'}}}}]})
    result = search_board(settings, '午后厨房游戏')
    assert result['recommended_query'] == 'cozinha apartamento Brasil luz natural'
    assert [p['id'] for p in result['items']] == ['99']


@pytest.mark.parametrize('url', ['http://i.pinimg.com/a.png','https://i.pinimg.com.evil.example/a.png','http://127.0.0.1:8787/private','https://user@i.pinimg.com/a.png'])
def test_remote_scene_download_cannot_target_arbitrary_host(url):
    assert not safe_pin_image(url)


def test_english_search_is_localized_for_selected_market(tmp_path, monkeypatch):
    settings = Settings(Store(tmp_path))
    settings.store.save_settings({'pinterest_board_id':'123', 'llm_base_url':'https://director.example/v1','llm_model':'vision'})
    monkeypatch.setattr(settings, 'secret', lambda _: 'test-only')
    calls = []
    class Response:
        ok=True
        def json(self):
            return {'choices':[{'message':{'content':'{"query":"cocina mexicana luz natural"}'}}]}
    def post(*a, **kw):
        calls.append(kw['json'])
        return Response()
    monkeypatch.setattr('studio.director.requests.post', post)
    monkeypatch.setattr('studio.pinterest.api_get', lambda *a, **kw: {'items':[]})
    result = search_board(settings, 'kitchen', language='es-MX')
    assert result['recommended_query'] == 'cocina mexicana luz natural'
    assert 'es-MX' in calls[0]['messages'][0]['content']
