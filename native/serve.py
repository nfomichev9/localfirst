"""Serve LocalFirst chat and own one resident llama.cpp process."""

import argparse
import asyncio
import json
import os
import secrets
import shutil
import socket
import tempfile
import time
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.search_route import router as search_router

HOST = '127.0.0.1'
ROOT = Path(__file__).resolve().parents[1]
NATIVE_ASSETS = ROOT / 'dist' / 'native'
CONFIG = ROOT / 'data' / 'native-model.json'
MODEL = 'gemma-270m'
GEMMA_270M_PARAMS = 268_098_176


class Message(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=3200)


class Generation(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=21)


class FolderInput(BaseModel):
    folder: str = Field(min_length=1, max_length=4096)


class ModelInput(FolderInput):
    filename: str = Field(min_length=1, max_length=255)


def scan_folder(folder):
    folder = folder.expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Choose a folder containing Gemma 3 270M Instruct in GGUF format.')
    return folder, sorted(path for path in folder.iterdir() if path.suffix.lower() == '.gguf' and path.is_file())


def find_model(folder, filename=None):
    folder, candidates = scan_folder(folder)
    if filename is not None:
        candidates = [path for path in candidates if path.name == filename]
    if not candidates:
        raise ValueError(f'No matching GGUF file in {folder}.')
    if len(candidates) > 1:
        raise ValueError('Choose a GGUF with --model: ' + ', '.join(path.name for path in candidates))
    model = candidates[0]
    with model.open('rb') as source:
        if source.read(4) != b'GGUF':
            raise ValueError(f'{model.name} is not a GGUF file.')
    return model


def private_port(ui_port):
    while True:
        with socket.socket() as listener:
            listener.bind((HOST, 0))
            port = listener.getsockname()[1]
        if port != ui_port:
            return port


def event(kind, **values):
    return json.dumps({'type': kind, **values}) + '\n'


@dataclass
class Engine:
    model: Path
    process: asyncio.subprocess.Process
    client: httpx.AsyncClient
    load_ms: float


@asynccontextmanager
async def launch_engine(binary, model, ui_port, threads):
    port = private_port(ui_port)
    api_key = secrets.token_hex(32)
    env = {key: value for key, value in os.environ.items() if not key.startswith(('LLAMA_', 'GGML_'))}
    env['LLAMA_API_KEY'] = api_key
    command = [binary, '--model', model, '--alias', MODEL, '--host', HOST, '--port', str(port),
               '--ctx-size', '4096', '--parallel', '1', '--n-gpu-layers', '0', '--no-mmproj',
               '--no-ui', '--no-slots', '--no-cache-prompt', '--log-verbosity', '2']
    if threads is not None:
        command.extend(('--threads', str(threads)))
    print(f'Loading {model.name} with llama.cpp…', flush=True)
    with tempfile.TemporaryFile() as log:
        started = time.perf_counter()
        process = await asyncio.create_subprocess_exec(*command, env=env, stdin=asyncio.subprocess.DEVNULL,
                                                       stdout=log, stderr=log)
        try:
            async with httpx.AsyncClient(base_url=f'http://{HOST}:{port}', trust_env=False,
                                         headers={'Authorization': f'Bearer {api_key}'},
                                         timeout=httpx.Timeout(60, connect=2)) as client:
                try:
                    async with asyncio.timeout(90):
                        while process.returncode is None:
                            try:
                                response = await client.get('/health', timeout=0.5)
                                if response.is_success:
                                    load_ms = (time.perf_counter() - started) * 1000
                                    break
                            except httpx.RequestError:
                                pass
                            await asyncio.sleep(0.025)
                        else:
                            raise RuntimeError(f'llama.cpp exited with code {process.returncode}.')
                        info = await client.get('/v1/models', timeout=2)
                        info.raise_for_status()
                        model_info = info.json()['data'][0]['meta']
                        if model_info['n_params'] != GEMMA_270M_PARAMS:
                            raise RuntimeError('Choose a Gemma 3 270M Instruct GGUF for native chat.')
                except (TimeoutError, httpx.HTTPError, RuntimeError, KeyError, ValueError, IndexError) as error:
                    log.seek(max(0, log.seek(0, os.SEEK_END) - 2500))
                    detail = log.read().decode(errors='replace').strip()
                    raise RuntimeError(f'Could not load the local model. {error}\n{detail}'.rstrip()) from error
                print(f'{model.name} ready in {load_ms:.0f} ms.', flush=True)
                yield Engine(model, process, client, load_ms)
        finally:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except TimeoutError:
                    with suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()


def save_model(config, model):
    config.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=config.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump({'folder': str(model.parent), 'filename': model.name}, file)
            file.close()
            temporary.replace(config)
        finally:
            temporary.unlink(missing_ok=True)


class ModelSession:
    def __init__(self, binary, ui_port, threads, config):
        self.binary = binary
        self.ui_port = ui_port
        self.threads = threads
        self.config = config
        self.resources = AsyncExitStack()
        self.engine = None
        self.task = None
        self.selection = None
        self.error = None
        self.generation = asyncio.Lock()
        self.picker = asyncio.Lock()

    @property
    def ready(self):
        return self.engine is not None and self.engine.process.returncode is None

    @property
    def loading(self):
        return self.task is not None and not self.task.done()

    def start(self, model, *, persist=False):
        self.selection = model
        self.error = None
        self.task = asyncio.create_task(self.load(model, persist))

    async def load(self, model, persist):
        try:
            async with AsyncExitStack() as candidate:
                engine = self.engine
                replace = not self.ready or engine.model != model
                if replace:
                    engine = await candidate.enter_async_context(launch_engine(self.binary, model, self.ui_port, self.threads))
                if persist:
                    save_model(self.config, model)
                if replace:
                    previous = self.resources
                    self.resources = candidate.pop_all()
                    self.engine = engine
                    await previous.aclose()
        except (OSError, RuntimeError) as error:
            print(error, flush=True)
            self.error = 'Could not load this model. Choose a readable Gemma 3 270M Instruct GGUF and try again.'

    async def close(self):
        if self.loading:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        await self.resources.aclose()

    def status(self):
        result = {'status': 'loading' if self.loading else 'ready' if self.ready else 'setup'}
        if self.selection:
            result.update(folder=str(self.selection.parent), filename=self.selection.name)
        if self.ready:
            result.update(model=MODEL, load_ms=self.engine.load_ms, pid=self.engine.process.pid)
        error = self.error or ('The model process stopped. Load the model again.' if self.engine and not self.ready else None)
        if error:
            result['error'] = error
        return result


async def choose_folder():
    command = 'POSIX path of (choose folder with prompt "Choose the folder containing Gemma")'
    process = await asyncio.create_subprocess_exec('/usr/bin/osascript', '-e', command,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, error = await asyncio.wait_for(process.communicate(), 120)
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
    if process.returncode == 0:
        return out.decode().rstrip('\n')
    if b'(-128)' in error:
        return None
    raise RuntimeError('The folder picker could not open.')


def create_app(binary, model=None, ui_port=8019, threads=None, config=CONFIG):
    session = ModelSession(binary, ui_port, threads, config)

    @asynccontextmanager
    async def lifespan(app):
        selection = model
        if selection is None:
            try:
                saved = json.loads(config.read_text())
                selection = find_model(Path(saved['folder']), saved['filename'])
            except FileNotFoundError as error:
                if error.filename != str(config):
                    session.error = 'The saved model folder or file is unavailable. Choose its current location.'
            except (OSError, ValueError, KeyError, TypeError):
                session.error = 'The saved model could not be opened. Choose its folder again.'
        if selection is not None:
            session.start(selection)
        print(f'Open http://{HOST}:{ui_port}/ for LocalFirst.', flush=True)
        try:
            yield
        finally:
            await session.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[HOST, 'localhost'])
    app.include_router(search_router)

    @app.middleware('http')
    async def same_origin(request: Request, call_next):
        if request.method == 'POST':
            origin = request.headers.get('origin')
            if origin is not None and origin != f"http://{request.headers.get('host')}":
                return JSONResponse({'detail': 'Use native chat from the LocalFirst site.'}, status_code=403)
            if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                return JSONResponse({'detail': 'Send requests as JSON.'}, status_code=415)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/api/native/status')
    async def status():
        return JSONResponse(session.status(), headers={'Cache-Control': 'no-store'})

    @app.post('/api/native/folder')
    async def pick_folder():
        if session.picker.locked():
            raise HTTPException(409, 'A folder picker is already open.')
        async with session.picker:
            try:
                return {'folder': await choose_folder()}
            except (OSError, RuntimeError, TimeoutError) as error:
                raise HTTPException(503, 'Could not open the folder picker. Paste the folder path instead.') from error

    @app.post('/api/native/models')
    async def models(body: FolderInput):
        try:
            folder, candidates = scan_folder(Path(body.folder))
        except (OSError, ValueError) as error:
            raise HTTPException(422, 'Enter the path to a readable folder.') from error
        return {'folder': str(folder), 'files': [path.name for path in candidates]}

    @app.post('/api/native/setup', status_code=202)
    async def setup(body: ModelInput):
        if session.loading or session.generation.locked():
            raise HTTPException(409, 'Wait for the current model load or reply to finish, then try again.')
        try:
            selection = find_model(Path(body.folder), body.filename)
        except (OSError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        session.start(selection, persist=True)
        return session.status()

    @app.post('/api/native/generate')
    async def generate(body: Generation):
        if session.loading or not session.ready:
            raise HTTPException(503, 'Gemma is not ready. Finish model setup or wait for it to load.')
        messages = [message.model_dump() for message in body.messages]
        if sum(len(message['content'].encode()) for message in messages) > 3200:
            raise HTTPException(422, 'Use a shorter message for the native model.')
        if [message['role'] for message in messages] != (['user', 'assistant'] * (len(messages) // 2) + ['user']):
            raise HTTPException(422, 'A chat needs alternating messages and a final user message.')
        return StreamingResponse(completion(session, messages), media_type='application/x-ndjson',
                                 headers={'Cache-Control': 'no-store'})

    @app.get('/', include_in_schema=False)
    @app.get('/index.html', include_in_schema=False)
    async def index():
        return FileResponse(NATIVE_ASSETS / 'index.html', headers={'Cache-Control': 'no-cache'})

    app.mount('/', StaticFiles(directory=NATIVE_ASSETS))
    return app


async def completion(session, messages):
    if session.loading or not session.ready:
        yield event('error', message='Gemma is still loading. Try again when setup is complete.')
        return
    lock = session.generation
    if lock.locked():
        yield event('error', message='The native model is replying in another tab. Try again when it finishes.')
        return
    payload = {'model': MODEL, 'messages': messages, 'stream': True, 'stream_options': {'include_usage': True},
               'max_tokens': 256, 'temperature': 0}
    async with lock:
        metrics = {}
        try:
            async with asyncio.timeout(180), session.engine.client.stream('POST', '/v1/chat/completions', json=payload) as reply:
                reply.raise_for_status()
                async for line in reply.aiter_lines():
                    if not line.startswith('data: '):
                        continue
                    data = line[6:]
                    if data == '[DONE]':
                        yield event('done', metrics=metrics)
                        return
                    packet = json.loads(data)
                    if packet.get('error'):
                        break
                    choices = packet.get('choices') or []
                    if choices:
                        content = choices[0]['delta'].get('content')
                        if content:
                            yield event('delta', content=content)
                    if usage := packet.get('usage'):
                        metrics = {'input_tokens': usage.get('prompt_tokens'), 'output_tokens': usage.get('completion_tokens'),
                                   'tokens_per_second': packet.get('timings', {}).get('predicted_per_second')}
        except (TimeoutError, httpx.HTTPError, ValueError, AttributeError, KeyError, TypeError):
            pass
        yield event('error', message='llama.cpp could not finish the reply. Try again or restart the native launcher.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, help='Open with a specific local Gemma folder')
    parser.add_argument('--model', help='GGUF filename when the folder contains more than one')
    parser.add_argument('--llama-server', default='llama-server', help='Path to the llama.cpp server executable')
    parser.add_argument('--port', type=int, default=8019, help='Browser port, defaults to 8019')
    parser.add_argument('--threads', type=int, help='CPU inference threads, defaults to llama.cpp selection')
    parser.add_argument('--config', type=Path, default=CONFIG, help='Path to the saved model selection')
    args = parser.parse_args()
    binary = shutil.which(os.path.expanduser(args.llama_server))
    if binary is None:
        parser.error('Could not find llama-server. Supply its path with --llama-server.')
    if not 1 <= args.port <= 65535:
        parser.error('--port must be in the range 1–65535.')
    if args.threads is not None and args.threads < 1:
        parser.error('--threads must be positive.')
    if not (NATIVE_ASSETS / 'index.html').is_file():
        parser.error('Build the browser assets with npm run build:browser first.')
    if args.model and not args.model_dir:
        parser.error('--model requires --model-dir.')
    try:
        model = find_model(args.model_dir, args.model) if args.model_dir else None
    except (OSError, ValueError) as error:
        parser.error(str(error))
    uvicorn.run(create_app(binary, model, args.port, args.threads, args.config.expanduser().resolve()), host=HOST, port=args.port,
                access_log=False, proxy_headers=False)


if __name__ == '__main__':
    main()
