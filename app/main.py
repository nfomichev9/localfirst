import asyncio
import json
import time
from contextlib import asynccontextmanager, aclosing
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, SecretStr

from .ollama_adapter import OllamaAdapter, OllamaError, count_metric, duration_metric
from .storage import Storage
from .lab_storage import LabStorage
from .lab import router as lab_router
from .models import DEFAULT_MODEL, MODEL_LABELS, preferred_model
from .telemetry import Telemetry
from .routing import Mode, Routing, SettingsInput, bounded, RATES
from .openai_adapter import stream_openai, check_connection
from .credentials import CredentialError
from .handoff import prepare, prepare_manual, payload
from .documents import (DocumentError, MAX_FILE_BYTES, filename_for_upload,
                        read_pdf, pdf_context)
from .web_search import WebSearchError, search_query, search_web, web_context

ROOT = Path(__file__).resolve().parent
GENERATION_TIMEOUT_SECONDS = 180


class FeedbackInput(BaseModel):
    value: int | None = Field(default=None, ge=-1, le=1, strict=True)


class ModelInput(BaseModel):
    expected_mode: Mode | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)


class ChatInput(ModelInput):
    content: str = Field(min_length=1, max_length=16000)
    document_id: str | None = Field(default=None, min_length=1, max_length=36)
    web_search: bool = Field(default=False, strict=True)



class BriefInput(BaseModel):
    summary: str = Field(max_length=8192)
    facts_and_constraints: str = Field(max_length=8192)
    task: str = Field(max_length=8192)
    latest_request: str = Field(max_length=8192)
    source_excerpts: str = Field(max_length=8192)


class HandoffInput(BriefInput):
    token: str = Field(min_length=1, max_length=40)


class ConnectionInput(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    key: SecretStr | None = None


def create_app(db_path=None, adapter=None, secret_store=None, env_file=None, web_searcher=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.storage = Storage(db_path or ROOT.parent / 'data' / 'localfirst.sqlite3')
        # Isolated/custom databases never inherit the developer's project file.
        config_file = env_file if env_file is not None else (ROOT.parent / '.env' if db_path is None else None)
        app.state.routing = Routing(app.state.storage, secret_store, config_file)
        app.state.telemetry = Telemetry(app.state.storage)
        app.state.lab = LabStorage(app.state.storage)
        app.state.adapter = adapter or OllamaAdapter()
        app.state.web_searcher = web_searcher or search_web
        app.state.busy = False
        app.state.pdf_busy = False
        try:
            yield
        finally:
            await app.state.adapter.close()

    app = FastAPI(title='LocalFirst', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path == '/api/provider/connection':
            return JSONResponse({'detail':'Enter an API key and choose a supported cloud model.'}, status_code=422)
        return await request_validation_exception_handler(request, exc)

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        # Reject cross-origin writes without adding authentication to this local app.
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, status_code=403)
        response = await call_next(request)
        if request.url.path in ('/', '/settings', '/static/settings.html',
                                '/static/settings.css', '/static/settings.js',
                                '/static/app.js', '/static/chat.css', '/static/markdown.js'):
            response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'"
        return response

    @app.get('/settings')
    async def settings_page():
        return FileResponse(ROOT / 'static' / 'settings.html')

    @app.get('/api/settings')
    async def settings():
        return app.state.routing.settings()

    @app.get('/api/provider/connection')
    async def connection():
        return app.state.routing.connection()

    @app.put('/api/provider/connection')
    async def connect_provider(body: ConnectionInput):
        if app.state.busy or app.state.pdf_busy:
            raise HTTPException(409, 'Wait for the current response or PDF to finish before changing the connection.')
        if body.model not in RATES:
            raise HTTPException(422, 'Choose a supported cloud model.')
        routing = app.state.routing
        key = (body.key.get_secret_value().strip() if body.key else '') or routing.key
        if not key:
            raise HTTPException(422, 'Enter an OpenAI API key.')
        if not 8 <= len(key) <= 512 or not key.isascii() or any(c.isspace() for c in key):
            raise HTTPException(422, 'The API key contains unexpected characters. Copy it again from OpenAI.')
        app.state.busy = True
        try:
            await check_connection(key, body.model)
            await asyncio.to_thread(routing.connect, body.model, key)
            return routing.settings()
        except (OllamaError, CredentialError) as exc:
            raise HTTPException(422, str(exc)) from None
        finally:
            app.state.busy = False

    @app.put('/api/settings')
    async def save_settings(body: SettingsInput):
        routing = app.state.routing
        if body.mode != 'always_local' and (not routing.ready or not body.daily_limit_cents):
            raise HTTPException(422, 'Set OPENAI_API_KEY and OPENAI_MODEL (gpt-6-luna) on the server and enter a positive daily limit.')
        if body.mode in ('automatic_handoff', 'always_frontier') and not body.acknowledged:
            raise HTTPException(422, 'Acknowledge that chat content may be sent to OpenAI.')
        routing.save(body)
        return routing.settings()

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

    @app.post('/api/conversations/{cid}/documents', status_code=201)
    async def upload_pdf(cid: str, request: Request, filename: str = Query(max_length=500)):
        get_conversation(cid)
        if app.state.busy or app.state.pdf_busy:
            raise HTTPException(409, 'Wait for the current response or PDF to finish.')
        app.state.pdf_busy = True
        try:
            name = filename_for_upload(filename)
            data = bytearray()
            async for part in request.stream():
                if len(data) + len(part) > MAX_FILE_BYTES:
                    raise HTTPException(413, 'Choose a PDF smaller than 10 MB.')
                data.extend(part)
            async def disconnected():
                while (await request.receive())['type'] != 'http.disconnect':
                    pass
            reading = asyncio.create_task(read_pdf(bytes(data)))
            disconnect = asyncio.create_task(disconnected())
            try:
                await asyncio.wait((reading, disconnect), return_when=asyncio.FIRST_COMPLETED)
                if disconnect.done() and not reading.done():
                    raise HTTPException(499, 'PDF reading stopped.')
                extracted = reading.result()
            finally:
                for task in (reading, disconnect):
                    task.cancel()
                await asyncio.gather(reading, disconnect, return_exceptions=True)
            return app.state.storage.save_document(cid, name, extracted)
        except DocumentError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            app.state.pdf_busy = False

    @app.delete('/api/conversations/{cid}/documents/{document_id}', status_code=204)
    async def discard_pdf(cid: str, document_id: str):
        if not app.state.storage.discard_document(cid, document_id):
            raise HTTPException(409, 'Only an unsent PDF attachment can be removed.')

    @app.get('/api/usage')
    async def usage(days: int = Query(default=30, ge=0, le=3650), model: str | None = None):
        result = app.state.telemetry.analytics(days, model or None)
        return dict(result, cloud_budget=app.state.routing.daily_usage())

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
        return await generate(cid, body.model, content=body.content, expected_mode=body.expected_mode,
                              document_id=body.document_id, use_web=body.web_search)

    @app.post('/api/conversations/{cid}/messages/{mid}/retry')
    async def retry_chat(cid: str, mid: int, body: ModelInput):
        return await generate(cid, body.model, retry_of=mid, expected_mode=body.expected_mode)

    def require_cloud(settings):
        if not app.state.routing.ready:
            raise HTTPException(503, 'Connect your OpenAI API key in Settings to continue.',
                                headers={'X-LocalFirst-Action':'connect-openai'})
        if not settings['daily_limit_cents']:
            raise HTTPException(409, 'Set a positive daily cloud limit in Settings to continue.',
                                headers={'X-LocalFirst-Action':'set-cloud-limit'})

    @app.post('/api/conversations/{cid}/messages/{mid}/handoff/preview')
    async def preview_handoff(cid: str, mid: int, request: Request):
        storage = app.state.storage
        if storage.web_coverage(mid):
            raise HTTPException(409, 'Web search answers stay local. Start an ordinary turn for cloud help.')
        if storage.document(cid):
            raise HTTPException(409, 'PDF conversations stay local. Start a new chat for cloud help.')
        routing = app.state.routing
        settings = routing.settings()
        if settings['mode'] != 'manual_handoff':
            raise HTTPException(409, 'Select Manual handoff in Settings.')
        require_cloud(settings)
        saved = storage.handoff_input(cid, mid)
        if not saved:
            raise HTTPException(409, 'This reply is no longer eligible for a handoff.')
        if app.state.busy:
            raise HTTPException(409, 'A response is already in progress.')
        app.state.busy = True
        try:
            async def until_disconnect():
                while (await request.receive())['type'] != 'http.disconnect':
                    pass

            preparation = asyncio.create_task(prepare_manual(app.state.adapter, saved[2], saved[0], saved[1]))
            disconnect = asyncio.create_task(until_disconnect())
            try:
                await asyncio.wait((preparation, disconnect), return_when=asyncio.FIRST_COMPLETED)
                if disconnect.done():
                    raise HTTPException(499, 'Brief preparation stopped.')
                reason, brief, preparation_note = preparation.result()
            finally:
                for task in (preparation, disconnect):
                    task.cancel()
                await asyncio.gather(preparation, disconnect, return_exceptions=True)
            token = storage.save_preview(mid, reason)
            fixed = routing.estimate([{'role': 'user', 'content': ''}])
            input_rate = routing.charge(1, 0)
            return {'token': token, 'brief': brief, 'reason': reason,
                    'fixed_nanodollars': fixed, 'input_nanodollars_per_byte': input_rate,
                    'preparation_note':preparation_note}
        except (OllamaError, TimeoutError, ValueError, TypeError) as exc:
            raise HTTPException(422, 'Ollama could not prepare a usable handoff brief.') from exc
        finally:
            app.state.busy = False

    @app.post('/api/conversations/{cid}/messages/{mid}/handoff')
    async def manual_handoff(cid: str, mid: int, body: HandoffInput):
        storage = app.state.storage
        if storage.web_coverage(mid):
            raise HTTPException(409, 'Web search answers stay local. Start an ordinary turn for cloud help.')
        if storage.document(cid):
            raise HTTPException(409, 'PDF conversations stay local. Start a new chat for cloud help.')
        settings = app.state.routing.settings()
        reason = storage.preview_reason(mid, body.token)
        if settings['mode'] != 'manual_handoff' or not reason or not storage.handoff_input(cid, mid):
            raise HTTPException(409, 'Prepare a fresh preview in Manual handoff mode.')
        try:
            outbound = payload(body.model_dump(exclude={'token'}))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return await generate(cid, None, handoff_of=mid, handoff=outbound, reason=reason)

    def begin_frontier(cid, outbound, settings, *, omitted=0, retry_of=None,
                       handoff_of=None, reason=None, original_content=None):
        routing = app.state.routing
        require_cloud(settings)
        if handoff_of is None:
            reason = 'Always frontier selected in Settings.'
        rid = app.state.telemetry.start(cid, routing.model, 'openai', 'cloud', routing_mode=settings['mode'])
        try:
            if not routing.reserve(rid, outbound, settings['daily_limit_cents']):
                raise HTTPException(409, 'Daily cloud spending limit reached. Change the limit or mode in Settings.')
            mid = app.state.storage.begin_chat(cid, rid, routing.model, outbound, omitted, retry_of,
                                               mode=settings['mode'], handoff_of=handoff_of,
                                               reason=reason, original_content=original_content)
        except Exception:
            app.state.telemetry.finish(rid, 'error', 0)
            raise
        return rid, mid

    async def generate(cid, model, *, content=None, retry_of=None, handoff_of=None,
                       handoff=None, reason=None, expected_mode=None, document_id=None, use_web=False):
        get_conversation(cid)
        if app.state.busy or app.state.pdf_busy:
            raise HTTPException(409, 'A response is already in progress. Stop it or wait before sending again.')
        routing = app.state.routing
        settings = routing.settings()
        if expected_mode is not None and expected_mode != settings['mode']:
            raise HTTPException(409, 'Routing changed in Settings. Refresh chat before sending.')
        document = app.state.storage.document(cid, document_id)
        if document_id and document is None:
            raise HTTPException(404, 'PDF attachment not found in this conversation.')
        coverage = None
        web_info = app.state.storage.web_coverage(retry_of) if retry_of else None
        if use_web or web_info:
            if document:
                raise HTTPException(409, 'PDF conversations stay offline. Start a new chat to search the web.')
            try:
                web_info = web_info or {'query':search_query(content), 'provider':'DuckDuckGo',
                                        'retrieved_at':None, 'sources':[]}
            except WebSearchError as exc:
                raise HTTPException(422, str(exc)) from exc
            settings = dict(settings, mode='always_local')
        if document:
            if handoff is not None:
                raise HTTPException(409, 'PDF conversations stay local. Start a new chat for cloud help.')
            settings = dict(settings, mode='always_local')
        cloud = handoff is not None or settings['mode'] == 'always_frontier'
        app.state.busy = True
        started = time.perf_counter()
        rid = None
        try:
            if handoff is not None:
                input_messages, omitted = handoff, 0
            elif retry_of is not None:
                saved = app.state.storage.retry_input(cid, retry_of)
                if saved is None:
                    raise HTTPException(409, 'Only the latest stopped or failed reply can be retried.')
                input_messages, omitted = saved
                coverage = app.state.storage.document_coverage(retry_of)
            else:
                history, omitted = app.state.storage.context(cid)
                if document:
                    input_messages, extra_omitted, coverage = pdf_context(document, history, content)
                    omitted += extra_omitted
                else:
                    input_messages = history + [{'role': 'user', 'content': content}]
            if cloud:
                selected_model = routing.model
                outbound = bounded(input_messages) if handoff is None else handoff
                omitted += len(input_messages) - len(outbound)
                rid, mid = begin_frontier(cid, outbound, settings, omitted=omitted, retry_of=retry_of,
                                          handoff_of=handoff_of, reason=reason, original_content=content)
            else:
                if retry_of is not None and model is None:
                    raise HTTPException(422, 'Choose an installed model to retry.')
                rid = app.state.telemetry.start(cid, model or DEFAULT_MODEL, routing_mode=settings['mode'])
                names = await app.state.adapter.models()
                selected_model = model or preferred_model(names)
                if selected_model not in names:
                    raise HTTPException(400, 'Select an installed model. Refresh the model list.')
                outbound = input_messages
                mid = app.state.storage.begin_chat(cid, rid, selected_model, outbound, omitted, retry_of,
                                                   mode=settings['mode'], document_id=document_id,
                                                   document_context=coverage, web_context=web_info)
        except BaseException as exc:
            if rid:
                app.state.telemetry.finish(rid, 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'error', (time.perf_counter()-started)*1000)
            app.state.busy = False
            if isinstance(exc, DocumentError):
                raise HTTPException(422, str(exc)) from exc
            raise

        async def events():
            try:
                result = {}
                async with aclosing(phase(rid, mid, selected_model, outbound, settings, cloud, started,
                                          omitted, result, handoff_of, reason)) as stream:
                    async for packet in stream:
                        yield packet
                if cloud or settings['mode'] != 'automatic_handoff' or not result:
                    return
                yield event('preparing')
                try:
                    disposition, why, brief = await prepare(app.state.adapter, result['model'],
                                                           input_messages, result['answer'], True)
                    if disposition == 'answered':
                        return
                    if disposition == 'needs_user_input':
                        yield event('handoff_status', message=why)
                        return
                    continuation = payload(brief)
                    cloud_rid, cloud_mid = begin_frontier(cid, continuation, settings,
                                                          handoff_of=mid, reason=why)
                except HTTPException as exc:
                    yield event('handoff_status', message=exc.detail)
                    return
                except (OllamaError, TimeoutError, ValueError, TypeError):
                    yield event('handoff_status', message='Ollama could not prepare a usable handoff brief.')
                    return
                async with aclosing(phase(cloud_rid, cloud_mid, routing.model, continuation, settings,
                                          True, time.perf_counter(), 0, {}, mid, why)) as stream:
                    async for packet in stream:
                        yield packet
            finally:
                app.state.busy = False

        return StreamingResponse(events(), media_type='application/x-ndjson',
            headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    def event(kind, **data):
        return json.dumps({'type': kind, **data}) + '\n'

    async def phase(rid, mid, selected_model, outbound, settings, cloud, started, omitted,
                    result, handoff_of, reason):
        routing = app.state.routing
        provider = 'openai' if cloud else 'ollama'
        spend = None
        chunks = []
        status, error = 'stopped', None
        actual_model = selected_model
        prompt_tokens = output_tokens = ttft_ms = generation_ms = None
        latency = None
        try:
            yield event('start', request_id=rid, message_id=mid, omitted_messages=omitted,
                        context_messages=len(outbound), model=selected_model, provider=provider, routing_mode=settings['mode'],
                        handoff_of=handoff_of, route_reason=reason,
                        handoff_brief=outbound[0]['content'] if handoff_of else None,
                        document_context=app.state.storage.document_coverage(mid),
                        web_context=app.state.storage.web_coverage(mid))
            async with asyncio.timeout(GENERATION_TIMEOUT_SECONDS):
                search = app.state.storage.web_coverage(mid)
                if search:
                    if not search['sources']:
                        yield event('web_status', message='Searching the web…')
                        search = await app.state.web_searcher(search['query'])
                        outbound, extra_omitted = web_context(outbound, search)
                        omitted += extra_omitted
                        app.state.storage.save_web_input(mid, outbound, omitted, search)
                    yield event('web_sources', web_context=search, context_messages=len(outbound),
                                omitted_messages=omitted)
                packets = stream_openai(routing, outbound) if cloud else app.state.adapter.stream(selected_model, outbound)
                async with aclosing(packets) as stream:
                    async for packet in stream:
                        actual_model = packet.get('model') or actual_model
                        content = packet.get('message', {}).get('content', '')
                        if content is None and cloud:
                            content = ''
                        if not isinstance(content, str):
                            raise OllamaError(f'{provider} returned invalid message content.')
                        if content:
                            if ttft_ms is None:
                                ttft_ms = (time.perf_counter() - started) * 1000
                            chunks.append(content)
                            yield event('delta', content=content)
                        if packet.get('done'):
                            prompt_tokens = count_metric(packet.get('prompt_eval_count'))
                            output_tokens = count_metric(packet.get('eval_count'))
                            generation_ms = duration_metric(packet.get('eval_duration'))
                            if cloud:
                                spend = routing.reconcile(rid, prompt_tokens, output_tokens)
                            if not ''.join(chunks).strip():
                                raise OllamaError(f'{provider} returned an empty response. Try another prompt.')
                            status = 'complete'
                            break
                    else:
                        raise OllamaError(f'{provider} ended the stream before completing the response.')
            latency = (time.perf_counter() - started) * 1000
            app.state.storage.finish(mid, ''.join(chunks), status, actual_model, latency, prompt_tokens, output_tokens)
            telemetry = app.state.telemetry.finish(rid, 'success', latency, actual_model, ttft_ms, prompt_tokens, output_tokens, generation_ms, spend)
            result.update(model=actual_model, answer=''.join(chunks))
            yield event('done', telemetry=telemetry, model=actual_model, latency_ms=latency, prompt_tokens=prompt_tokens,
                        output_tokens=output_tokens, provider='openai' if cloud else 'local', external_api_spend=spend if cloud else 0)
        except (OllamaError, WebSearchError, TimeoutError) as exc:
            status = 'error'
            error = str(exc) if isinstance(exc, (OllamaError, WebSearchError)) else 'Response exceeded the 180-second limit. Try a shorter prompt.'
            yield event('error', message=error)
        except asyncio.CancelledError:
            error = 'Response stopped before completion.'
            raise
        except Exception:
            status, error = 'error', 'Response failed unexpectedly. Please retry.'
            yield event('error', message=error)
        finally:
            if latency is None:
                latency = (time.perf_counter()-started)*1000
            app.state.telemetry.finish(rid, {'complete':'success','stopped':'cancelled','error':'error'}[status],
                latency, actual_model, ttft_ms, prompt_tokens, output_tokens, generation_ms, spend)
            app.state.storage.finish(mid, ''.join(chunks), status, actual_model,
                latency, prompt_tokens, output_tokens, error)

    @app.exception_handler(OllamaError)
    async def ollama_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=503)

    app.include_router(lab_router)

    @app.get('/lab')
    async def lab_page():
        return FileResponse(ROOT / 'static' / 'lab.html')

    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    @app.get('/usage')
    async def usage_page():
        return FileResponse(ROOT / 'static' / 'usage.html')

    @app.get('/')
    async def index():
        return FileResponse(ROOT / 'static' / 'index.html')

    return app


app = create_app()
