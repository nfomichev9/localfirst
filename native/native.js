import {openChat} from './chat.js';

const model = {id: 'gemma-270m', name: 'Gemma 3 270M'};
const $ = id => document.getElementById(id);
const onboarding = new URLSearchParams(location.search).has('onboarding');
let active;
let selection;

async function api(path, body) {
  const options = body === undefined ? {cache: 'no-store', signal: AbortSignal.timeout(5000)} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  };
  const response = await fetch('/api/native/' + path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'LocalFirst could not complete setup.');
  return result;
}

async function check() {
  const status = await api('status');
  if (status.status !== 'ready') throw new Error(status.error || 'Gemma is still loading. Check Model setup.');
}

async function generate(messages, onChunk) {
  const controller = new AbortController();
  active = controller;
  try {
    const response = await fetch('/api/native/generate', {
      method: 'POST', signal: controller.signal, headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({messages}),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'The native chat service could not start a reply.');
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';
    try {
      for (;;) {
        const {done, value} = await reader.read();
        if (done) throw new Error('The native model disconnected before completing the reply.');
        buffer += value;
        let end;
        while ((end = buffer.indexOf('\n')) !== -1) {
          const packet = JSON.parse(buffer.slice(0, end));
          buffer = buffer.slice(end + 1);
          if (packet.type === 'delta') onChunk(packet.content);
          if (packet.type === 'done') return packet.metrics;
          if (packet.type === 'error') throw new Error(packet.message);
        }
      }
    } finally {
      await reader.cancel().catch(() => {});
    }
  } finally {
    active = null;
  }
}

function showStatus(message = '', error = false) {
  const status = $('setup-status');
  status.textContent = message;
  status.dataset.error = String(error);
  status.hidden = !message;
}

function setBusy(busy) {
  for (const id of ['folder-path', 'check-folder', 'choose-folder', 'model-file', 'load-model']) $(id).disabled = busy;
  $('model-form').setAttribute('aria-busy', String(busy));
}

function setSelection(folder, files, selected) {
  selection = files.length ? folder : null;
  $('model-file').replaceChildren(...files.map(name => new Option(name, name)));
  if (files.includes(selected)) $('model-file').value = selected;
  $('model-options').hidden = !selection;
}

async function scan(folder) {
  const previous = $('model-file').value;
  setSelection(null, []);
  if (!folder) throw new Error('Enter the path to your Gemma model folder.');
  const result = await api('models', {folder});
  $('folder-path').value = result.folder;
  setSelection(result.folder, result.files, previous);
  if (!result.files.length) showStatus('No GGUF files found in this folder.', true);
  else $('model-file').focus();
}

async function runSetup(action) {
  setBusy(true);
  showStatus();
  try { await action(); }
  catch (error) { showStatus(error.message, true); }
  finally { setBusy(false); }
}

async function openNativeChat() {
  if (onboarding) {
    const url = new URL(location.href);
    url.searchParams.delete('onboarding');
    history.replaceState(null, '', url);
  }
  $('refresh-models').title = 'Model setup';
  $('refresh-models').setAttribute('aria-label', 'Model setup');
  await openChat(model, {check, generate, stop: () => active?.abort()}, {
    provider: 'llama.cpp', manageModels: () => location.assign('?onboarding=1'),
  });
}

async function waitForModel(openWhenReady) {
  $('load-progress').hidden = false;
  showStatus('Loading Gemma 3 270M…');
  try {
    let status;
    do {
      await new Promise(resolve => setTimeout(resolve, 250));
      status = await api('status');
    } while (status.status === 'loading');
    $('back-to-chat').hidden = status.status !== 'ready';
    if (status.error) showStatus(status.error, true);
    else if (status.status === 'ready' && openWhenReady) await openNativeChat();
    else showStatus('Gemma 3 270M is ready.');
  } finally { $('load-progress').hidden = true; }
}

$('model-form').onsubmit = event => {
  event.preventDefault();
  runSetup(() => scan($('folder-path').value.trim()));
};
$('folder-path').oninput = () => {
  setSelection(null, []);
  showStatus();
};
$('choose-folder').onclick = () => runSetup(async () => {
  showStatus('Choose a folder in the macOS dialog.');
  const {folder} = await api('folder', {});
  showStatus();
  if (folder) await scan(folder);
});
$('load-model').onclick = () => runSetup(async () => {
  await api('setup', {folder: selection, filename: $('model-file').value});
  await waitForModel(true);
});

async function start() {
  const status = await api('status');
  if (status.status === 'ready' && !onboarding) {
    await openNativeChat();
    return;
  }
  $('startup-screen').hidden = true;
  $('setup-screen').hidden = false;
  $('back-to-chat').hidden = status.status !== 'ready';
  if (status.folder) {
    $('folder-path').value = status.folder;
    if (status.filename) setSelection(status.folder, [status.filename]);
  }
  if (status.error) showStatus(status.error, true);
  if (status.status === 'loading') await runSetup(() => waitForModel(!onboarding));
  else $('folder-path').focus();
}

start().catch(error => {
  $('startup-screen').setAttribute('aria-busy', 'false');
  $('startup-status').textContent = error.message;
});
