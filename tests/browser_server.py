"""Isolated fake-provider server used only by browser.cjs."""
import asyncio
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from app.main import create_app
import app.main as backend
from app.ollama_adapter import OllamaError
from app.web_search import WEB_CONTEXT_PREFIX, WebSearchError

# This test process never inherits a real provider key or calls a cloud endpoint.
os.environ['OPENAI_API_KEY'] = 'browser-synthetic-key'
os.environ['OPENAI_MODEL'] = 'gpt-6-luna'


class MemorySecrets:
    def __init__(self):
        self.values = {}

    def set(self, identifier, key):
        self.values[identifier] = key

    def get(self, identifier):
        return self.values.get(identifier)

    def delete(self, identifier):
        self.values.pop(identifier, None)


async def fake_connection_check(key, model):
    if key == 'invalid-key':
        raise OllamaError('OpenAI did not accept that API key. Check it and try again.')


async def fake_frontier(routing, messages):
    if 'simulate frontier failure' in messages[0]['content']:
        yield {'message':{'content':'Partial review'}}
        raise OllamaError('Synthetic cloud stream failed. Your local answer is preserved.')
    yield {'message':{'content':'Frontier reviewed '}, 'model':routing.model}
    await asyncio.sleep(.15)
    yield {'message':{'content':'the supplied brief.'}, 'model':routing.model}
    yield {'done':True, 'prompt_eval_count':30, 'eval_count':8}


backend.check_connection = fake_connection_check
backend.stream_openai = fake_frontier

web_attempts = {}


async def fake_web_search(query):
    web_attempts[query] = web_attempts.get(query, 0) + 1
    if query == '__web_slow__' and web_attempts[query] == 1:
        await asyncio.sleep(60)
    if query == '__web_error__':
        raise WebSearchError('Synthetic search unavailable. Try again or turn Search off.')
    return {'query':query, 'provider':'DuckDuckGo', 'retrieved_at':'2026-11-20T12:00:00+00:00',
            'sources':[{'number':1,'title':'CedarMoon official news','url':'https://example.com/news',
                        'excerpt':'The approved CedarMoon budget is USD 18400.'},
                       {'number':2,'title':'CedarMoon release notes','url':'https://example.net/releases',
                        'excerpt':'The launch is December 12.'}]}

MARKDOWN = '''# A useful answer

A **bold** and *italic* idea with `inline code`.

- First item
- Second item

| Name | Value |
| --- | --- |
| Local | Yes |

```python
print("hello")
```

[Safe link](https://example.com)
<script>window.pwned = true</script><img src=x onerror="window.pwned=true">
[Bad link](javascript:alert(1))
'''


class BrowserAdapter:
    async def close(self):
        pass

    async def models(self):
        return ['test:local', 'second:local']

    async def stream(self, model, messages):
        prompt = messages[-1]['content']
        if messages[0]['role'] == 'system' and messages[0]['content'].startswith(WEB_CONTEXT_PREFIX):
            yield {'message':{'content':'The approved budget is **USD 18400** '}}
            await asyncio.sleep(.2)
            yield {'message':{'content':'[1, 2].'}, 'done':True,'model':model,
                   'prompt_eval_count':100,'eval_count':15,'eval_duration':200_000_000}
            return
        if messages[0]['role'] == 'system' and messages[0]['content'].startswith('Prepare a concise review'):
            if '__prepare_slow__' in prompt:
                await asyncio.sleep(3)
            answer = 'Malformed preparation.' if '__prepare_invalid__' in prompt else json.dumps({
                'summary':'Review the synthetic conversation.', 'facts_and_constraints':'Synthetic input only.',
                'task':'Review the local draft.', 'source_excerpts':'Local draft excerpt.', 'reason':'The user requested review.'})
            yield {'message':{'content':answer}, 'done':True, 'model':model}
            return
        if prompt in ('__manual_handoff__','__prepare_slow__','__prepare_invalid__'):
            yield {'message':{'content':'Local draft for review.'}, 'done':True, 'model':model,
                   'prompt_eval_count':10, 'eval_count':5, 'eval_duration':100_000_000}
            return
        if messages[0]['content'].startswith('You are reading an attached PDF locally.'):
            text = messages[0]['content']
            answer = 'The approved budget is **USD 18400** [p. 1].' if '18400' in text else 'No budget found in the supplied excerpts.'
            if 'lead' in prompt.lower():
                answer = 'The lead is **Riley** [p. 2].' if 'Riley' in text else 'The lead is not in the excerpts.'
            yield {'message': {'content': answer[:12]}}
            await asyncio.sleep(3 if prompt == '__pdf_slow__' and model == 'test:local' else .2)
            yield {'message': {'content': answer[12:]}, 'done': True, 'model': model,
                   'prompt_eval_count': 110, 'eval_count': 15, 'eval_duration': 200_000_000}
            return
        if prompt.startswith('You are a local request editor') or prompt.startswith('Task:\n'):
            if prompt.startswith('You are a local request editor'):
                result = json.dumps(dict(context_sufficient=False, missing_information=['The email body'],
                    clarifying_questions=['What does the email say?'], assumptions=[],
                    prepared_prompt='Reply to the supplied email without inventing its contents.'))
            else:
                result = '391'
            yield {'message':{'content':result[:3]}}
            await asyncio.sleep(2 if '__lab_slow__' in prompt else .15)
            yield {'message':{'content':result[3:]}, 'done':True, 'model':model,
                   'prompt_eval_count':20, 'eval_count':5, 'eval_duration':100_000_000}
            return
        if messages[-1]['content'] in ('__streaming_stress__', '__streaming_error__'):
            yield {'message': {'content': '# Streaming test\n\nSelect this stable paragraph.\n\n```python\nprint("stable")\n```\n\n' + ''.join(f'Paragraph {i} stays readable.\n\n' for i in range(60))}}
            for i in range(30):
                await asyncio.sleep(.05)
                for part in ('Batch ', str(i), ' — café 🌿. '):
                    yield {'message': {'content': part}}
                if i == 5 and prompt == '__streaming_error__' and model == 'test:local':
                    from app.ollama_adapter import OllamaError
                    raise OllamaError('Test stream interrupted.')
            yield {'message': {'content':'\n\n**Complete.**'}, 'done':True, 'model':model,
                   'prompt_eval_count':10, 'eval_count':100, 'eval_duration':1_500_000_000}
            return
        yield {'message': {'content': '# A useful'}}
        await asyncio.sleep(.5)
        yield {'message': {'content': MARKDOWN[len('# A useful'):]}}
        await asyncio.sleep(.1)
        yield {'done': True, 'model': model, 'prompt_eval_count': 10, 'eval_count': 30, 'eval_duration': 500_000_000}


uvicorn.run(create_app(sys.argv[2], BrowserAdapter(), MemorySecrets(), web_searcher=fake_web_search),
            host='127.0.0.1', port=int(sys.argv[1]), log_level='error', access_log=False)
