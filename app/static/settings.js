'use strict';
const $ = id => document.getElementById(id);
const form = $('settings'), dialog = $('settings-dialog');
const mode = $('mode'), limit = $('limit'), consent = $('consent'), acknowledged = $('acknowledged');
const save = $('save-settings'), reset = $('reset-settings');
const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
const returnConversation = new URLSearchParams(location.search).get('conversation');
const returnTo = returnConversation ? '/?conversation=' + encodeURIComponent(returnConversation) : '/';
document.querySelector('.close-button').href = returnTo;
let saved = null, ready = false, saving = false, budget = null, connecting = false;
const descriptions = {
  always_local: 'Replies are generated on this computer.',
  manual_handoff: 'Start locally. Review and confirm before sending a brief to OpenAI.',
  automatic_handoff: 'Start locally. OpenAI may help when more reasoning is needed.',
  always_frontier: 'Send chat context directly to OpenAI for each reply.'
};
const cents = () => Math.round(Number(limit.value) * 100);
const dirty = () => saved && (mode.value !== saved.mode || !limit.validity.valid || cents() !== saved.daily_limit_cents);

function setStatus(text = '', error = false) {
  $('status').textContent = text;
  $('status').dataset.error = String(error);
}
function showSection(section, focus = false) {
  const selected = tabs.find(tab => tab.dataset.section === section) || tabs[0];
  tabs.forEach(tab => {
    const active = tab === selected;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    $(tab.getAttribute('aria-controls')).hidden = !active;
  });
  history.replaceState(null, '', '#' + selected.dataset.section);
  if (focus) selected.focus();
}
tabs.forEach((tab, index) => {
  tab.onclick = () => showSection(tab.dataset.section);
  tab.onkeydown = event => {
    let next;
    if (['ArrowRight', 'ArrowDown'].includes(event.key)) next = (index + 1) % tabs.length;
    if (['ArrowLeft', 'ArrowUp'].includes(event.key)) next = (index + tabs.length - 1) % tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length - 1;
    if (next != null) { event.preventDefault(); showSection(tabs[next].dataset.section, true); }
  };
});
const mobile = matchMedia('(max-width: 620px)');
function orientTabs() { document.querySelector('[role="tablist"]').setAttribute('aria-orientation', mobile.matches ? 'horizontal' : 'vertical'); }
mobile.addEventListener('change', orientTabs); orientTabs();
dialog.addEventListener('cancel', event => { event.preventDefault(); location.assign(returnTo); });
dialog.showModal();
showSection(location.hash.slice(1));

function renderBudget() {
  const valid = budget && Number.isFinite(budget.reserved_or_charged);
  $('today-usage').textContent = valid ? `$${budget.reserved_or_charged.toFixed(4)}` : 'Unavailable';
  const cap = saved ? saved.daily_limit_cents / 100 : 0;
  $('budget-progress').hidden = !valid || cap <= 0;
  if (valid && cap > 0) {
    $('usage-progress').max = cap;
    $('usage-progress').value = Math.min(cap, budget.reserved_or_charged);
    $('budget-caption').textContent = budget.unresolved_estimate > 0
      ? `Includes $${budget.unresolved_estimate.toFixed(4)} awaiting final usage. Saved daily limit: $${cap.toFixed(2)}.`
      : `Saved daily limit: $${cap.toFixed(2)}.`;
  }
}
function update() {
  const changed = Boolean(dirty());
  consent.hidden = !changed || !['automatic_handoff', 'always_frontier'].includes(mode.value);
  acknowledged.required = !consent.hidden;
  $('mode-description').textContent = descriptions[mode.value] || 'Choose a response mode.';
  save.disabled = !saved || saving || connecting || !changed;
  reset.disabled = !saved || saving || connecting || !changed;
  mode.disabled = limit.disabled = acknowledged.disabled = !saved || saving || connecting;
  $('edit-connection').disabled = !saved || saving || connecting;
  $('change-state').textContent = !saved ? 'Settings unavailable' : saving ? 'Saving…' : changed ? 'Unsaved changes' : 'Saved on this device';
  $('change-state').dataset.dirty = String(changed);
  form.setAttribute('aria-busy', String(saving));
}
form.addEventListener('input', () => { setStatus(); update(); });
mode.addEventListener('change', () => { acknowledged.checked = false; setStatus(); update(); });
reset.onclick = () => {
  if (!saved || saving) return;
  mode.value = saved.mode;
  limit.value = (saved.daily_limit_cents / 100).toFixed(2);
  acknowledged.checked = false;
  setStatus('Unsaved changes discarded.'); update();
};

async function loadSettings() {
  setStatus(); $('retry-load').hidden = true;
  $('change-state').textContent = 'Loading settings…';
  form.setAttribute('aria-busy', 'true');
  try {
    const results = await Promise.allSettled([
      fetch('/api/settings').then(async response => {
        if (!response.ok) throw new Error('Could not load settings.');
        return response.json();
      }),
      fetch('/api/usage?days=1').then(async response => {
        if (!response.ok) throw new Error('Usage unavailable.');
        return response.json();
      })
    ]);
    budget = results[1].status === 'fulfilled' ? results[1].value.cloud_budget : null;
    if (results[0].status === 'rejected') throw results[0].reason;
    const data = results[0].value;
    saved = {mode: data.mode, daily_limit_cents: data.daily_limit_cents};
    ready = data.provider_ready;
    mode.value = data.mode;
    limit.value = (data.daily_limit_cents / 100).toFixed(2);
    acknowledged.checked = false;
    for (const option of mode.options) option.disabled = option.value !== 'always_local' && !ready;
    showConnection(data);
    renderBudget(); update();
  } catch {
    saved = null; update();
    $('readiness').textContent = 'Unavailable';
    $('retry-load').hidden = false;
    setStatus('Could not load settings. Check the local connection and try again.', true);
  }
}
$('retry-load').onclick = loadSettings;

function showConnection(data) {
  ready = data.provider_ready;
  $('readiness').textContent = ready ? 'Configured' : 'Not configured';
  $('readiness').dataset.ready = String(ready);
  $('frontier-model').textContent = data.frontier_model || '';
  $('provider-note').hidden = ready;
  $('edit-connection').textContent = ready ? 'Manage' : 'Connect';
  for (const option of mode.options) option.disabled = option.value !== 'always_local' && !ready;
}
async function editConnection() {
  const editor = $('connection-editor');
  editor.hidden = false;
  $('connection-heading').textContent = ready ? 'Manage OpenAI connection' : 'Connect OpenAI';
  $('connection-status').textContent = 'Loading connection options…';
  $('connection-key').placeholder = ready ? 'Leave blank to keep your saved key' : 'Paste your API key';
  $('connection-key').value = '';
  $('save-connection').disabled = true;
  try {
    const response = await fetch('/api/provider/connection');
    if (!response.ok) throw new Error('Could not load connection options. Close and try again.');
    const data = await response.json();
    $('connection-model').replaceChildren(...data.models.map(model => new Option(model.label, model.id)));
    $('connection-model').value = data.model;
    $('connection-model').disabled = false;
    $('save-connection').disabled = false;
    $('connection-status').textContent = data.error || '';
    $('connection-status').dataset.error = String(Boolean(data.error));
    editor.scrollIntoView({block:'nearest'}); $('connection-key').focus();
  } catch (error) { $('connection-status').textContent = error.message; }
}
$('edit-connection').onclick = editConnection;
$('cancel-connection').onclick = () => {
  if (connecting) return;
  $('connection-key').value = '';
  $('connection-editor').hidden = true;
  $('edit-connection').focus();
};
$('connection-key').addEventListener('keydown', event => {
  if (event.key === 'Enter') { event.preventDefault(); $('save-connection').click(); }
});
window.addEventListener('pagehide', () => { $('connection-key').value = ''; });
$('save-connection').onclick = async () => {
  if (connecting) return;
  const key = $('connection-key').value.trim();
  const message = $('connection-status');
  message.dataset.error = 'false';
  if (!key && !ready) { message.textContent = 'Enter an OpenAI API key.'; $('connection-key').focus(); return; }
  connecting = true; update();
  $('save-connection').disabled = $('cancel-connection').disabled = $('connection-key').disabled = $('connection-model').disabled = true;
  message.textContent = 'Checking your key and model access…';
  try {
    const response = await fetch('/api/provider/connection', {method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({key:key || null, model:$('connection-model').value})});
    const result = await response.json().catch(() => null);
    if (!response.ok || !result) throw new Error(typeof result?.detail === 'string' ? result.detail : 'Could not save the connection. Try again.');
    showConnection(result);
    $('connection-key').value = '';
    $('connection-editor').hidden = true;
    setStatus('OpenAI connection saved.');
    $('edit-connection').focus();
  } catch (error) {
    message.textContent = error.message === 'Failed to fetch' ? 'Could not reach the local app. Try again.' : error.message;
    message.dataset.error = 'true';
    $('connection-key').value = '';
  } finally {
    connecting = false;
    $('save-connection').disabled = $('cancel-connection').disabled = $('connection-key').disabled = $('connection-model').disabled = false;
    update();
  }
};

form.onsubmit = async event => {
  event.preventDefault();
  if (!saved || saving || connecting || !dirty()) return;
  setStatus();
  if (!limit.checkValidity()) {
    showSection('spending'); limit.reportValidity(); return;
  }
  if (mode.value !== 'always_local' && (!ready || cents() <= 0)) {
    showSection(!ready ? 'chat' : 'spending');
    setStatus(!ready ? 'Cloud help is not configured. Select Always local to continue.'
      : 'Set a positive daily limit to use cloud help.', true);
    (!ready ? mode : limit).focus(); return;
  }
  if (!consent.hidden && !acknowledged.checked) {
    setStatus('Confirm permission to send chat content to OpenAI before saving.', true);
    acknowledged.focus(); return;
  }
  const requested = {mode: mode.value, daily_limit_cents: cents(), acknowledged: acknowledged.checked};
  saving = true; update();
  try {
    const response = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(requested)});
    const result = await response.json().catch(() => null);
    if (!result) throw new Error('Could not save settings. Try again.');
    if (!response.ok) {
      const detail = typeof result.detail === 'string' ? result.detail : 'Could not save settings.';
      throw new Error(detail.includes('OPENAI_API_KEY') ? 'Cloud help needs configuration on this computer. Choose Always local to continue.' : detail);
    }
    saved = {mode: result.mode, daily_limit_cents: result.daily_limit_cents};
    mode.value = saved.mode;
    limit.value = (saved.daily_limit_cents / 100).toFixed(2);
    setStatus('Settings saved.'); renderBudget();
  } catch (error) {
    setStatus(error.message === 'Failed to fetch' ? 'Could not save settings. Check the local connection and try again.' : error.message, true);
  } finally { saving = false; update(); }
};
loadSettings().then(() => {
  if (saved && new URLSearchParams(location.search).get('connect') === 'openai') {
    showSection('chat'); editConnection();
  }
});
