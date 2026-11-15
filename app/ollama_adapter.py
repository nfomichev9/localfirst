"""The local inference boundary. Never downloads models or follows redirects."""
import json
import httpx


class OllamaError(Exception):
    pass


class OllamaAdapter:
    def __init__(self, transport=None):
        self.client = httpx.AsyncClient(base_url='http://127.0.0.1:11434',
            timeout=httpx.Timeout(120, connect=5), transport=transport, trust_env=False)

    async def close(self):
        await self.client.aclose()

    @staticmethod
    def translate(exc):
        if isinstance(exc, httpx.TimeoutException):
            return OllamaError('Ollama timed out. Try a shorter prompt or a smaller installed model.')
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code == 404:
                return OllamaError('Model not found in Ollama. Refresh models and select an installed model.')
            return OllamaError(f'Ollama returned HTTP {exc.response.status_code}. Check the local Ollama service.')
        return OllamaError('Cannot connect to Ollama at localhost:11434. Open Ollama or run ollama serve, then retry.')

    async def models(self):
        try:
            response = await self.client.get('/api/tags', timeout=5)
            response.raise_for_status()
            names = [m['name'] for m in response.json()['models']]
            if not all(isinstance(name, str) and name for name in names):
                raise ValueError('Invalid model name')
            return names
        except httpx.HTTPError as exc:
            raise self.translate(exc) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise OllamaError('Ollama returned an invalid model list.') from exc

    async def stream(self, model, messages):
        try:
            async with self.client.stream('POST', '/api/chat', json={
                'model': model, 'messages': messages, 'stream': True,
                'options': {'num_ctx': 4096, 'num_predict': 2048},
            }) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    packet = json.loads(line)
                    if not isinstance(packet, dict):
                        raise ValueError('Invalid packet')
                    if packet.get('error'):
                        raise OllamaError('Ollama could not generate a response. Check the selected model and retry.')
                    yield packet
                    if packet.get('done'):
                        return
                raise OllamaError('Ollama ended the stream before completing the response.')
        except httpx.HTTPError as exc:
            raise self.translate(exc) from exc
        except (ValueError, TypeError) as exc:
            raise OllamaError('Ollama returned an invalid response stream.') from exc
