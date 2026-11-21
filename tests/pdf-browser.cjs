const assert = require('node:assert/strict');
const fs = require('node:fs');

module.exports = async function(browser, base) {
  const page = await browser.newPage();
  const errors = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    if (route.request().url().startsWith(base)) route.continue();
    else { external.push(route.request().url()); route.abort(); }
  });
  try {
    await page.goto(base);
    await page.waitForFunction(() => !document.querySelector('#send').disabled);
    const before = await (await fetch(base + '/api/usage?days=0')).json();
    await page.locator('#pdf-file').setInputFiles('tests/fixtures/brief.pdf');
    await page.getByText('Ready to send · Text only', {exact:true}).waitFor();
    await page.waitForFunction(() => !document.querySelector('#attach-pdf').disabled);
    assert.match(await page.locator('#pdf-name').innerText(), /brief.pdf · 2 pages/);
    assert.ok(await page.getByRole('button',{name:'Search',exact:true}).isDisabled());
    assert.match(await page.locator('#routing-mode').innerText(), /stays on this computer/);
    await page.getByRole('button', {name:'Remove PDF attachment'}).click();
    await page.locator('#pdf-attachment').waitFor({state:'hidden'});
    // Drag/drop uses the same real upload/parser path as the picker.
    const bytes = Array.from(fs.readFileSync('tests/fixtures/brief.pdf'));
    await page.evaluate(bytes => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(bytes)], 'dropped.pdf', {type:'application/pdf'}));
      document.querySelector('main').dispatchEvent(new DragEvent('drop', {dataTransfer:transfer, bubbles:true}));
    }, bytes);
    await page.getByText('Ready to send · Text only', {exact:true}).waitFor();
    await page.waitForFunction(() => !document.querySelector('#attach-pdf').disabled);
    assert.equal((await (await fetch(base + '/api/usage?days=0')).json()).overview.requests, before.overview.requests);
    await page.locator('#send').click(); // Attachment-only Send asks for a summary.
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    assert.match(await page.locator('.assistant .message-content').innerText(), /18400/);
    assert.match(await page.locator('.assistant .document-coverage').innerText(), /All extracted text/);
    assert.match(await page.locator('.user .document-coverage').innerText(), /dropped.pdf/);
    assert.ok(await page.getByRole('button', {name:'Remove PDF attachment'}).isHidden());
    await page.locator('#prompt').fill('Who is the lead?'); await page.locator('#send').click();
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    assert.match(await page.locator('.assistant').last().innerText(), /Riley/);
    const cid = await page.evaluate(() => current);
    await page.reload(); await page.locator('#conversations button').first().click();
    await page.getByText('Available for follow-up questions · Text only', {exact:true}).waitFor();
    assert.match(await page.locator('#pdf-name').innerText(), /dropped.pdf/);
    assert.match(await page.locator('.assistant').last().innerText(), /Riley/);
    await page.locator('#pdf-file').setInputFiles({name:'bad.pdf', mimeType:'application/pdf', buffer:Buffer.from('invalid')});
    await page.getByText('This file is not a readable PDF.', {exact:true}).waitFor();
    assert.match(await page.locator('#pdf-name').innerText(), /dropped.pdf/);
    await page.locator('#pdf-file').setInputFiles({name:'notes.pptx', mimeType:'application/octet-stream', buffer:Buffer.from('invalid')});
    await page.getByText('Choose a PDF file (.pdf).', {exact:true}).waitFor();
    await page.locator('#prompt').fill('__pdf_slow__'); await page.locator('#send').click();
    await page.locator('.assistant').last().getByText('Generating…', {exact:true}).waitFor();
    await page.getByRole('button', {name:'Stop', exact:true}).click();
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    assert.match(await page.locator('.assistant').last().innerText(), /Stopped/);
    await page.locator('.assistant').last().getByRole('combobox', {name:'Model for retry'}).selectOption('second:local');
    await page.locator('.assistant').last().getByRole('button', {name:'Retry', exact:true}).click();
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    assert.match(await page.locator('.assistant').last().innerText(), /18400/);
    assert.match(await page.locator('.assistant').last().locator('.document-coverage').innerText(), /dropped.pdf/);
    assert.equal((await (await fetch(`${base}/api/conversations/${cid}`)).json()).document.filename, 'dropped.pdf');
    await page.setViewportSize({width:390,height:844});
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'PDF composer fits mobile');
    const buttons = await page.evaluate(() => ({attach:document.querySelector('#attach-pdf').getBoundingClientRect().top,
      send:document.querySelector('#send').getBoundingClientRect().top}));
    assert.ok(Math.abs(buttons.attach - buttons.send) < 5, 'mobile PDF and send controls fit on one row');
    await page.screenshot({path:'test-results/pdf-chat-mobile.png', fullPage:true});
    await page.setViewportSize({width:1280,height:900});
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({path:'test-results/pdf-chat-desktop.png', fullPage:true});
    await page.getByRole('button', {name:'New chat'}).click();
    await page.locator('#pdf-attachment').waitFor({state:'hidden'});
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    console.log('PASS: PDF picker/drop, removal, local parsing, summary, follow-up, restart display, errors, Stop/retry, mobile and zero external requests');
  } finally { await page.close(); }
};
