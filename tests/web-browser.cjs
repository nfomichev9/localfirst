const assert = require('node:assert/strict');

module.exports = async function(browser, base) {
  const page = await browser.newPage({viewport:{width:1280,height:900}});
  const errors = [], external = [], sent = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/chat')) sent.push(request.postDataJSON());
  });
  await page.route('**/*', route => {
    if (route.request().url().startsWith(base)) route.continue();
    else { external.push(route.request().url()); route.abort(); }
  });
  const idle = () => page.waitForFunction(() => !document.querySelector('#send').hidden && !document.querySelector('#send').disabled);
  const search = () => page.getByRole('button', {name:'Search',exact:true});
  const start = async query => {
    if (!(await page.locator('#new-chat').isVisible())) await page.getByRole('button',{name:'Toggle conversations'}).click();
    await page.getByRole('button', {name:'New chat',exact:true}).click();
    await idle(); await search().click(); await idle();
    await page.locator('#prompt').fill(query); await page.locator('#send').click();
  };
  try {
    await page.goto(base); await idle();
    assert.equal(await search().getAttribute('aria-pressed'), 'false');
    await start('What is new at CedarMoon?');
    await page.getByText('Sources · 2', {exact:true}).waitFor(); await idle();
    assert.equal(sent.at(-1).web_search, true);
    assert.equal(await page.locator('.assistant .message-content').innerText(), 'The approved budget is USD 18400 [1, 2].');
    assert.deepEqual(await page.locator('.assistant .message-content a').evaluateAll(links => links.map(link=>link.href)),
      ['https://example.com/news','https://example.net/releases']);
    assert.match(await page.locator('.assistant .metrics').innerText(), /Local/);
    assert.equal(await page.locator('.handoff-button').count(),0);
    await page.locator('.web-sources summary').click();
    assert.equal(await page.locator('.web-sources a').count(),2);
    assert.equal(await page.locator('.web-sources a').first().getAttribute('href'),'https://example.com/news');
    const cid = await page.evaluate(() => current);
    await page.screenshot({path:'test-results/web-chat-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.ok(await page.evaluate(() => document.querySelector('#search-web').getBoundingClientRect().bottom <= innerHeight), 'Search stays within the mobile viewport');
    await page.screenshot({path:'test-results/web-chat-mobile.png'});
    await page.goto(base + '/?conversation=' + cid); await idle();
    await page.getByText('Sources · 2', {exact:true}).waitFor();
    assert.equal(await search().getAttribute('aria-pressed'), 'false');
    await page.locator('.web-sources summary').click();
    assert.equal(await page.locator('.web-sources a').count(),2);
    await start('__web_slow__');
    await page.getByText('Searching the web…', {exact:true}).waitFor();
    await page.locator('.assistant').waitFor();
    await page.getByRole('button',{name:'Stop',exact:true}).click(); await idle();
    const stoppedId = await page.evaluate(() => current);
    const stopped = await (await fetch(`${base}/api/conversations/${stoppedId}`)).json();
    assert.equal(stopped.messages.at(-1).status,'stopped');
    assert.equal(stopped.messages.at(-1).content,'');
    await page.locator('.assistant').last().getByRole('button',{name:'Retry',exact:true}).click();
    await page.getByText('Sources · 2', {exact:true}).waitFor(); await idle();
    assert.equal((await (await fetch(`${base}/api/conversations/${stoppedId}`)).json()).messages.length,3);
    await start('__web_error__');
    await page.getByText('Synthetic search unavailable. Try again or turn Search off.', {exact:true}).first().waitFor(); await idle();
    assert.equal(await page.locator('.assistant .message-content').innerText(),'');
    await search().click(); await idle();
    await page.locator('#prompt').fill('An ordinary offline question'); await page.locator('#send').click(); await idle();
    assert.equal(sent.at(-1).web_search,false);
    assert.deepEqual(errors,[]); assert.deepEqual(external,[]);
    console.log('PASS: opt-in web search, local answer/citations/sources, persistence, mobile, Stop during search, retry, provider error and offline recovery');
  } finally { await page.close(); }
};
