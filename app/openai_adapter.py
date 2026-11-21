"""Streaming text completions from the OpenAI API."""
import json

import httpx

from .ollama_adapter import OllamaError
from .routing import MAX_OUTPUT_TOKENS


async def check_connection(key, model):
    """Metadata only: verify authentication/model access without generating text."""
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.get(f'https://api.openai.com/v1/models/{model}',
                                        headers={'Authorization': f'Bearer {key}'})
        if response.status_code == 401:
            raise OllamaError('OpenAI did not accept that API key. Check it and try again.')
        if response.status_code in (403, 404):
            raise OllamaError('This key cannot access the selected model. Check model permissions or choose another model.')
        if not response.is_success:
            raise OllamaError('OpenAI could not verify the connection right now. Try again shortly.')
        if not isinstance(response.json().get('id'), str):
            raise OllamaError('OpenAI returned an invalid model check. The connection was not saved.')
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise OllamaError('Could not reach OpenAI to verify the connection. Check your internet connection and try again.') from None


async def stream_openai(routing, messages):
    usage = {}
    options = {'reasoning_effort': 'none'} if routing.model == 'gpt-6-luna' else {}
    try:
        async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
            async with client.stream(
                'POST', 'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {routing.key}'},
                json={'model': routing.model, 'messages': messages, 'stream': True,
                      'stream_options': {'include_usage': True}, 'max_completion_tokens': MAX_OUTPUT_TOKENS,
                      'store': False, 'service_tier': 'default', **options},
            ) as response:
                if response.status_code != 200:
                    raise OllamaError(f'OpenAI rejected the request (HTTP {response.status_code}). Check provider configuration and quota.')
                async for line in response.aiter_lines():
                    if not line.startswith('data: '):
                        continue
                    data = line[6:]
                    if data == '[DONE]':
                        yield {'done': True, 'prompt_eval_count': usage.get('prompt_tokens'),
                               'eval_count': usage.get('completion_tokens')}
                        return
                    packet = json.loads(data)
                    if packet.get('error'):
                        raise OllamaError('OpenAI reported a streaming error.')
                    if packet.get('usage'):
                        usage = packet['usage']
                    for choice in packet.get('choices', []):
                        yield {'model': packet.get('model'), 'message': choice.get('delta', {})}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise OllamaError('OpenAI connection or stream failed.') from exc
