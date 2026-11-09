import json
import threading
from pathlib import Path
from .models import Brief, Draft
from .languages import LANGUAGES
from .director import create_draft, compile_prompt, generation_inputs
from .providers import FlovaCLIProvider, WaveSpeedPreSubmitError, find_flova_cli, seedance_tool, wavespeed_provider


class StudioService:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.refresh_lock = threading.Lock()

    def resolution(self):
        config = self.settings.get()
        return config['flova_resolution'] if config['video_provider'] == 'flova' else '480p'

    def resolve_assets(self, brief):
        actor_id = brief.character_id
        if brief.character_mode == 'default':
            defaults = [a for a in self.store.assets('character') if a['is_default']]
            if not defaults:
                raise ValueError('还没有默认人物。请先上传一张人物图并设为默认。')
            actor_id = defaults[0]['id']
            brief.character_id = actor_id
        pairs = [(actor_id, 'character'), (brief.scene_id, 'scene')]
        if brief.game_id:
            pairs.append((brief.game_id, 'game'))
        assets = []
        for aid, role in pairs:
            asset = self.store.get_asset(aid)
            if asset['role'] != role:
                raise ValueError(f'参考图用途不匹配：{role}。')
            assets.append(asset)
        return assets

    def draft(self, jid):
        try:
            job = self.store.get_job(jid)
            self.checkpoint(jid, 'ugc_script', 'in_progress', {})
            brief = Brief(**job['request'])
            # The default actor ID was resolved at intake, never re-resolve a mutable default.
            brief.character_mode = 'upload'
            assets = self.resolve_assets(brief)
            draft = create_draft(brief, assets, self.settings)
            prompt = compile_prompt(brief, draft, self.resolution())
            self.store.update_job(jid, status='draft_ready', draft=draft.model_dump(), prompt=prompt, error=None)
            self.write_artifacts(jid)
            self.checkpoint(jid, 'ugc_script', 'awaiting_human', {'ugc_draft': draft.model_dump()})
        except Exception as exc:
            self.store.update_job(jid, status='failed', error=self.safe_error(exc, '策划失败'))

    def submit(self, jid):
        provider_name = self.settings.get()['video_provider']
        try:
            self.settings.require(provider_name)
            job = self.store.get_job(jid)
            brief = Brief(**job['request'])
            brief.character_mode = 'upload'
            assets = self.resolve_assets(brief)
            draft = Draft(**job['draft'])
            if draft.language != brief.language:
                raise ValueError('草稿语言与任务语言不一致。')
            prompt = compile_prompt(brief, draft, self.resolution())
            config = self.settings.get()
            from lib.pipeline_loader import load_pipeline
            manifest = load_pipeline('brazil-ugc-game-ad')
            stage = next(stage for stage in manifest['stages'] if stage['name'] == 'ugc_generate')
            # Skills are part of the execution contract, not decorative files.
            instructions = (Path(__file__).resolve().parent.parent / stage['skill']).read_text(encoding='utf-8')
            if not instructions.strip():
                raise ValueError('视频生成阶段 skill 为空。')
            paths = [a['path'] for a in assets]
            if provider_name == 'ark':
                inputs = generation_inputs(prompt, paths, config['ark_model'])
                tool = seedance_tool(self.settings)
                check = tool.dry_run(inputs)
                if not check.get('valid'):
                    self.store.update_job(jid, status='draft_ready', error=self.redact(check.get('error') or 'Seedance 参数验证失败。'))
                    return
                model = check.get('model')
                preflight = {k: check.get(k) for k in ['model', 'duration', 'ratio', 'resolution', 'media_counts']}
            elif provider_name == 'wavespeed':
                tool = wavespeed_provider(self.settings)
                model = config['wavespeed_model']
                preflight = {'model': model, 'duration': 15, 'ratio': '9:16',
                             'resolution': config['wavespeed_resolution'], 'media_counts': {'image': len(paths)}}
            elif provider_name == 'flova':
                tool = FlovaCLIProvider(find_flova_cli(config['flova_cli_path']))
                model = config['flova_model']
                preflight = {'model': model, 'duration': 15, 'ratio': '9:16',
                             'resolution': config['flova_resolution'], 'media_counts': {'image': len(paths)}}
            else:
                raise ValueError('未知的视频服务。')
            # Persist exact backend/spec before crossing the paid request boundary.
            self.store.update_job(jid, prompt=prompt, provider=provider_name, model=model, preflight=preflight)
            self.checkpoint(jid, 'ugc_script', 'completed', {'ugc_draft': job['draft']}, approved=True)
            self.checkpoint(jid, 'ugc_generate', 'in_progress', {'generation_packet': self.packet(jid)})
        except Exception as exc:
            self.store.update_job(jid, status='draft_ready', error=self.safe_error(exc, '提交预检失败'))
            return
        try:
            if provider_name == 'ark':
                result = tool.execute(inputs)
                if result.success and result.data.get('task_id'):
                    self.store.update_job(jid, status='queued', task_id=result.data['task_id'], error=None)
                elif (result.data or {}).get('status') == 'rejected':
                    error = self.redact(result.error or '方舟拒绝了输入内容。')
                    if 'InputImageSensitiveContentDetected.PrivacyInformation' in error:
                        error = '方舟将人物参考图判定为真人或隐私信息。请改用明显虚构角色，或先在方舟完成该人物的授权流程。'
                    self.store.update_job(jid, status='failed', error=error, task_id=None)
                else:
                    self.store.update_job(jid, status='submission_unknown', error=self.redact(result.error or '提交结果未知；请核对服务商任务。'), task_id=(result.data or {}).get('task_id'))
            elif provider_name == 'wavespeed':
                result = tool.submit(prompt=prompt, reference_paths=paths, model=config['wavespeed_model'],
                                     resolution=config['wavespeed_resolution'], duration=15)
                self.store.update_job(jid, status='queued', task_id=result['id'], error=None)
            else:
                output = self.store.projects / jid / 'renders' / 'final.mp4'
                result = tool.generate(api_key=self.settings.secret('flova_api_key'), project_name=job['theme'],
                    prompt=prompt, reference_paths=paths, output_path=output, model=config['flova_model'],
                    resolution=config['flova_resolution'], duration=15)
                if result['status'] == 'succeeded':
                    self.store.update_job(jid, status='succeeded', video_url=f'/api/videos/{jid}', error=None,
                        output_path=str(output), provider_project_url=result.get('project_url'),
                        review_status=f'待人工检查：人物、手指、屏幕内容、连续性与{LANGUAGES[brief.language]}口型')
                else:
                    self.store.update_job(jid, status='submission_unknown', task_id=result.get('stream_chat_id'),
                        provider_project_url=result.get('project_url'), error='Flova 需要在项目页完成确认或核对任务状态。')
        except WaveSpeedPreSubmitError as exc:
            self.store.update_job(jid, status='draft_ready', error=self.safe_error(exc, '素材上传失败'))
        except Exception as exc:
            self.store.update_job(jid, status='submission_unknown', error=self.safe_error(exc, '提交结果未知，请核对服务商任务，避免重复计费'))
        self.write_artifacts(jid)

    def refresh(self, jid):
        # One provider query/download at a time across browser + background polling.
        if not self.refresh_lock.acquire(blocking=False):
            return self.store.get_job(jid)
        try:
            job = self.store.get_job(jid)
            if not job.get('task_id') or job['status'] not in ('queued', 'running', 'submission_unknown'):
                return job
            if job.get('provider') == 'wavespeed':
                tool = wavespeed_provider(self.settings)
                task = tool.query(job['task_id'])
                status = task.get('status')
            elif job.get('provider') == 'flova':
                return job
            else:
                tool = seedance_tool(self.settings)
                result = tool.execute({'task_action': 'query', 'task_id': job['task_id'], 'model': job.get('model') or ''})
                if not result.success:
                    return self.store.update_job(jid, error=self.redact(result.error or '暂时无法查询任务。'))
                task = result.data['task']
                status = task.get('status')
            if status in ('succeeded', 'completed'):
                if job.get('provider') == 'wavespeed':
                    output_item = (task.get('outputs') or [None])[0]
                    url = output_item if isinstance(output_item, str) else (output_item or {}).get('url')
                else:
                    url = (task.get('content') or {}).get('video_url')
                if not url:
                    raise ValueError('服务商任务成功但没有返回视频链接。')
                output = self.store.projects / jid / 'renders' / 'final.mp4'
                if job.get('provider') == 'wavespeed':
                    tool.download(url, output)
                else:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    tool._download_video(url, output)
                if not output.is_file() or output.stat().st_size == 0:
                    raise ValueError('视频下载为空，请重试查询。')
                job = self.store.update_job(jid, status='succeeded', video_url=f'/api/videos/{jid}', error=None,
                        review_status=f"待人工检查：人物、手指、屏幕内容、连续性与{LANGUAGES[Brief(**job['request']).language]}口型", output_path=str(output))
                # Recovered provider tasks keep the approved script checkpoint from submission.
                self.checkpoint(jid, 'ugc_generate', 'completed', {'generation_packet': self.packet(jid)})
            elif status in ('failed', 'cancelled', 'expired', 'timeout', 'deleted'):
                job = self.store.update_job(jid, status='failed', error=f'Seedance 任务 {status}。请在服务商控制台查看原因。')
            else:
                job = self.store.update_job(jid, status='queued' if status == 'queued' else 'running', error=None)
            self.write_artifacts(jid)
            return job
        except Exception as exc:
            return self.store.update_job(jid, error=self.safe_error(exc, '查询或下载失败，可稍后重试'))
        finally:
            self.refresh_lock.release()

    def redact(self, message):
        for key in ['llm_api_key', 'ark_api_key', 'wavespeed_api_key', 'flova_api_key', 'pinterest_access_token']:
            secret = self.settings.secret(key)
            if secret:
                message = str(message).replace(secret, '[已隐藏]')
        return str(message)[:1000]

    def safe_error(self, exc, prefix):
        # Network exceptions often contain URLs/auth fragments; do not echo them.
        if isinstance(exc, ValueError):
            return self.redact(f'{prefix}：{exc}')
        return f'{prefix}（{type(exc).__name__}），请检查服务设置和网络后重试。'

    def packet(self, jid):
        job = self.store.get_job(jid)
        refs = []
        for field, role in [('character_id', 'identity'), ('scene_id', 'environment'), ('game_id', 'phone_screen')]:
            if job['request'].get(field):
                refs.append({'label': f'图片{len(refs)+1}', 'role': role, 'asset_id': job['request'][field]})
        return {'version': 2, 'language': Brief(**job['request']).language, 'pipeline': 'brazil-ugc-game-ad', 'duration': 15, 'aspect_ratio': '9:16', 'shot_count': 1,
                'references': refs, 'prompt': job.get('prompt'), 'draft': job.get('draft'), 'task_id': job.get('task_id')}

    def checkpoint(self, jid, stage, status, artifacts, approved=False):
        from lib.checkpoint import init_project, write_checkpoint
        job = self.store.get_job(jid)
        init_project(jid, title=job['theme'], pipeline_type='brazil-ugc-game-ad', pipeline_dir=self.store.projects)
        return write_checkpoint(self.store.projects, jid, stage, status, artifacts,
            pipeline_type='brazil-ugc-game-ad', human_approved=approved)

    def write_artifacts(self, jid):
        directory = self.store.projects / jid / 'artifacts'
        directory.mkdir(parents=True, exist_ok=True)
        packet = self.packet(jid)
        path = directory / 'generation_packet.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
