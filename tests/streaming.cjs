const assert = require('node:assert/strict');

module.exports = async function streamingChecks(browser, base) {
  const page = await browser.newPage({viewport:{width:1100,height:720}});
  try {
    await page.goto(base);
    await page.waitForFunction(() => !document.querySelector('#send').disabled);
    // Deterministic frame scheduling: bursts coalesce, closing flushes even if no
    // frame fires (background tab), and late data cannot change a closed stream.
    const buffering = await page.evaluate(() => {
      const request = window.requestAnimationFrame, cancel = window.cancelAnimationFrame;
      let callbacks = new Map(), id = 0, paints = [];
      window.requestAnimationFrame = callback => {callbacks.set(++id, callback); return id;};
      window.cancelAnimationFrame = key => callbacks.delete(key);
      try {
        const buffer = createStreamBuffer(raw => paints.push(raw));
        buffer.set('A'); buffer.set('AB'); buffer.set('AB🌿');
        const pendingFrames = callbacks.size, beforeFrame = paints.length;
        const callback = [...callbacks.values()][0]; callbacks.clear(); callback();
        buffer.set('AB🌿 café'); buffer.close(); buffer.set('late');
        return {pendingFrames, beforeFrame, paints, remaining:callbacks.size};
      } finally {window.requestAnimationFrame = request; window.cancelAnimationFrame = cancel;}
    });
    assert.deepEqual(buffering, {pendingFrames:1,beforeFrame:0,paints:['AB🌿','AB🌿 café'],remaining:0});
    await page.evaluate(() => {
      const fixtures = [
        '# Heading\n\nA **bold** and *italic* paragraph with `code`.\n\n- One\n- Two\n\n| Name | Value |\n| --- | --- |\n| Local | Yes |\n\n```python\nprint("🌿")\n```',
        'Read [the link][ref].\n\n[ref]: https://example.com\n\n> A quotation\n\n---\n\nEnd.'
      ];
      for (const raw of fixtures) {
        const incremental = document.createElement('div'), complete = document.createElement('div');
        for (let i=0; i<=raw.length; i++) renderMarkdown(incremental, raw.slice(0, i));
        renderMarkdown(complete, raw);
        if (incremental.innerHTML !== complete.innerHTML) throw Error('Incremental Markdown differs from complete rendering');
      }
      const root = document.createElement('div'); document.body.append(root);
      renderMarkdown(root, 'Select this growing paragraph');
      const text = root.firstChild.firstChild;
      const range = document.createRange(); range.setStart(text, 0); range.setEnd(text, 6);
      getSelection().removeAllRanges(); getSelection().addRange(range);
      renderMarkdown(root, 'Select this growing paragraph with more text');
      if (getSelection().toString() !== 'Select' || text !== root.firstChild.firstChild) throw Error('Appending clears selection');
      getSelection().removeAllRanges(); root.remove();
    });
    await page.evaluate(() => {
      const original = renderMarkdown;
      window.streamPaints = 0;
      window.renderMarkdown = (...args) => { window.streamPaints++; return original(...args); };
    });
    await page.locator('#prompt').fill('__streaming_stress__'); await page.locator('#send').click();
    await page.locator('.assistant pre code').waitFor();
    await page.waitForFunction(() => document.querySelector('.assistant .message-content').textContent.includes('Batch 2'));
    await page.evaluate(() => {
      const root = document.querySelector('.assistant .message-content');
      window.stableParagraph = root.querySelector('p');
      window.stableCode = root.querySelector('pre');
      window.stableMetrics = document.querySelector('.assistant .metrics').firstChild;
      document.querySelector('#thread').scrollTop = 0;
      const range = document.createRange(); range.setStart(stableParagraph.firstChild, 0); range.setEnd(stableParagraph.firstChild, 6);
      getSelection().removeAllRanges(); getSelection().addRange(range);
    });
    await page.waitForFunction(() => document.querySelector('.assistant .message-content').textContent.includes('Batch 12'));
    const during = await page.evaluate(() => ({
      paragraph:stableParagraph === document.querySelector('.assistant .message-content p'),
      code:stableCode === document.querySelector('.assistant pre'),
      metrics:stableMetrics === document.querySelector('.assistant .metrics').firstChild,
      selection:getSelection().toString(), top:document.querySelector('#thread').scrollTop
    }));
    assert.deepEqual(during, {paragraph:true,code:true,metrics:true,selection:'Select',top:0});
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    const completed = await page.evaluate(async () => {
      const conversation = await (await fetch('/api/conversations/'+current)).json();
      const raw = conversation.messages.at(-1).content;
      const expected = document.createElement('div'); renderMarkdown(expected, raw);
      const actual = document.querySelector('.assistant .message-content');
      return {same:actual.innerHTML === expected.innerHTML, paints:streamPaints, raw,
        selection:getSelection().toString(), top:document.querySelector('#thread').scrollTop};
    });
    assert.equal(completed.same, true, 'final Markdown matches the complete persisted raw response');
    assert.ok(completed.paints < 65, `bursts are batched (${completed.paints} paints for 92 deltas)`);
    for (let i=0; i<30; i++) assert.equal(completed.raw.split(`Batch ${i} — café 🌿. `).length-1, 1);
    assert.ok(completed.raw.endsWith('**Complete.**'));
    assert.equal(completed.selection, 'Select'); assert.equal(completed.top, 0);
    // Resume following by returning to the bottom, then verify a second long reply.
    await page.evaluate(() => getSelection().removeAllRanges());
    await page.locator('#new-chat').click();
    await page.locator('#prompt').fill('__streaming_stress__'); await page.locator('#send').click();
    await page.waitForFunction(() => document.querySelector('.assistant .message-content')?.textContent.includes('Batch 4'));
    const following = await page.locator('#thread').evaluate(el => el.scrollHeight-el.scrollTop-el.clientHeight);
    assert.ok(following < 64, 'follows output when user stays at the bottom');
    await page.locator('#stop').click();
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    const stopped = await page.locator('.assistant .message-content').innerHTML();
    await page.waitForTimeout(200);
    assert.equal(await page.locator('.assistant .message-content').innerHTML(), stopped, 'Stop freezes the displayed response');
    assert.match(await page.locator('.assistant .message-error').innerText(), /Stopped/);
    assert.equal(await page.getByLabel('Model for retry').inputValue(), 'test:local');
    assert.equal(await page.getByRole('button', {name:'Retry', exact:true}).isEnabled(), true);
    // Errors also flush a final partial batch without converting it to success.
    await page.locator('#new-chat').click();
    await page.locator('#prompt').fill('__streaming_error__'); await page.locator('#send').click();
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    assert.match(await page.locator('.assistant .message-content').innerText(), /Batch 5/);
    assert.match(await page.locator('.assistant .message-error').innerText(), /interrupted/);
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await page.locator('.assistant').evaluate(el => getComputedStyle(el).animationName), 'none');
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const model = page.getByLabel('Model for retry');
    const retry = page.getByRole('button', {name:'Retry', exact:true});
    await page.route('**/api/models', route => route.fulfill({status:503, json:{detail:'Ollama offline'}}));
    await page.getByRole('button',{name:'Refresh installed models'}).click();
    await page.getByText('Ollama offline',{exact:true}).waitFor();
    assert.equal(await retry.isDisabled(), true);
    await page.unroute('**/api/models');
    await page.route('**/api/models', route => route.fulfill({json:{models:[]}}));
    await page.getByRole('button',{name:'Refresh installed models'}).click();
    await page.getByText('No models installed',{exact:true}).waitFor();
    assert.equal(await retry.isDisabled(), true);
    await page.unroute('**/api/models');
    await page.getByRole('button',{name:'Refresh installed models'}).click();
    await model.selectOption('second:local');
    await page.locator('#prompt').fill('Unsent draft');
    await retry.click();
    await page.waitForFunction(() => !document.querySelector('#send').hidden);
    assert.equal(await page.locator('#prompt').inputValue(), 'Unsent draft');
    assert.equal(await page.locator('.message.user').count(), 1);
    assert.equal(await page.locator('.message.assistant').count(), 2);
    assert.match(await page.locator('.assistant').last().locator('.message-heading').innerText(), /RETRY/);
    assert.match(await page.locator('.assistant').last().locator('.metrics summary').innerText(), /second:local.*success/);
    const retryConversation = await page.evaluate(() => current);
    await page.goto(base+'/?conversation='+retryConversation);
    await page.locator('.assistant').last().locator('.metrics summary').waitFor();
    assert.equal(await page.locator('.message.assistant').count(), 2);
    assert.match(await page.locator('.assistant').first().locator('.message-error').innerText(), /interrupted/);
    console.log('PASS: streaming stability, cancellation, error partials, retry model switching, offline and empty catalogs, persistence, mobile chat');
  } finally {await page.close();}
};
