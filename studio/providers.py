"""Video-provider bridges. Secrets never appear in subprocess arguments."""
import json
import mimetypes
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import requests

from tools.tool_registry import ToolRegistry
from tools.video import seedance_ark


def seedance_tool(settings):
    registry = ToolRegistry()
    registry.register_module(seedance_ark)
    tool = registry.get('seedance_ark')
    # Per-instance key accessor avoids mutating environment across concurrent jobs.
    tool._get_api_key = lambda: settings.secret('ark_api_key')
    return tool


class WaveSpeedPreSubmitError(ValueError):
    """A failure that happened before the paid prediction POST began."""


class WaveSpeedProvider:
    API_BASE = 'https://api.wavespeed.ai/api/v3'

    def __init__(self, api_key, session=requests):
        self.api_key, self.session = api_key, session

    @property
    def headers(self):
        return {'Authorization': f'Bearer {self.api_key}'}

    @staticmethod
    def _data(response, operation):
        if not response.ok:
            raise ValueError(f'WaveSpeed {operation}失败（HTTP {response.status_code}）。')
        body = response.json()
        data = body.get('data', body)
        if not isinstance(data, dict):
            raise ValueError(f'WaveSpeed {operation}返回格式无效。')
        return data

    @staticmethod
    def _https_url(value, name):
        parsed = urlsplit(str(value or ''))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f'WaveSpeed {name}地址无效。')
        return str(value)

    def upload(self, path):
        path = Path(path)
        payload = {'filename': path.name, 'size': path.stat().st_size}
        content_type = mimetypes.guess_type(path.name)[0]
        if content_type:
            payload['content_type'] = content_type
        ticket_response = self.session.post(
            self.API_BASE + '/media/uploads', headers={**self.headers, 'Content-Type': 'application/json'},
            json=payload, timeout=(10, 45),
        )
        ticket = self._data(ticket_response, '上传凭证')
        upload = ticket.get('upload') or {}
        upload_url = self._https_url(upload.get('url'), '上传')
        # The signed storage URL is an opaque temporary credential. Never send the API key to it.
        with path.open('rb') as file:
            response = self.session.put(
                upload_url, headers=upload.get('headers') or {}, data=file,
                timeout=(15, 300),
            )
        response.raise_for_status()
        return self._https_url(ticket.get('download_url'), '素材')

    def submit(self, *, prompt, reference_paths, model, resolution='480p', duration=15):
        if model != 'bytedance/seedance-2.0-mini/text-to-video':
            raise ValueError('当前只允许 WaveSpeed Seedance 2.0 Mini 多参考图端点。')
        if resolution != '480p' or duration != 15:
            raise ValueError('当前工作流固定为 480p / 15秒。')
        try:
            references = [self.upload(path) for path in reference_paths]
        except Exception as exc:
            raise WaveSpeedPreSubmitError(
                '素材上传失败，尚未提交付费任务，可以安全重试。'
            ) from exc
        payload = {
            'prompt': prompt, 'reference_images': references, 'aspect_ratio': '9:16',
            'resolution': resolution, 'duration': duration,
            'enable_web_search': False, 'generate_audio': True,
        }
        response = self.session.post(
            f'{self.API_BASE}/{model}',
            headers={**self.headers, 'Content-Type': 'application/json'},
            json=payload, timeout=(10, 60),
        )
        data = self._data(response, '付费任务提交')
        if not data.get('id'):
            raise ValueError('WaveSpeed 提交结果没有任务 ID。')
        return data

    def query(self, prediction_id):
        response = self.session.get(
            f'{self.API_BASE}/predictions/{prediction_id}/result',
            headers=self.headers, timeout=(10, 45),
        )
        return self._data(response, '任务查询')

    def download(self, url, path):
        url = self._https_url(url, '视频下载')
        response = self.session.get(url, timeout=(15, 300), stream=True)
        response.raise_for_status()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.part')
        with temporary.open('wb') as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)
        if not temporary.is_file() or not temporary.stat().st_size:
            raise ValueError('WaveSpeed 视频下载为空。')
        temporary.replace(target)


def wavespeed_provider(settings):
    return WaveSpeedProvider(settings.secret('wavespeed_api_key'))


class FlovaCLIError(RuntimeError):
    pass


class FlovaCLIProvider:
    """Use Flova's supported project-oriented CLI as a generation backend."""

    def __init__(self, executable='flova', runner=subprocess.run):
        self.executable = executable
        self.runner = runner

    def _call(self, arguments, *, input_text=None, timeout=600):
        command = [self.executable, *arguments]
        result = self.runner(
            command, input=input_text, text=True, capture_output=True,
            timeout=timeout, check=False,
        )
        try:
            envelope = json.loads((result.stdout or '').strip())
        except json.JSONDecodeError as exc:
            raise FlovaCLIError('Flova CLI 没有返回可读的 JSON 结果。') from exc
        if result.returncode != 0 or envelope.get('code') not in (0, '0'):
            error = envelope.get('error') or {}
            message = error.get('hint') or envelope.get('message') or 'Flova CLI 请求失败。'
            code = envelope.get('code')
            raise FlovaCLIError(f'{message} ({code})')
        return envelope, result.stderr or ''

    @staticmethod
    def _data(envelope):
        data = envelope.get('data') or {}
        if not isinstance(data, dict):
            raise FlovaCLIError('Flova CLI 返回的 data 格式无效。')
        return data

    @staticmethod
    def _ready_videos(stderr):
        paths = []
        for raw in stderr.splitlines():
            marker = 'flova_event='
            if marker not in raw:
                continue
            try:
                event = json.loads(raw.split(marker, 1)[1].strip())
            except json.JSONDecodeError:
                continue
            if event.get('type') == 'resource_ready' and event.get('asset_kind') == 'video_playback':
                path = Path(str(event.get('local_path') or ''))
                if path.is_absolute() and path.is_file() and path.stat().st_size:
                    paths.append(path)
        return paths

    def generate(self, *, api_key, project_name, prompt, reference_paths,
                 output_path, model='Seedance 2.5', resolution='720p', duration=15):
        if api_key:
            # Login accepts the key on stdin; never put it in argv, logs, or project files.
            self._call(['auth', 'login'], input_text=api_key + '\n', timeout=60)
        else:
            self._call(['auth', 'status'], timeout=30)

        created, _ = self._call([
            'project', 'create', '--name', project_name[:120],
            '--description', 'videoX UGC batch item; one 15-second continuous take',
        ], timeout=60)
        project = self._data(created)
        project_id = project.get('project_id')
        if not project_id:
            raise FlovaCLIError('Flova 项目已创建，但未返回 project_id。')

        with tempfile.TemporaryDirectory(prefix='videox-flova-') as temporary:
            upload_files = []
            for index, reference in enumerate(reference_paths, start=1):
                uploaded, _ = self._call(['upload', str(Path(reference).resolve())], timeout=600)
                envelope_path = Path(temporary) / f'upload-{index}.json'
                envelope_path.write_text(json.dumps(uploaded, ensure_ascii=False), encoding='utf-8')
                upload_files.extend(['--file-from', str(envelope_path)])

            directive = (
                f'用 {model} 生成恰好 {duration} 秒、{resolution}、9:16、带同步声音的单条最终视频。'
                '这是用户已审核的单条付费生成请求；不改写下方导演提示词，'
                '不拆成多镜头，不另行生成人物、场景或游戏截图。'
                '上传文件按顺序分别是唯一人物身份、场景环境，以及可选的手机唯一游戏画面。\n\n'
                + prompt
            )
            finished, stderr = self._call([
                'run', str(project_id), '--content', directive,
                *upload_files, '--timeout', '18000',
            ], timeout=18100)

        data = self._data(finished)
        common = {
            'project_id': project_id,
            'project_url': data.get('project_url') or project.get('project_url'),
            'stream_chat_id': data.get('stream_chat_id'),
        }
        pending = [item for item in data.get('pending_actions', []) if item.get('blocking')]
        if pending:
            return {**common, 'status': 'awaiting_user', 'pending_actions': pending}
        if not data.get('terminal') or data.get('status') not in ('success', 'completed'):
            return {**common, 'status': 'submission_unknown'}
        videos = self._ready_videos(stderr)
        if not videos:
            raise FlovaCLIError('Flova 任务已结束，但没有收到可播放的本地视频。请在 Flova 项目中查看结果。')
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(videos[-1], target)
        return {**common, 'status': 'succeeded', 'output_path': str(target)}


def find_flova_cli(configured='flova'):
    direct = Path(configured).expanduser()
    if direct.is_file():
        return str(direct)
    found = shutil.which(configured)
    if found:
        return found
    candidates = [Path.home() / '.local/bin/flova', Path.home() / '.local/bin/flova.exe']
    return str(next((path for path in candidates if path.is_file()), configured))
