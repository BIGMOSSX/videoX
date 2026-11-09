import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, BackgroundTasks, File, Form, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from .assets import ingest_image, public_asset, seed_builtin_assets, MAX_BYTES
from .config import Settings, ConfigurationError
from .models import BatchBrief, BatchGenerate, Brief, SettingsPatch, SceneSearch, SceneImport, LanguageCheckRequest
from .store import Store
from .service import StudioService
from .pinterest import search_board, import_pin

ROOT = Path(__file__).resolve().parent.parent


def public_job(job):
    return {k: v for k, v in job.items() if k != 'output_path'}


def create_app(data_dir=None, builtin_dir=None):
    store = Store(Path(data_dir or os.getenv('STUDIO_DATA_DIR') or ROOT / '.studio'))
    library = builtin_dir if builtin_dir is not None else (ROOT / 'studio/builtin' if data_dir is None else None)
    if library is not None:
        seed_builtin_assets(store, Path(library))
    settings = Settings(store)
    service = StudioService(store, settings)

    async def poll():
        while True:
            await asyncio.sleep(10)
            for job in store.active_jobs():
                if job.get('task_id') and job['status'] in ('queued', 'running', 'submission_unknown'):
                    await asyncio.to_thread(service.refresh, job['id'])

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        task = asyncio.create_task(poll())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title='videoX Brazil UGC Studio', lifespan=lifespan)
    app.state.store, app.state.settings, app.state.service = store, settings, service

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        origin = request.headers.get('origin')
        allowed = {'http://127.0.0.1:8787', 'http://localhost:8787', 'http://127.0.0.1:5173', 'http://localhost:5173'}
        if origin and origin not in allowed:
            return JSONResponse({'detail': '仅允许本地工作室页面访问。'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': '禁止跨站访问。'}, status_code=403)
        length = request.headers.get('content-length')
        if length:
            try:
                if int(length) > MAX_BYTES + 100_000:
                    return JSONResponse({'detail': '上传内容超过 10 MB。'}, status_code=413)
            except ValueError:
                return JSONResponse({'detail': 'Content-Length 格式无效。'}, status_code=400)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'no-cache'
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1'])

    @app.exception_handler(ConfigurationError)
    async def config_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Validation responses must not echo input API keys back into the UI/logs.
        details = '; '.join(f"{'.'.join(map(str,e['loc']))}: {e['msg']}" for e in exc.errors())
        return JSONResponse({'detail': details}, status_code=422)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({'detail': service.redact(str(exc))}, status_code=422)

    @app.exception_handler(KeyError)
    async def key_error(request, exc):
        return JSONResponse({'detail': str(exc.args[0])}, status_code=404)

    @app.get('/api/health')
    def health():
        return {'ok': True}

    @app.get('/api/settings')
    def get_settings():
        return settings.public()

    @app.patch('/api/settings')
    def update_settings(patch: SettingsPatch):
        return settings.update(patch.model_dump(exclude_none=True))

    @app.get('/api/assets')
    def assets(role: str | None = None):
        return [public_asset(a) for a in store.assets(role)]

    @app.post('/api/assets')
    async def upload(file: UploadFile = File(...), role: str = Form(...)):
        content = await file.read(MAX_BYTES + 1)
        await file.close()
        asset = await asyncio.to_thread(ingest_image, store, content, role, file.filename or 'image')
        return public_asset(asset)

    @app.post('/api/assets/{aid}/default')
    def set_default(aid: str):
        return public_asset(store.set_default(aid))

    @app.get('/api/media/{aid}')
    def media(aid: str):
        return FileResponse(store.get_asset(aid)['path'], media_type='image/webp')

    @app.post('/api/scenes/search')
    def scene_search(query: SceneSearch):
        return search_board(settings, query.query, query.bookmark, query.language)

    @app.post('/api/scenes/import')
    def scene_import(data: SceneImport):
        return public_asset(import_pin(settings, store, data.pin_id))

    @app.post('/api/language-check')
    def language_check(data: LanguageCheckRequest):
        from .language_check import check_dialogue
        return check_dialogue(data.language, data.dialogue_lines, settings)

    @app.post('/api/drafts')
    def draft(brief: Brief, background: BackgroundTasks):
        service.resolve_assets(brief)
        settings.require('llm')
        job = store.create_job(brief.model_dump())
        background.add_task(service.draft, job['id'])
        return public_job(job)

    @app.post('/api/drafts/batch')
    def draft_batch(batch: BatchBrief, background: BackgroundTasks):
        settings.require('llm')
        briefs = batch.expand()
        for brief in briefs:
            service.resolve_assets(brief)
        jobs = [store.create_job(brief.model_dump()) for brief in briefs]
        for job in jobs:
            background.add_task(service.draft, job['id'])
        return [public_job(job) for job in jobs]

    @app.get('/api/jobs')
    def jobs():
        return [public_job(j) for j in store.jobs()]

    @app.get('/api/jobs/{jid}')
    def job(jid: str):
        return public_job(store.get_job(jid))

    @app.post('/api/jobs/{jid}/generate')
    def generate(jid: str, background: BackgroundTasks):
        existing = store.get_job(jid)
        if existing['status'] in ('submitting', 'queued', 'running', 'succeeded'):
            return public_job(existing)
        if existing['status'] != 'draft_ready':
            raise ValueError('当前任务不能再次提交。请先查看状态或重新创建策划。')
        settings.require(settings.get()['video_provider'])
        if store.claim_submission(jid):
            background.add_task(service.submit, jid)
        return public_job(store.get_job(jid))

    @app.post('/api/jobs/generate-batch')
    def generate_batch(data: BatchGenerate, background: BackgroundTasks):
        settings.require(settings.get()['video_provider'])
        if not store.claim_submissions(data.job_ids):
            raise ValueError('整批任务必须全部处于“草稿待审核”状态，请刷新后重试。')
        for jid in data.job_ids:
            background.add_task(service.submit, jid)
        return [public_job(store.get_job(jid)) for jid in data.job_ids]

    @app.post('/api/jobs/{jid}/refresh')
    def refresh(jid: str):
        return public_job(service.refresh(jid))

    @app.get('/api/jobs/{jid}/packet')
    def packet(jid: str):
        return JSONResponse(service.packet(jid), headers={'Content-Disposition': f'attachment; filename="videox-{jid}.json"'})

    @app.get('/api/videos/{jid}')
    def video(jid: str):
        job = store.get_job(jid)
        if job['status'] != 'succeeded' or not job.get('output_path'):
            raise ValueError('视频尚未生成完成。')
        return FileResponse(job['output_path'], media_type='video/mp4', filename=f'videox-{jid}.mp4', content_disposition_type='inline')

    dist = ROOT / 'studio-web/dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='studio')
    return app
