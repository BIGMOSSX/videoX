from fastapi.testclient import TestClient
from studio.app import create_app


def test_check_endpoint_uses_text_only_and_conservative_results(tmp_path, monkeypatch):
    import studio.language_check as lc
    captured = {}
    class Response:
        ok = True
        def json(self):
            return {'choices': [{'message': {'content': '{"results":[{"line":1,"language":"en-US","confidence":0.99},{"line":2,"language":"en-US","confidence":0.99}]}'}}]}
    def fake_post(url, **kwargs):
        captured.update(kwargs['json'])
        return Response()
    monkeypatch.setattr(lc.requests, 'post', fake_post)
    app = create_app(tmp_path)
    monkeypatch.setattr(app.state.settings, 'require', lambda _: None)
    monkeypatch.setattr(app.state.settings, 'secret', lambda _: 'test')
    with TestClient(app, base_url='http://127.0.0.1:8787') as c:
        r = c.post('/api/language-check', json={'language': 'es-MX', 'dialogue_lines': ['This is a clearly English sentence for testing', 'Nike', '  ']})
    assert r.status_code == 200
    assert [x['status'] for x in r.json()['results']] == ['likely_mismatch', 'uncertain']
    assert all(isinstance(m['content'], str) for m in captured['messages'])


def test_check_failure_is_explicit_and_invalid_language_rejected(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8787') as c:
        r = c.post('/api/language-check', json={'language': 'es-MX', 'dialogue_lines': ['A longer line that needs an evaluation']})
        assert r.json()['status'] == 'failed'
        assert c.post('/api/language-check', json={'language': 'bad', 'dialogue_lines': []}).status_code == 422


def test_ten_lines_map_seventh_and_taglish_is_uncertain(monkeypatch):
    import json
    import studio.language_check as lc
    class Settings:
        def require(self, _): pass
        def get(self): return {'llm_base_url': 'https://example.com', 'llm_model': 'test'}
        def secret(self, _): return 'secret'
    class Response:
        ok = True
        def json(self):
            rows = [{'line': i, 'language': 'en-US' if i == 7 else 'es-MX', 'confidence': 0.99} for i in range(1, 11)]
            return {'choices': [{'message': {'content': json.dumps({'results': rows})}}]}
    monkeypatch.setattr(lc.requests, 'post', lambda *args, **kwargs: Response())
    lines = ['Una frase suficiente para poder identificar el idioma'] * 10
    result = lc.check_dialogue('es-MX', lines, Settings())
    assert [row['line'] for row in result['results'] if row['status'] == 'likely_mismatch'] == [7]
    assert '英语' in result['results'][6]['message'] and '美式英语' not in result['results'][6]['message']
    assert all(row['status'] == 'uncertain' for row in lc.check_dialogue('fil-PH', lines, Settings())['results'] if row['line'] == 7)


def test_one_character_dialogue_survives_draft():
    from studio.models import Draft
    from test_contract import draft_data
    data = draft_data()
    data['dialogue_pt_br'] = '🎉'
    assert Draft(**data).dialogue == '🎉'


def test_filipino_target_flags_clear_english_but_not_taglish_or_ambiguous(monkeypatch):
    import json
    import studio.language_check as lc
    class Settings:
        def require(self, _): pass
        def get(self): return {'llm_base_url': 'https://example.com', 'llm_model': 'test'}
        def secret(self, _): return 'secret'
    class Response:
        ok = True
        def json(self):
            rows = [
                {'line': 1, 'language': 'en-US', 'confidence': 0.99, 'pure_language': True},
                {'line': 2, 'language': 'en-US', 'confidence': 0.99, 'pure_language': False},
                {'line': 3, 'language': 'en-US', 'confidence': 0.99},
            ]
            return {'choices': [{'message': {'content': json.dumps({'results': rows})}}]}
    monkeypatch.setattr(lc.requests, 'post', lambda *args, **kwargs: Response())
    lines = ['I want to show you this incredible game today',
             'Ang saya nito, you should try this game now',
             'This is a sentence that may be ambiguous']
    result = lc.check_dialogue('fil-PH', lines, Settings())
    assert [x['status'] for x in result['results']] == ['likely_mismatch', 'uncertain', 'uncertain']
