import asyncio
import json
import time
from contextlib import asynccontextmanager, aclosing
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from .ollama_adapter import OllamaAdapter, OllamaError, count_metric, duration_metric
from .storage import Storage
from .models import DEFAULT_MODEL, MODEL_LABELS, preferred_model
from .telemetry import Telemetry

ROOT = Path(__file__).resolve().parent
GENERATION_TIMEOUT_SECONDS = 180


class FeedbackInput(BaseModel):
    value: int | None = Field(default=None, ge=-1, le=1, strict=True)


class ChatInput(BaseModel):
    content: str = Field(min_length=1, max_length=16000)
    model: str | None = Field(default=None, min_length=1, max_length=200)


def create_app(db_path=None, adapter=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.storage = Storage(db_path or ROOT.parent / 'data' / 'localfirst.sqlite3')
        app.state.telemetry = Telemetry(app.state.storage)
        app.state.adapter = adapter or OllamaAdapter()
        app.state.busy = False
        try:
            yield
        finally:
            await app.state.adapter.close()

    app = FastAPI(title='LocalFirst', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        # Reject cross-origin writes without adding authentication to this local app.
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'"
        return response

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'provider': 'local'}

    @app.get('/api/models')
    async def models():
        try:
            names = await app.state.adapter.models()
            return {'models': names, 'default': preferred_model(names), 'labels': MODEL_LABELS, 'provider': 'local'}
        except OllamaError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get('/api/conversations')
    async def conversations():
        return app.state.storage.list()

    @app.post('/api/conversations', status_code=201)
    async def new_conversation():
        return app.state.storage.create()

    def get_conversation(cid):
        conversation = app.state.storage.conversation(cid)
        if conversation is None:
            raise HTTPException(404, 'Conversation not found.')
        return conversation

    @app.get('/api/conversations/{cid}')
    async def conversation(cid: str):
        return get_conversation(cid)

    @app.get('/api/usage')
    async def usage(days: int = Query(default=30, ge=0, le=3650), model: str | None = None):
        return app.state.telemetry.analytics(days, model or None)

    @app.put('/api/inference/{rid}/feedback')
    async def feedback(rid: str, body: FeedbackInput):
        if body.value == 0:
            raise HTTPException(422, 'Feedback must be -1, 1, or null.')
        if not app.state.telemetry.feedback(rid, body.value):
            raise HTTPException(404, 'Response not found.')
        return {'feedback': body.value}

    @app.post('/api/conversations/{cid}/chat')
    async def chat(cid: str, body: ChatInput):
        if not body.content.strip():
            raise HTTPException(422, 'Message cannot be blank.')
        get_conversation(cid)
        if app.state.busy:
            raise HTTPException(409, 'A response is already in progress. Stop it or wait before sending again.')
        app.state.busy = True
        started = time.perf_counter()
        rid = None
        try:
            rid = app.state.telemetry.start(cid, body.model or DEFAULT_MODEL)
            names = await app.state.adapter.models()
            selected_model = body.model or preferred_model(names)
            if selected_model not in names:
                raise HTTPException(400, 'Select an installed model. Refresh the model list.')
            history, omitted = app.state.storage.context(cid)
            app.state.storage.add(cid, 'user', body.content)
            mid = app.state.storage.add(cid, 'assistant', '', selected_model, 'streaming')
            app.state.telemetry.attach(rid, mid)
        except BaseException as exc:
            if rid:
                app.state.telemetry.finish(rid, 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'error', (time.perf_counter()-started)*1000)
            app.state.busy = False
            raise

        async def events():
            chunks = []
            status, error = 'stopped', None
            actual_model = selected_model
            prompt_tokens = output_tokens = ttft_ms = generation_ms = None
            latency = None
            def event(kind, **data):
                return json.dumps({'type': kind, **data}) + '\n'
            try:
                yield event('start', request_id=rid, message_id=mid, omitted_messages=omitted, model=selected_model)
                async with asyncio.timeout(GENERATION_TIMEOUT_SECONDS):
                    async with aclosing(app.state.adapter.stream(selected_model, history + [{'role': 'user', 'content': body.content}])) as stream:
                        async for packet in stream:
                            actual_model = packet.get('model') or actual_model
                            content = packet.get('message', {}).get('content', '')
                            if not isinstance(content, str):
                                raise OllamaError('Ollama returned invalid message content.')
                            if content:
                                if ttft_ms is None:
                                    ttft_ms = (time.perf_counter() - started) * 1000
                                chunks.append(content)
                                yield event('delta', content=content)
                            if packet.get('done'):
                                prompt_tokens = count_metric(packet.get('prompt_eval_count'))
                                output_tokens = count_metric(packet.get('eval_count'))
                                generation_ms = duration_metric(packet.get('eval_duration'))
                                if not ''.join(chunks).strip():
                                    raise OllamaError('Ollama returned an empty response. Try another prompt or installed model.')
                                status = 'complete'
                                break
                        else:
                            raise OllamaError('Ollama ended the stream before completing the response.')
                latency = (time.perf_counter() - started) * 1000
                app.state.storage.finish(mid, ''.join(chunks), status, actual_model, latency, prompt_tokens, output_tokens)
                telemetry = app.state.telemetry.finish(rid, 'success', latency, actual_model, ttft_ms, prompt_tokens, output_tokens, generation_ms)
                yield event('done', telemetry=telemetry, model=actual_model, latency_ms=latency, prompt_tokens=prompt_tokens,
                            output_tokens=output_tokens, provider='local', external_api_spend=0)
            except (OllamaError, TimeoutError) as exc:
                status = 'error'
                error = str(exc) if isinstance(exc, OllamaError) else 'Response exceeded the 180-second limit. Try a shorter prompt.'
                yield event('error', message=error)
            except asyncio.CancelledError:
                error = 'Response stopped before completion.'
                raise
            except Exception:
                status, error = 'error', 'Response failed unexpectedly. Please retry.'
                yield event('error', message=error)
            finally:
                try:
                    if latency is None:
                        latency = (time.perf_counter()-started)*1000
                    app.state.telemetry.finish(rid, {'complete':'success','stopped':'cancelled','error':'error'}[status],
                        latency, actual_model, ttft_ms, prompt_tokens, output_tokens, generation_ms)
                    app.state.storage.finish(mid, ''.join(chunks), status, actual_model,
                        latency, prompt_tokens, output_tokens, error)
                finally:
                    app.state.busy = False

        return StreamingResponse(events(), media_type='application/x-ndjson',
            headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    @app.exception_handler(OllamaError)
    async def ollama_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=503)

    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    @app.get('/usage')
    async def usage_page():
        return FileResponse(ROOT / 'static' / 'usage.html')

    @app.get('/')
    async def index():
        return FileResponse(ROOT / 'static' / 'index.html')

    return app


app = create_app()
