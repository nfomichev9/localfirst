const assert = require('node:assert/strict');

module.exports = async function(browser, base) {
  const page = await browser.newPage({viewport:{width:1280,height:900}});
  const errors = [], external = [];
  let missingPreview = true, unconfiguredView = true;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (!request.url().startsWith(base)) { external.push(request.url()); return route.abort(); }
    if (url.pathname === '/api/settings' && request.method() === 'GET' && unconfiguredView) {
      const response = await route.fetch();
      return route.fulfill({json:{...await response.json(), provider_ready:false, frontier_model:null}});
    }
    if (url.pathname.endsWith('/handoff/preview') && missingPreview) {
      missingPreview = false;
      return route.fulfill({status:503, headers:{'Content-Type':'application/json','X-LocalFirst-Action':'connect-openai'},
        body:JSON.stringify({detail:'Connect your OpenAI API key in Settings to continue.'})});
    }
    return route.continue();
  });
  const idle = () => page.waitForFunction(() => !document.querySelector('#send').hidden && !document.querySelector('#send').disabled);
  const local = async prompt => {
    await page.locator('#prompt').fill(prompt); await page.locator('#send').click(); await idle();
  };
  const conversation = async cid => (await fetch(`${base}/api/conversations/${cid}`)).json();
  try {
    const configured = await fetch(base+'/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mode:'manual_handoff', daily_limit_cents:10, acknowledged:false})});
    assert.ok(configured.ok);
    await page.goto(base); await idle();
    await local('__manual_handoff__');
    const cid = await page.evaluate(() => current);
    await page.getByRole('button', {name:'Continue with OpenAI', exact:true}).click();
    await page.locator('.handoff-feedback').getByRole('link', {name:'Connect OpenAI', exact:true}).waitFor();
    assert.ok(!(await page.locator('#handoff-dialog').isVisible()));
    await page.locator('.handoff-feedback').getByRole('link', {name:'Connect OpenAI', exact:true}).click();
    await page.locator('#connection-editor').waitFor();
    await page.waitForFunction(() => !document.querySelector('#save-connection').disabled);
    await page.getByLabel('API key', {exact:true}).fill('invalid-key');
    await page.getByRole('button', {name:'Save connection', exact:true}).click();
    await page.getByText('OpenAI did not accept that API key. Check it and try again.', {exact:true}).waitFor();
    assert.equal(await page.locator('#connection-key').inputValue(), '');
    await page.getByLabel('API key', {exact:true}).fill('sk-browser-synthetic-key');
    await page.getByRole('button', {name:'Save connection', exact:true}).click();
    await page.getByText('OpenAI connection saved.', {exact:true}).waitFor();
    assert.equal(await page.locator('#connection-key').inputValue(), '');
    assert.equal(await page.locator('#readiness').innerText(), 'Configured');
    unconfiguredView = false;
    await page.getByRole('link', {name:'Back to chat'}).click();
    await page.waitForURL(`${base}/?conversation=${cid}`); await idle();
    await page.getByRole('button', {name:'Continue with OpenAI', exact:true}).click();
    await page.locator('#handoff-dialog').waitFor();
    assert.equal((await conversation(cid)).messages.filter(m=>m.telemetry?.provider==='openai').length,0);
    await page.locator('#handoff-dialog button[value="cancel"]').click();
    assert.equal((await conversation(cid)).messages.filter(m=>m.telemetry?.provider==='openai').length,0);
    await page.getByRole('button', {name:'Continue with OpenAI', exact:true}).click();
    await page.locator('#handoff-dialog').waitFor();
    await page.locator('#brief-fields textarea').nth(2).fill('Explain the corrected result in plain English.');
    assert.match(await page.locator('#outgoing-brief').innerText(),/Explain the corrected result/);
    const sent = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/handoff') && response.request().method()==='POST');
    await page.getByRole('button', {name:'Send to OpenAI', exact:true}).click();
    assert.equal((await sent).status(),200); await idle();
    const first = await conversation(cid);
    assert.equal(first.messages.length,3,'handoff adds an assistant continuation, not another user turn');
    assert.equal(first.messages[1].content,'Local draft for review.');
    assert.equal(first.messages[2].content,'Frontier reviewed the supplied brief.');
    assert.equal(first.messages[2].handoff_of,first.messages[1].id);
    assert.match(first.messages[2].handoff_brief,/Explain the corrected result/);
    assert.equal(await page.getByRole('button', {name:'Continue with OpenAI', exact:true}).count(),0);
    await page.reload(); await idle();
    assert.match(await page.locator('.assistant').last().innerText(),/Frontier reviewed/);
    await local('__prepare_slow__');
    await page.getByRole('button', {name:'Continue with OpenAI', exact:true}).click();
    await page.getByText('Preparing a brief on your Mac…', {exact:true}).waitFor();
    await page.getByRole('button', {name:'Stop', exact:true}).click(); await idle();
    await page.waitForTimeout(100);
    assert.ok(!(await page.locator('#handoff-dialog').isVisible()));
    assert.equal((await conversation(cid)).messages.filter(m=>m.telemetry?.provider==='openai').length,1);
    await local('__prepare_invalid__');
    await page.getByRole('button', {name:'Continue with OpenAI', exact:true}).last().click();
    await page.locator('#handoff-dialog').waitFor();
    assert.match(await page.locator('.preparation-note').innerText(), /could not format a brief/);
    assert.match(await page.locator('#outgoing-brief').innerText(), /Local draft for review/);
    await page.locator('#handoff-dialog button[value="cancel"]').click();
    await local('__manual_handoff__');
    await page.getByRole('button', {name:'Continue with OpenAI', exact:true}).last().click();
    await page.locator('#handoff-dialog').waitFor();
    await page.locator('#brief-fields textarea').nth(2).fill('simulate frontier failure');
    const failedSend = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/handoff') && response.request().method()==='POST');
    await page.getByRole('button', {name:'Send to OpenAI', exact:true}).click();
    assert.equal((await failedSend).status(),200); await idle();
    assert.match(await page.locator('.assistant').last().innerText(), /Synthetic cloud stream failed/);
    const failed = (await conversation(cid)).messages.at(-1);
    assert.equal(failed.status,'error'); assert.equal(failed.content,'Partial review');
    assert.deepEqual(errors,[]); assert.deepEqual(external,[]);
    console.log('PASS: handoff setup link/secure connection UI, exact chat return, prepare/edit/cancel/confirm, streaming, duplicates, Stop, malformed preparation and cloud failure');
  } catch (error) {
    console.error('Handoff browser state:',await page.evaluate(()=>({url:location.href,
      notice:document.querySelector('#notice')?.textContent, busy:typeof busy==='boolean'?busy:null,
      open:document.querySelector('#handoff-dialog')?.open,
      result:document.querySelector('#handoff-dialog')?.returnValue})));
    await page.screenshot({path:'test-results/handoff-failure.png',fullPage:true});
    throw error;
  } finally { await page.close(); }
};
