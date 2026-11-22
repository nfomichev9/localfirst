/* Real Gemma onboarding with an isolated browser profile and saved model selection. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync} = require('node:fs');
const {createServer} = require('node:net');
const {tmpdir} = require('node:os');
const {basename, join, resolve} = require('node:path');
const {setTimeout: delay} = require('node:timers/promises');
const {chromium} = require('playwright');

async function sparePort() {
  const server = createServer().listen(0, '127.0.0.1');
  await once(server, 'listening');
  const {port} = server.address();
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function main() {
  const [binary, model] = process.argv.slice(2);
  assert.ok(binary && model, 'Usage: node tests/native-onboarding.cjs /path/to/llama-server /path/to/model.gguf');
  const port = await sparePort();
  const base = 'http://127.0.0.1:' + port;
  const directory = mkdtempSync(join(tmpdir(), 'localfirst-onboarding-'));
  const config = join(directory, 'model.json');
  const folder = join(directory, 'Gemma models');
  mkdirSync(folder);
  const filename = basename(model);
  symlinkSync(resolve(model), join(folder, filename));
  writeFileSync(join(folder, 'broken.gguf'), 'GGUF');
  let child, exited, browser;

  async function status() {
    const response = await fetch(base + '/api/native/status');
    assert.ok(response.ok);
    return response.json();
  }

  async function start() {
    child = spawn(process.env.PYTHON || '.venv/bin/python', ['-m', 'native.serve', '--llama-server', resolve(binary),
      '--port', String(port), '--config', config, '--threads', '2'], {stdio: ['ignore', 'ignore', 'inherit']});
    exited = once(child, 'exit');
    for (let i = 0; i < 100; i++) {
      if (child.exitCode != null) throw new Error('The launcher stopped before opening the UI.');
      const result = await status().catch(() => null);
      if (result) return result;
      await delay(100);
    }
    throw new Error('Timed out waiting for the launcher.');
  }

  async function stop() {
    if (!child) return;
    child.kill('SIGTERM');
    await exited;
    child = null;
  }

  try {
    assert.equal((await start()).status, 'setup');
    assert.equal((await fetch(base + '/browser/')).status, 404);
    browser = await chromium.launch({channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome'});
    const page = await browser.newPage();
    const external = [];
    await page.context().route('**/*', route => {
      if (route.request().url().startsWith(base + '/')) return route.continue();
      external.push(route.request().url());
      return route.abort();
    });
    await page.goto(base);
    const heading = page.getByRole('heading', {name: 'Set up local chat'});
    const path = page.getByLabel('Or paste a folder path');
    const find = page.getByRole('button', {name: 'Find models'});
    await heading.waitFor();
    await path.fill(folder + '/missing');
    await find.click();
    await page.getByText('Enter the path to a readable folder.').waitFor();
    // Use a fixture for the macOS dialog so the GUI smoke test needs no desktop interaction.
    await page.route('**/api/native/folder', route => route.fulfill({json: {folder}}));
    await page.getByRole('button', {name: 'Choose folder…'}).click();
    const file = page.getByLabel('Model file');
    await file.selectOption('broken.gguf');
    const load = page.getByRole('button', {name: 'Load model'});
    await load.click();
    await page.getByText('Could not load this model.', {exact: false}).waitFor();
    assert.equal((await status()).status, 'setup');
    await file.selectOption(filename);
    await load.click();
    await page.getByText('llama.cpp ready', {exact: true}).waitFor();
    const first = await status();
    assert.ok(first.pid);
    assert.equal(readFileSync(config, 'utf8').includes(filename), true);

    const prompt = page.getByRole('textbox', {name: 'Message LocalFirst'});
    await prompt.fill('What color is the sky? The sky is blue. Answer in one word.');
    const send = page.getByRole('button', {name: 'Send message'});
    await send.click();
    const reply = page.locator('.assistant .message-content').filter({hasText: /blue/i});
    await reply.waitFor();
    await send.waitFor();
    await page.reload();
    await reply.waitFor();
    assert.equal((await status()).pid, first.pid);

    await page.locator('#workspace summary').click();
    await page.getByRole('link', {name: 'Model setup', exact: true}).click();
    await heading.waitFor();
    assert.equal(await file.inputValue(), filename);
    await page.getByRole('link', {name: 'Back to chat'}).click();
    await reply.waitFor();
    assert.equal((await status()).pid, first.pid);

    await stop();
    await start();
    await page.goto(base);
    await reply.waitFor();
    const resumed = await status();
    assert.equal(resumed.status, 'ready');
    assert.equal(resumed.filename, filename);
    assert.notEqual(resumed.pid, first.pid);
    assert.deepEqual(external, []);
    console.log('PASS: native folder selection, invalid model recovery, saved setup, warm reload, and offline chat');
  } finally {
    await browser?.close();
    await stop();
    rmSync(directory, {recursive: true, force: true});
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
