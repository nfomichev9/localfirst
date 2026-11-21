const assert = require('node:assert/strict');

module.exports = async function(browser, base) {
  const page = await browser.newPage({viewport:{width:1280,height:900}});
  const errors = [], external = [], updates = [];
  let state = {mode:'always_local', daily_limit_cents:100, provider_ready:true, frontier_model:'gpt-6-luna'};
  let failLoad = false, failSave = false, failUsage = false, malformedSave = false;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (!request.url().startsWith(base)) { external.push(request.url()); return route.abort(); }
    if (url.pathname === '/api/settings') {
      if (request.method() === 'GET') {
        return route.fulfill({status:failLoad ? 503 : 200, json:failLoad ? {detail:'Unavailable'} : state});
      }
      const change = request.postDataJSON(); updates.push(change);
      if (failSave) return route.fulfill({status:503, json:{detail:'Settings temporarily unavailable.'}});
      if (malformedSave) return route.fulfill({status:503, contentType:'text/html', body:'Unavailable'});
      state = {...state, mode:change.mode, daily_limit_cents:change.daily_limit_cents};
      return route.fulfill({json:state});
    }
    if (url.pathname === '/api/usage') return route.fulfill({status:failUsage ? 503 : 200,
      json:{cloud_budget:{reserved_or_charged:.12, unresolved_estimate:.02, limit:state.daily_limit_cents/100}}});
    return route.continue();
  });
  const saved = () => page.getByText('Settings saved.', {exact:true}).waitFor();
  const ready = () => page.waitForFunction(() => document.querySelector('#settings').getAttribute('aria-busy') === 'false');
  const paint = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  try {
    await page.goto(base + '/');
    await page.getByRole('link', {name:'Settings', exact:true}).click();
    assert.equal(new URL(page.url()).pathname, '/settings');
    await ready();
    assert.ok(await page.locator('#settings-dialog').evaluate(element =>
      getComputedStyle(element).borderRadius === '16px'), 'Settings stylesheet loaded through home navigation');
    assert.equal(await page.getByRole('tab').count(), 2);
    assert.equal(await page.locator('#mode').inputValue(), 'always_local');
    assert.ok(await page.getByRole('button', {name:'Save settings', exact:true}).isDisabled());
    assert.ok(await page.locator('#consent').isHidden());
    assert.equal(await page.locator('#readiness').innerText(), 'Configured');
    await page.screenshot({path:'test-results/settings-chat-desktop.png', fullPage:true});
    await page.getByRole('tab', {name:'Chat', exact:true}).focus();
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.getByRole('tab', {name:'Spending', exact:true}).getAttribute('aria-selected'), 'true');
    assert.equal(await page.locator('#today-usage').innerText(), '$0.1200');
    assert.match(await page.locator('#budget-caption').innerText(), /\$0.0200 awaiting final usage/);
    await page.screenshot({path:'test-results/settings-spending-desktop.png', fullPage:true});
    await page.setViewportSize({width:390,height:844}); await paint();
    assert.equal(await page.getByRole('tablist').getAttribute('aria-orientation'), 'horizontal');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path:'test-results/settings-spending-mobile.png', fullPage:true});
    await page.getByRole('tab', {name:'Chat', exact:true}).click();
    await page.screenshot({path:'test-results/settings-chat-mobile.png', fullPage:true});
    await page.setViewportSize({width:1280,height:900}); await paint();
    await page.getByRole('tab', {name:'Spending', exact:true}).click();
    await page.getByLabel('Daily cloud spending limit (USD)').fill('2.50');
    assert.equal(await page.locator('#change-state').innerText(), 'Unsaved changes');
    await page.getByRole('button', {name:'Reset', exact:true}).click();
    assert.equal(await page.locator('#limit').inputValue(), '1.00');
    assert.equal(updates.length, 0, 'reset/navigation never writes settings');
    await page.getByLabel('Daily cloud spending limit (USD)').fill('');
    assert.equal(await page.locator('#change-state').innerText(), 'Unsaved changes');
    await page.getByRole('button', {name:'Reset', exact:true}).click();
    await page.getByRole('tab', {name:'Chat', exact:true}).click();
    await page.getByRole('combobox', {name:'Response mode'}).selectOption('automatic_handoff');
    assert.ok(await page.locator('#consent').isVisible());
    await page.getByRole('button', {name:'Save settings', exact:true}).click();
    await page.getByText('Confirm permission to send chat content to OpenAI before saving.', {exact:true}).waitFor();
    assert.equal(updates.length, 0);
    await page.locator('#acknowledged').check();
    await page.getByRole('tab', {name:'Spending', exact:true}).click();
    await page.getByLabel('Daily cloud spending limit (USD)').fill('2.50');
    await page.getByRole('button', {name:'Save settings', exact:true}).click(); await saved();
    assert.deepEqual(updates.at(-1), {mode:'automatic_handoff', daily_limit_cents:250, acknowledged:true});
    await page.reload(); await ready();
    assert.equal(await page.locator('#limit').inputValue(), '2.50');
    assert.equal(await page.getByRole('tab', {name:'Spending', exact:true}).getAttribute('aria-selected'), 'true');
    assert.ok(await page.locator('#consent').isHidden(), 'unchanged saved policy does not show an unchecked permission prompt');
    assert.ok(!(await page.locator('#acknowledged').isChecked()), 'reload does not invent consent');
    await page.getByLabel('Daily cloud spending limit (USD)').fill('3.00');
    await page.locator('#acknowledged').check(); failSave = true;
    await page.getByRole('button', {name:'Save settings', exact:true}).click();
    await page.getByText('Settings temporarily unavailable.', {exact:true}).waitFor();
    assert.equal(await page.locator('#limit').inputValue(), '3.00');
    assert.ok(await page.getByRole('button', {name:'Save settings', exact:true}).isEnabled());
    failSave = false;
    malformedSave = true;
    await page.getByRole('button', {name:'Save settings', exact:true}).click();
    await page.getByText('Could not save settings. Try again.', {exact:true}).waitFor();
    assert.equal(await page.locator('#limit').inputValue(), '3.00');
    malformedSave = false;
    await page.getByRole('button', {name:'Save settings', exact:true}).click(); await saved();
    const count = updates.length;
    await page.getByLabel('Daily cloud spending limit (USD)').fill('100.01');
    await page.getByRole('tab', {name:'Chat', exact:true}).click();
    await page.getByRole('button', {name:'Save settings', exact:true}).click();
    assert.equal(await page.getByRole('tab', {name:'Spending', exact:true}).getAttribute('aria-selected'), 'true');
    assert.ok(await page.locator('#limit').evaluate(input => input.validity.rangeOverflow));
    assert.equal(updates.length, count, 'invalid cap never reaches server');
    await page.getByRole('button', {name:'Reset', exact:true}).click();
    state.provider_ready = false;
    await page.reload(); await ready();
    await page.getByRole('tab', {name:'Chat', exact:true}).click();
    assert.equal(await page.locator('#mode').inputValue(), 'automatic_handoff', 'preserve a configured mode when provider becomes unavailable');
    assert.ok(await page.locator('#mode option[value="always_frontier"]').isDisabled());
    assert.equal(await page.locator('#readiness').innerText(), 'Not configured');
    assert.ok(!(await page.locator('#provider-note').innerText()).includes('API_KEY'));
    await page.getByRole('combobox', {name:'Response mode'}).selectOption('always_local');
    await page.getByRole('button', {name:'Save settings', exact:true}).click(); await saved();
    assert.equal(updates.at(-1).mode, 'always_local');
    failUsage = true;
    await page.reload(); await ready();
    await page.getByRole('tab', {name:'Spending', exact:true}).click();
    assert.equal(await page.locator('#today-usage').innerText(), 'Unavailable');
    assert.ok(await page.locator('#budget-progress').isHidden());
    failLoad = true;
    await page.reload();
    await page.getByRole('button', {name:'Try again', exact:true}).waitFor();
    assert.ok(await page.getByRole('button', {name:'Save settings', exact:true}).isDisabled());
    failLoad = false;
    await page.getByRole('button', {name:'Try again', exact:true}).click(); await ready();
    assert.ok(await page.locator('#mode').isEnabled());
    await page.keyboard.press('Escape');
    await page.waitForURL(base + '/');
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    console.log('PASS: settings tabs/keyboard, save/reset/persistence, consent, limits, unavailable provider/usage, error recovery, mobile, Escape, zero external requests');
  } finally { await page.close(); }
};
