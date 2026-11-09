import io
import json
import pytest
from PIL import Image
from studio.assets import ingest_image
from studio.config import Settings
from studio.models import Brief, Draft
from studio.service import StudioService
from studio.store import Store
from tools.video.seedance_ark import SeedanceArkVideo
from test_contract import draft_data


def setup_job(tmp_path, monkeypatch):
    store = Store(tmp_path)
    settings = Settings(store)
    monkeypatch.setattr(settings, 'secret', lambda _: 'test-credential')
    store.save_settings({'video_provider': 'ark'})
    service = StudioService(store, settings)
    ids = []
    for role, color in [('character','red'),('scene','green'),('game','blue')]:
        b = io.BytesIO()
        Image.new('RGB', (600,800), color).save(b, 'PNG')
        ids.append(ingest_image(store, b.getvalue(), role, role)['id'])
    request = {'theme':'厨房游戏','character_mode':'upload','character_id':ids[0],'scene_id':ids[1],'game_id':ids[2]}
    job = store.create_job(request)
    store.update_job(job['id'], status='draft_ready', prompt='Test one take', draft=draft_data())
    store.claim_submission(job['id'])
    return store, settings, service, job['id'], ids


def test_real_ark_payload_preserves_three_refs_and_async_task(tmp_path, monkeypatch):
    store, _, service, jid, ids = setup_job(tmp_path, monkeypatch)
    payloads = []
    def create(self, payload, key):
        payloads.append(payload)
        return 'task-123'
    monkeypatch.setattr(SeedanceArkVideo, '_create_task', create)
    service.submit(jid)
    assert store.get_job(jid)['task_id'] == 'task-123'
    payload = payloads[0]
    assert payload['duration'] == 15 and payload['ratio'] == '9:16' and payload['generate_audio'] is True
    images = [item for item in payload['content'] if item['type']=='image_url']
    assert len(images) == 3
    import base64
    from pathlib import Path
    for item, aid in zip(images, ids):
        assert item['role'] == 'reference_image'
        assert base64.b64decode(item['image_url']['url'].split(',')[1]) == Path(store.get_asset(aid)['path']).read_bytes()


def test_network_ambiguity_is_not_auto_resubmitted(tmp_path, monkeypatch):
    store, _, service, jid, _ = setup_job(tmp_path, monkeypatch)
    def create(*args):
        raise TimeoutError('paid POST timed out')
    monkeypatch.setattr(SeedanceArkVideo, '_create_task', create)
    service.submit(jid)
    assert store.get_job(jid)['status'] == 'submission_unknown'
    assert store.claim_submission(jid) is False


def test_definitive_ark_input_rejection_is_failed_not_submission_unknown(tmp_path, monkeypatch):
    import requests
    store, _, service, jid, _ = setup_job(tmp_path, monkeypatch)
    response = requests.Response()
    response.status_code = 400
    response.url = 'https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks'

    def reject(*args):
        raise requests.HTTPError(
            "400 Client Error: InputImageSensitiveContentDetected.PrivacyInformation",
            response=response,
        )

    monkeypatch.setattr(SeedanceArkVideo, '_create_task', reject)
    service.submit(jid)
    job = store.get_job(jid)
    assert job['status'] == 'failed'
    assert job['task_id'] is None
    assert '真人' in job['error'] and '授权' in job['error']


def test_model_preflight_failure_is_retryable_without_paid_post(tmp_path, monkeypatch):
    store, settings, service, jid, _ = setup_job(tmp_path, monkeypatch)
    store.save_settings({'ark_model':'unrecognized-model'})
    def forbidden(*args):
        raise AssertionError('must not submit')
    monkeypatch.setattr(SeedanceArkVideo, '_create_task', forbidden)
    service.submit(jid)
    assert store.get_job(jid)['status'] == 'draft_ready'
    assert store.get_job(jid)['error']


def test_provider_success_download_and_restart_preserve_output(tmp_path, monkeypatch):
    store, _, service, jid, _ = setup_job(tmp_path, monkeypatch)
    monkeypatch.setattr(SeedanceArkVideo, '_create_task', lambda *args: 'task-existing')
    service.submit(jid)
    assert store.get_job(jid)['status'] == 'queued'
    monkeypatch.setattr(SeedanceArkVideo, '_query_task', lambda *args: {'id':'task-existing','status':'succeeded','content':{'video_url':'https://provider.example/video.mp4'}})
    def download(url, path):
        path.write_bytes(b'provider-response-test')
    monkeypatch.setattr(SeedanceArkVideo, '_download_video', staticmethod(download))
    service.refresh(jid)
    restored = Store(tmp_path).get_job(jid)
    assert restored['status'] == 'succeeded'
    assert restored['video_url'] == f'/api/videos/{jid}'
    assert not restored.get('error')


def test_llm_receives_images_and_preserves_explicit_dialogue(tmp_path, monkeypatch):
    from studio.director import create_draft
    from pathlib import Path
    store, settings, service, jid, ids = setup_job(tmp_path, monkeypatch)
    store.save_settings({'llm_base_url':'https://director.example/v1','llm_model':'vision-model'})
    bodies=[]
    class Response:
        ok=True
        def json(self):
            return {'choices':[{'message':{'content':json.dumps(draft_data())}}]}
    def post(url, **kwargs):
        bodies.append(kwargs['json'])
        return Response()
    monkeypatch.setattr('studio.director.requests.post', post)
    brief = Brief(**store.get_job(jid)['request'], dialogue_override='Olha este jogo!')
    draft = create_draft(brief, [store.get_asset(aid) for aid in ids], settings)
    assert draft.dialogue_pt_br == 'Olha este jogo!'
    messages = bodies[0]['messages']
    images = [c for c in messages[1]['content'] if c['type']=='image_url']
    assert len(images) == 3
    assert all(c['image_url']['url'].startswith('data:image/webp;base64,') for c in images)
    assert '厨房游戏' in messages[1]['content'][0]['text']


@pytest.mark.parametrize('language', ['pt-BR', 'es-MX', 'en-US', 'fil-PH'])
def test_director_gets_phone_geometry_rules_in_every_market(tmp_path, monkeypatch, language):
    from studio.director import create_draft
    store, settings, _, jid, ids = setup_job(tmp_path, monkeypatch)
    calls = []
    class Response:
        ok = True
        def json(self):
            return {'choices': [{'message': {'content': json.dumps(draft_data())}}]}
    def post(url, **kwargs):
        calls.append(kwargs['json'])
        return Response()
    monkeypatch.setattr('studio.director.requests.post', post)
    request = store.get_job(jid)['request']
    request['language'] = language
    create_draft(Brief(**request), [store.get_asset(aid) for aid in ids], settings)
    system = calls[0]['messages'][0]['content']
    assert '展示时手机必须竖握、屏幕正面朝向镜头、顶部朝上，不能拿反、不能镜像' in system
    assert 'The back may be visible before display' in system
    assert 'never a screen' in system


def test_deepseek_json_mode_marker_is_removed_without_relaxing_draft_schema(tmp_path, monkeypatch):
    from studio.director import create_draft
    store, settings, _, jid, ids = setup_job(tmp_path, monkeypatch)
    payload = {**draft_data(), 'type': 'json_object'}

    class Response:
        ok = True
        def json(self):
            return {'choices': [{'message': {'content': json.dumps(payload)}}]}

    monkeypatch.setattr('studio.director.requests.post', lambda *args, **kwargs: Response())
    brief = Brief(**store.get_job(jid)['request'])
    draft = create_draft(brief, [store.get_asset(aid) for aid in ids], settings)
    assert draft.title == payload['title']

    payload['unexpected'] = 'still forbidden'
    try:
        create_draft(brief, [store.get_asset(aid) for aid in ids], settings)
    except ValueError as exc:
        assert 'unexpected' in str(exc)
    else:
        raise AssertionError('unknown fields must remain forbidden')


def test_flova_checkpoint_uses_recompiled_prompt_after_provider_change(tmp_path, monkeypatch):
    store, settings, service, jid, _ = setup_job(tmp_path, monkeypatch)
    store.save_settings({'video_provider': 'flova'})
    store.update_job(jid, prompt='previous 480p prompt')
    checkpoints = []
    monkeypatch.setattr(service, 'checkpoint', lambda jid, stage, status, artifacts, **kw: checkpoints.append((stage, artifacts)))
    monkeypatch.setattr('studio.service.find_flova_cli', lambda _: 'flova-test')
    sent = []
    class Provider:
        def __init__(self, executable):
            pass
        def generate(self, **kwargs):
            sent.append(kwargs['prompt'])
            return {'status': 'pending'}
    monkeypatch.setattr('studio.service.FlovaCLIProvider', Provider)
    service.submit(jid)
    packet = next(data['generation_packet'] for stage, data in checkpoints if stage == 'ugc_generate')
    assert packet['prompt'] == sent[0] == store.get_job(jid)['prompt']
    assert '720p' in packet['prompt'] and '480p' not in packet['prompt']


def test_manual_dialogue_overrides_invalid_director_line_but_not_conflicting_fields(tmp_path, monkeypatch):
    import pytest
    from studio.director import create_draft
    store, settings, _, jid, ids = setup_job(tmp_path, monkeypatch)
    payload = {**draft_data(), 'dialogue_pt_br': ''}
    class Response:
        ok = True
        def json(self):
            return {'choices': [{'message': {'content': json.dumps(payload)}}]}
    monkeypatch.setattr('studio.director.requests.post', lambda *args, **kwargs: Response())
    brief = Brief(**store.get_job(jid)['request'], dialogue_override='  Original line!  ')
    draft = create_draft(brief, [store.get_asset(aid) for aid in ids], settings)
    assert draft.dialogue == '  Original line!  '
    payload['dialogue'] = 'different'
    with pytest.raises(ValueError, match='冲突'):
        create_draft(brief, [store.get_asset(aid) for aid in ids], settings)


@pytest.mark.parametrize('language', ['pt-BR', 'es-MX', 'en-US', 'fil-PH'])
@pytest.mark.parametrize('provider', ['ark', 'wavespeed', 'flova'])
def test_four_markets_reach_all_three_gateway_prompts(tmp_path, monkeypatch, language, provider):
    from types import SimpleNamespace
    from studio.languages import LANGUAGES
    store, settings, service, jid, _ = setup_job(tmp_path, monkeypatch)
    request = store.get_job(jid)['request']
    request['language'] = language
    draft = draft_data()
    draft['language'] = language
    store.update_job(jid, request=request, draft=draft)
    store.save_settings({'video_provider': provider})
    monkeypatch.setattr(settings, 'require', lambda _: None)
    sent = []
    class Ark:
        def dry_run(self, inputs):
            return {'valid': True, 'model': 'mock-ark', 'duration': 15, 'ratio': '9:16', 'resolution': '480p'}
        def execute(self, inputs):
            sent.append(inputs['prompt'])
            return SimpleNamespace(success=True, data={'task_id': 'mock-task'})
    class WaveSpeed:
        def submit(self, **kwargs):
            sent.append(kwargs['prompt'])
            return {'id': 'mock-task'}
    class Flova:
        def __init__(self, executable):
            pass
        def generate(self, **kwargs):
            sent.append(kwargs['prompt'])
            return {'status': 'pending'}
    monkeypatch.setattr('studio.service.seedance_tool', lambda _: Ark())
    monkeypatch.setattr('studio.service.wavespeed_provider', lambda _: WaveSpeed())
    monkeypatch.setattr('studio.service.find_flova_cli', lambda _: 'mock-flova')
    monkeypatch.setattr('studio.service.FlovaCLIProvider', Flova)
    service.submit(jid)
    job = store.get_job(jid)
    assert len(sent) == 1 and sent[0] == job['prompt']
    assert language in sent[0] and LANGUAGES[language] in sent[0]
    assert all(x in sent[0] for x in ('15秒', '9:16', '@image1', '@image2', '@image3', '一镜到底'))
    assert '屏幕和后置摄像头不能出现在同一面' in sent[0]
    assert '手机背面只能显示背壳和后置摄像头，不能显示屏幕' in sent[0]
    assert ('720p' if provider == 'flova' else '480p') in sent[0]
    if language != 'pt-BR':
        assert '巴西葡语' not in sent[0] and 'pt-BR' not in sent[0]
    assert service.packet(jid)['language'] == language


def test_legacy_draft_ready_submission_and_restart_query_do_not_resubmit(tmp_path, monkeypatch):
    store, settings, service, jid, _ = setup_job(tmp_path, monkeypatch)
    # setup_job has no request.language and has legacy dialogue_pt_br only.
    assert 'language' not in store.get_job(jid)['request']
    assert 'dialogue_pt_br' in store.get_job(jid)['draft']
    store.save_settings({'video_provider': 'wavespeed'})
    submitted, queried = [], []
    class Provider:
        def submit(self, **kwargs):
            submitted.append(kwargs['prompt'])
            return {'id': 'existing-provider-id'}
        def query(self, task_id):
            queried.append(task_id)
            return {'status': 'running'}
    monkeypatch.setattr('studio.service.wavespeed_provider', lambda _: Provider())
    service.submit(jid)
    assert len(submitted) == 1 and 'pt-BR' in submitted[0]
    assert store.get_job(jid)['status'] == 'queued'
    restored = Store(tmp_path)
    restored.recover()
    StudioService(restored, settings).refresh(jid)
    assert queried == ['existing-provider-id'] and len(submitted) == 1
    assert restored.get_job(jid)['status'] == 'running'
    assert restored.claim_submission(jid) is False
