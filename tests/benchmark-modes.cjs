/* Real-model comparison. Use an isolated app database and Ollama instance. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {mkdtempSync, rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const {join} = require('node:path');
const {setTimeout: delay} = require('node:timers/promises');
const {chromium} = require('playwright');

const ollamaAppURL = process.env.BENCH_OLLAMA_APP_URL || 'http://127.0.0.1:18080';
const isolatedOllama = process.env.BENCH_OLLAMA_COLD_URL || 'http://127.0.0.1:18087';
const nativeURL = 'http://127.0.0.1:18089';
const model = 'gemma3:270m';
const prompts = ['oceans', 'mountains', 'deserts', 'forests', 'rivers'].map(topic =>
  `Write ten numbered facts about ${topic}. Use one short sentence per fact.`);

async function until(check) {
  const end = performance.now() + 90_000;
  do {
    const result = await check();
    if (result) return result;
    await delay(50);
  } while (performance.now() < end);
  throw new Error('Timed out waiting for a local model.');
}

async function benchmarkChat(page, name, content, nativeOrBrowser) {
  return page.evaluate(async ({name, content, nativeOrBrowser}) => {
    const request = nativeOrBrowser ? window.localfirstBrowser.request : fetch;
    const post = async (url, body) => {
      const result = await request(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)});
      if (!result.ok) throw new Error(`${result.status} ${await result.text()}`);
      return result;
    };
    const {id} = await (await post('/api/conversations', {})).json();
    const started = performance.now();
    const reply = await post(`/api/conversations/${id}/chat`, {model: name, content});
    const reader = reply.body.pipeThrough(new TextDecoderStream()).getReader();
    let pending = '', firstTextMs = null;
    try {
      for (;;) {
        const {done, value} = await reader.read();
        if (done) throw new Error('Chat ended without telemetry.');
        pending += value;
        let end;
        while ((end = pending.indexOf('\n')) !== -1) {
          const event = JSON.parse(pending.slice(0, end));
          pending = pending.slice(end + 1);
          if (event.type === 'delta' && event.content) firstTextMs ??= performance.now() - started;
          if (event.type === 'error') throw new Error(event.message);
          if (event.type === 'done') {
            const t = event.telemetry;
            if (firstTextMs == null || !t.output_tokens || !t.tokens_per_second) throw new Error('Incomplete timing sample.');
            return {firstTextMs, tokensPerSecond: t.tokens_per_second, tokens: t.output_tokens};
          }
        }
      }
    } finally { reader.releaseLock(); }
  }, {name, content, nativeOrBrowser});
}

async function nativeSamples(context, binary, folder) {
  const coldMs = [], warm = [];
  for (let trial = 0; trial < 3; trial++) {
    const child = spawn(process.env.PYTHON || '.venv/bin/python', ['-m', 'native.serve', '--llama-server', binary,
      '--model-dir', folder, '--port', '18089', '--threads', process.env.BENCH_THREADS || '2'],
    {stdio: ['ignore', 'ignore', 'inherit']});
    const exited = once(child, 'exit');
    try {
      const status = await until(async () => {
        if (child.exitCode != null) throw new Error('Native launcher exited before loading the model.');
        const response = await fetch(nativeURL + '/api/native/status').catch(() => null);
        if (!response?.ok) return false;
        const status = await response.json();
        if (status.error) throw new Error(status.error);
        return status.status === 'ready' && status;
      });
      coldMs.push(status.load_ms);
      if (trial !== 2) continue;
      const page = await context.newPage();
      try {
        await page.goto(nativeURL);
        await page.getByText('llama.cpp ready', {exact: true}).waitFor();
        for (const prompt of prompts) {
          await page.reload();
          await page.getByText('llama.cpp ready', {exact: true}).waitFor();
          const reloaded = await (await fetch(nativeURL + '/api/native/status')).json();
          assert.equal(reloaded.pid, status.pid, 'browser reload must retain the same llama.cpp process');
          warm.push(await benchmarkChat(page, 'gemma-270m', prompt, true));
        }
      } finally { await page.close(); }
    } finally {
      child.kill('SIGTERM');
      await exited;
    }
  }
  return {coldMs, warm};
}

async function ollamaSamples(context) {
  const origin = new URL(isolatedOllama);
  assert.match(origin.hostname, /^(127\.0\.0\.1|localhost)$/);
  assert.ok(origin.port && origin.port !== '11434', 'Use an isolated Ollama instance for unloads.');
  const coldMs = [];
  const load = async keep_alive => {
    const response = await fetch(isolatedOllama + '/api/generate', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({model, keep_alive, stream: false, options: {num_ctx: 4096, num_predict: 2048}})});
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  };
  for (let trial = 0; trial < 3; trial++) {
    await load(0);
    await until(async () => (await (await fetch(isolatedOllama + '/api/ps')).json()).models.length === 0);
    const start = performance.now();
    const result = await load('5m');
    coldMs.push(performance.now() - start);
    assert.equal(result.done_reason, 'load');
  }
  await load(0);

  const page = await context.newPage();
  try {
    await page.goto(ollamaAppURL);
    assert.equal((await (await fetch(ollamaAppURL + '/api/settings')).json()).mode, 'always_local');
    await page.locator('#model').locator(`option[value="${model}"]`).waitFor({state: 'attached'});
    await benchmarkChat(page, model, 'Write one short sentence about the color blue.', false);
    const warm = [];
    for (const prompt of prompts) warm.push(await benchmarkChat(page, model, prompt, false));
    return {coldMs, warm};
  } finally { await page.close(); }
}

async function main() {
  const [binary, folder] = process.argv.slice(2);
  assert.ok(binary && folder, 'Usage: node tests/benchmark-modes.cjs /path/to/llama-server /path/to/model-folder');
  assert.notEqual(new URL(ollamaAppURL).port, '8000', 'Use a temporary app database for benchmark conversations.');
  const profile = mkdtempSync(join(tmpdir(), 'localfirst-mode-benchmark-'));
  let context;
  try {
    context = await chromium.launchPersistentContext(profile, {channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome'});
    for (const [name, run] of [
      ['llama.cpp', () => nativeSamples(context, binary, folder)],
      ['ollama', () => ollamaSamples(context)],
    ]) console.log(JSON.stringify({name, ...await run()}));
  } finally {
    await context?.close();
    rmSync(profile, {recursive: true, force: true});
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
