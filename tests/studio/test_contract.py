import pytest
from studio.models import BatchBrief, Brief, Draft
from studio.director import compile_prompt, generation_inputs
from studio.store import Store


def draft_data():
    return dict(title='Pausa para jogar', hook='咖啡蒸汽升起，主角看向手机。', dialogue_pt_br='Olha esse jogo na minha pausa para o café!',
                scene_description='Cozinha de apartamento em São Paulo',
                background_motion='A cortina se move com o vento.', ambience='Cafeteira baixa e trânsito distante.',
                beats=[dict(start=a, end=b, action='Segura o único celular.', camera='Aproximação contínua.', audio='Som ambiente.')
                       for a, b in [(0, 1.5), (1.5, 8.5), (8.5, 11), (11, 15)]])


def test_uploaded_character_is_required():
    with pytest.raises(ValueError):
        Brief(theme='Teste', character_mode='upload', scene_id='scene')


def test_timeline_cannot_jump_or_exceed_fifteen_seconds():
    data = draft_data()
    data['beats'][2]['start'] = 9
    with pytest.raises(ValueError):
        Draft(**data)


def test_game_reference_is_third_and_seedance_gets_one_fifteen_second_take():
    brief = Brief(theme='Café e jogo', character_mode='upload', character_id='actor', scene_id='scene', game_id='game')
    draft = Draft(**draft_data())
    prompt = compile_prompt(brief, draft)
    inputs = generation_inputs(prompt, ['actor.png', 'scene.png', 'game.png'], '')
    assert inputs['duration'] == 15
    assert inputs['aspect_ratio'] == '9:16'
    assert inputs['resolution'] == '480p'
    assert inputs['reference_image_paths'] == ['actor.png', 'scene.png', 'game.png']
    assert inputs['task_action'] == 'create'
    assert '@image3' in prompt and '唯一' in prompt
    assert '@image1' in prompt and '@image2' in prompt and '@image3' in prompt
    assert '@图像' not in prompt
    assert '480p' in prompt and '720p' not in prompt
    assert 'single continuous take, no cuts' in prompt
    assert draft.dialogue_pt_br in prompt
    assert draft.background_motion in prompt
    assert '首帧已经处于动作中' in prompt
    assert '0.2秒内开口' in prompt
    assert '11–15秒' in prompt
    assert '不添加口播' not in prompt
    assert '1.5秒后开始' not in prompt


def test_phone_stays_upright_and_game_image_is_locked_inside_screen():
    brief = Brief(
        theme='手机游戏展示',
        character_mode='upload',
        character_id='actor',
        scene_id='scene',
        game_id='game',
    )
    prompt = compile_prompt(brief, Draft(**draft_data()))

    orientation_lock = '手机必须竖直正向握持，屏幕正面朝向镜头，不能拿反。'
    screen_lock = '游戏画面必须直接显示在手机屏幕内，屏幕内容不重绘、不替换、不生成新的UI。'
    assert orientation_lock in prompt
    assert screen_lock in prompt
    assert prompt.index(orientation_lock) < prompt.index('完整呈现视线转向手机')
    assert '手机顶部始终朝上' in prompt


@pytest.mark.parametrize('language', ['pt-BR', 'es-MX', 'en-US', 'fil-PH'])
@pytest.mark.parametrize('game_id', [None, 'game'])
def test_phone_showcase_preserves_front_back_geometry_and_orientation(language, game_id):
    brief = Brief(theme='手机游戏展示', character_id='actor', scene_id='scene', game_id=game_id, language=language)
    prompt = compile_prompt(brief, Draft(**draft_data()))
    assert '展示时手机必须竖握、屏幕正面朝向镜头、顶部朝上，不能拿反、不能镜像' in prompt
    assert '屏幕和后置摄像头不能出现在同一面' in prompt
    assert '手机背面只能显示背壳和后置摄像头，不能显示屏幕' in prompt
    assert '水平转向镜头' in prompt


def test_job_submission_claim_is_atomic_and_persists(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({'theme': 'test'})
    store.update_job(job['id'], status='draft_ready')
    assert store.claim_submission(job['id']) is True
    assert store.claim_submission(job['id']) is False
    assert Store(tmp_path).get_job(job['id'])['status'] == 'submitting'


def test_asset_ids_cannot_escape_storage(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(KeyError):
        store.get_asset('../../private')


def test_old_active_jobs_survive_large_history_and_restart(tmp_path):
    store = Store(tmp_path)
    pending = store.create_job({'theme': 'pending'})
    paid = store.create_job({'theme': 'paid'})
    store.update_job(paid['id'], status='running', task_id='paid-task')
    for _ in range(101):
        newer = store.create_job({'theme': 'newer'})
        store.update_job(newer['id'], status='succeeded')
    assert len(store.jobs()) == 103
    assert {j['id'] for j in store.active_jobs()} == {pending['id'], paid['id']}
    restarted = Store(tmp_path)
    restarted.recover()
    assert restarted.get_job(pending['id'])['status'] == 'interrupted'
    assert [j['id'] for j in restarted.active_jobs()] == [paid['id']]


def test_hook_is_required_nonempty_and_compiled():
    data = draft_data()
    data['hook'] = '手机旁的咖啡蒸汽吸引主角视线'
    draft = Draft(**data)
    assert draft.hook in compile_prompt(Brief(theme='Teste', character_id='a', scene_id='s'), draft)
    for invalid in [None, '', '   ']:
        data['hook'] = invalid
        with pytest.raises(ValueError):
            Draft(**data)
    del data['hook']
    with pytest.raises(ValueError):
        Draft(**data)


def test_batch_brief_expands_to_ten_distinct_directing_contracts():
    batch = BatchBrief(
        theme='巴西玩家分享手机游戏',
        count=10,
        character_mode='upload',
        character_ids=['actor'],
        scene_ids=['scene-a', 'scene-b'],
        game_ids=['game'],
    )
    briefs = batch.expand()
    assert len(briefs) == 10
    assert len({brief.variation_direction for brief in briefs}) == 10
    assert [brief.scene_id for brief in briefs[:4]] == ['scene-a', 'scene-b', 'scene-a', 'scene-b']
    assert all(brief.character_id == 'actor' and brief.game_id == 'game' for brief in briefs)


def test_batch_manual_dialogue_requires_one_line_per_video():
    with pytest.raises(ValueError, match='每条视频'):
        BatchBrief(
            theme='巴西游戏广告', count=3, character_ids=['actor'],
            scene_ids=['scene'], dialogue_lines=['Primeira linha.', 'Segunda linha.'],
        )


def test_batch_submission_claim_is_all_or_nothing(tmp_path):
    store = Store(tmp_path)
    first = store.create_job({'theme': 'one', 'batch_id': 'a' * 32, 'variation_count': 2, 'variation_index': 1})
    second = store.create_job({'theme': 'two', 'batch_id': 'a' * 32, 'variation_count': 2, 'variation_index': 2})
    store.update_job(first['id'], status='draft_ready')

    assert store.claim_submissions([first['id'], second['id']]) is False
    assert store.get_job(first['id'])['status'] == 'draft_ready'
    assert store.get_job(second['id'])['status'] == 'drafting'

    store.update_job(second['id'], status='draft_ready')
    assert store.claim_submissions([first['id'], second['id']]) is True
    assert store.get_job(first['id'])['status'] == 'submitting'
    assert store.get_job(second['id'])['status'] == 'submitting'


def test_batch_submission_rejects_mixed_or_incomplete_batches(tmp_path):
    store = Store(tmp_path)
    first = store.create_job({'theme': 'one', 'batch_id': 'a' * 32, 'variation_count': 2, 'variation_index': 1})
    second = store.create_job({'theme': 'two', 'batch_id': 'b' * 32, 'variation_count': 2, 'variation_index': 2})
    for job in (first, second):
        store.update_job(job['id'], status='draft_ready')

    assert store.claim_submissions([first['id'], second['id']]) is False
    assert store.claim_submissions([first['id']]) is False
    assert store.get_job(first['id'])['status'] == 'draft_ready'
    assert store.get_job(second['id'])['status'] == 'draft_ready'


def test_batch_submission_rejects_duplicate_job_ids():
    from studio.models import BatchGenerate
    with pytest.raises(ValueError, match='重复'):
        BatchGenerate(job_ids=['same', 'same'])


def test_multimarket_contract_and_legacy_dialogue():
    from pydantic import ValidationError
    from studio.models import BatchBrief
    import pytest
    for lang in ('pt-BR', 'es-MX', 'en-US', 'fil-PH'):
        batch = BatchBrief(theme='test', count=10, character_mode='default', scene_ids=['s'], language=lang)
        assert all(b.language == lang for b in batch.expand())
        draft = Draft(**draft_data())
        prompt = compile_prompt(batch.expand()[0], draft)
        assert lang in prompt
        if lang != 'pt-BR':
            assert '巴西葡语' not in prompt
    assert Brief(theme='test', character_id='a', scene_id='s').language == 'pt-BR'
    with pytest.raises(ValidationError):
        Brief(theme='test', character_id='a', scene_id='s', language='xx')
    data = draft_data()
    data['dialogue'] = 'different text'
    with pytest.raises(ValidationError):
        Draft(**data)


def test_manual_dialogue_whitespace_and_resolution_are_preserved():
    from studio.models import BatchBrief
    text = '  Olha este jogo!  '
    brief = BatchBrief(theme='test', character_mode='default', scene_ids=['s'], dialogue_lines=[text], language='es-MX').expand()[0]
    assert brief.dialogue_override == text
    data = draft_data()
    data.pop('dialogue_pt_br')
    data.update(dialogue=text, language='es-MX')
    draft = Draft(**data)
    assert draft.dialogue == text
    prompt = compile_prompt(brief, draft, '720p')
    assert text in prompt and '720p' in prompt and '480p' not in prompt


def test_checkpoint_rejects_conflicting_dialogue_fields_and_accepts_legacy():
    import pytest
    from lib.checkpoint import _validate_artifacts_for_stage, CheckpointValidationError
    old = draft_data()
    _validate_artifacts_for_stage('ugc_script', 'completed', {'ugc_draft': old})
    conflict = {**old, 'dialogue': 'Different dialogue'}
    with pytest.raises(CheckpointValidationError, match='conflict'):
        _validate_artifacts_for_stage('ugc_script', 'completed', {'ugc_draft': conflict})
    packet = {'pipeline':'brazil-ugc-game-ad', 'duration':15, 'aspect_ratio':'9:16', 'shot_count':1,
              'references':[{'label':'1','role':'identity','asset_id':'a'}, {'label':'2','role':'environment','asset_id':'s'}],
              'prompt':'test', 'draft':conflict}
    with pytest.raises(CheckpointValidationError, match='conflict'):
        _validate_artifacts_for_stage('ugc_generate', 'completed', {'generation_packet': packet})
