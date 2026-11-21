/* Runs against an isolated SQLite DB and fake provider. No model or external requests. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {mkdtempSync, mkdirSync, rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {chromium} = require('playwright');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'localfirst-browser-'));
  const socket = net.createServer(); await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
  const port = socket.address().port; await new Promise(resolve => socket.close(resolve));
  const base = `http://127.0.0.1:${port}`;
  const server = spawn(process.env.PYTHON || '.venv/bin/python', ['tests/browser_server.py', String(port), path.join(directory, 'test.db')], {stdio:'inherit'});
  let browser;
  try {
    let ready = false;
    for (let i=0; i<100; i++) {
      try { if ((await fetch(base+'/api/health')).ok) {ready = true; break;} } catch {}
      await delay(100);
    }
    assert.ok(ready, 'server starts');
    browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless:true});
    const page = await browser.newPage();
    const errors = [], external = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => {
      if (route.request().url().startsWith(base)) route.continue();
      else { external.push(route.request().url()); route.abort(); }
    });
    await page.goto(base+'/usage');
    await page.waitForFunction(() => document.querySelector('#usage-status').textContent.startsWith('No inference'));
    assert.match(await page.locator('#overview-cards').innerText(), /\$0.0000/);
    assert.equal(await page.locator('.chart-point').count(), 0);
    await page.goto(base);
    await page.waitForFunction(() => document.querySelector('#send').disabled === false);
    await page.locator('#prompt').fill('Show Markdown'); await page.locator('#send').click();
    await page.locator('.assistant h1').waitFor();
    assert.match(await page.locator('.assistant .message-error').innerText(), /Generating/);
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    assert.equal(await page.locator('.assistant strong').innerText(), 'bold');
    assert.equal(await page.locator('.assistant em').innerText(), 'italic');
    assert.equal(await page.locator('.assistant a').first().getAttribute('href'), 'https://example.com');
    assert.equal(await page.locator('.assistant li').count(), 2);
    assert.equal(await page.locator('.assistant table td').first().innerText(), 'Local');
    assert.ok(await page.locator('pre code.hljs span').count() > 0, 'syntax highlighting');
    assert.equal(await page.locator('.assistant script, .assistant img, .assistant [onerror], .assistant a[href^="javascript:"]').count(), 0);
    assert.equal(await page.evaluate(() => window.pwned), undefined);
    assert.match(await page.locator('.metrics summary').innerText(), /test:local · Local.*40 tokens.*\$0.0000/);
    await page.locator('.metrics summary').click();
    assert.match(await page.locator('.metrics details > div').innerText(), /60 tok\/s/);
    await page.getByRole('button', {name:'Helpful', exact:true}).click();
    await page.waitForFunction(() => document.querySelector('[aria-label="Helpful"]').getAttribute('aria-pressed') === 'true');
    await page.reload(); await page.locator('#conversations button').first().click();
    await page.locator('.assistant h1').waitFor();
    assert.equal(await page.getByRole('button', {name:'Helpful', exact:true}).getAttribute('aria-pressed'), 'true');
    const saved = await (await fetch(base+'/api/conversations')).json();
    const conversation = await (await fetch(base+`/api/conversations/${saved[0].id}`)).json();
    assert.ok(conversation.messages[1].content.includes('# A useful answer'), 'SQLite keeps raw Markdown');
    // Every partial prefix is re-rendered just as a streamed response would be.
    await page.evaluate(() => {
      const raw = '# Heading\n\n**bold** and `code`\n\n```js\nconst n = 2;\n```\n\n<img src=x onerror=alert(1)>[x](javascript:alert(1))';
      const el = document.createElement('div');
      for (let i=0; i<=raw.length; i++) {
        renderMarkdown(el, raw.slice(0,i));
        if (el.querySelector('script,img,[onerror],a[href^="javascript:"]')) throw Error('Unsafe partial Markdown');
      }
    });
    mkdirSync('test-results', {recursive:true});
    await page.screenshot({path:'test-results/chat-desktop.png',fullPage:true});
    await page.getByRole('link', {name:/Usage & analytics/}).click();
    await page.waitForFunction(() => document.querySelector('#usage-status').textContent.startsWith('Showing'));
    assert.match(await page.locator('#overview-cards').innerText(), /100%/);
    assert.match(await page.locator('#overview-cards').innerText(), /\$0.0000/);
    assert.equal(await page.locator('#model-rows tr').count(), 1);
    await page.locator('#requests-chart .chart-point').focus();
    assert.match(await page.locator('#requests-chart .chart-caption').innerText(), /1 requests \(1 local, 0 cloud\)/);
    await page.locator('#period').selectOption('0');
    await page.waitForFunction(() => document.querySelector('#usage-status').textContent.startsWith('Showing'));
    await page.locator('.analytics-content').evaluate(el => el.scrollTop = 0);
    await page.screenshot({path:'test-results/usage-desktop.png',fullPage:true});
    const second = await fetch(base+`/api/conversations/${saved[0].id}/chat`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({content:'Second model', model:'second:local'})});
    await second.text();
    await page.locator('#refresh-usage').click();
    await page.locator('#filter-model option[value="second:local"]').waitFor({state:'attached'});
    await page.locator('#filter-model').selectOption('test:local');
    await page.waitForFunction(() => document.querySelectorAll('#model-rows tr').length === 1);
    assert.match(await page.locator('#model-rows').innerText(), /test:local/);
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'mobile layout fits');
    await page.screenshot({path:'test-results/usage-mobile.png',fullPage:true});
    await page.goto(base+'/usage');
    await page.waitForFunction(() => document.querySelector('#usage-status').textContent.startsWith('Showing'));
    // API model filter with no observations preserves truthful empty state.
    const empty = await (await fetch(base+'/api/usage?model=missing')).json(); assert.equal(empty.overview.requests, 0);
    await page.goto(base+'/settings');
    await page.getByRole('button', {name:'Save settings'}).waitFor();
    await page.getByRole('combobox', {name:'Response mode'}).waitFor();
    assert.equal(await page.locator('#mode option').count(), 4);
    assert.equal(await page.locator('#mode').inputValue(), 'always_local');
    await page.getByRole('tab', {name:'Spending', exact:true}).click();
    await page.getByLabel('Daily cloud spending limit (USD)').fill('0.01');
    await page.getByRole('button', {name:'Save settings'}).click();
    await page.getByText('Settings saved.').waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'mobile settings fit');
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#limit').value === '0.01');
    await page.getByRole('link', {name:'Back to chat'}).click();
    await page.waitForURL(base + '/');
    await page.getByRole('link', {name:'Settings', includeHidden:true}).waitFor({state:'attached'});
    assert.equal(await page.locator('#routing-mode').textContent(), 'Always local');
    await require('./settings-browser.cjs')(browser, base);
    await require('./streaming.cjs')(browser, base);
    await require('./lab-browser.cjs')(browser, base);
    await require('./pdf-browser.cjs')(browser, base);
    await require('./handoff-browser.cjs')(browser, base);
    await require('./web-browser.cjs')(browser, base);
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    console.log('PASS: streaming/historical Markdown, XSS sanitization, highlighting, metrics, feedback, dashboard, chart interaction, mobile, zero external requests');
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve => server.once('exit', resolve));
    rmSync(directory, {recursive:true, force:true});
  }
})().catch(error => {console.error(error); process.exitCode=1;});
