"""Isolated fake-provider server used only by browser.cjs."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from app.main import create_app

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
        if messages[-1]['content'] in ('__streaming_stress__', '__streaming_error__'):
            yield {'message': {'content': '# Streaming test\n\nSelect this stable paragraph.\n\n```python\nprint("stable")\n```\n\n' + ''.join(f'Paragraph {i} stays readable.\n\n' for i in range(60))}}
            for i in range(30):
                await asyncio.sleep(.05)
                for part in ('Batch ', str(i), ' — café 🌿. '):
                    yield {'message': {'content': part}}
                if i == 5 and messages[-1]['content'] == '__streaming_error__':
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


uvicorn.run(create_app(sys.argv[2], BrowserAdapter()), host='127.0.0.1', port=int(sys.argv[1]), log_level='error', access_log=False)
