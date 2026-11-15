'use strict';
const $ = id => document.getElementById(id);
let current = null, busy = false, controller = null, online = false, stopActiveStream = null;
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: {'Content-Type': 'application/json', ...options.headers} });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
  }
  return response;
}
function notice(text = '') { $('notice').textContent = text; $('notice').hidden = !text; }
function controls() {
  $('send').hidden = busy; $('stop').hidden = !busy;
  $('send').disabled = !online; $('model').disabled = busy || !online;
  $('new-chat').disabled = busy; $('refresh-models').disabled = busy;
  $('prompt').disabled = busy; $('thread').setAttribute('aria-busy', String(busy));
  document.querySelectorAll('#conversations button, .suggestions button').forEach(b => b.disabled = busy);
}
async function refreshModels() {
  try {
    const previous = $('model').value;
    const data = await (await api('/api/models')).json();
    $('model').replaceChildren();
    data.models.forEach(name => { const option = document.createElement('option'); option.value = name; option.textContent = data.labels?.[name] || name; option.title = name; $('model').append(option); });
    online = data.models.length > 0;
    if (data.models.includes(previous)) $('model').value = previous;
    else if (data.models.includes(data.default)) $('model').value = data.default;
    if (!online) { const option = document.createElement('option'); option.textContent = 'No installed models'; $('model').append(option); }
    $('connection').textContent = online ? 'Ollama connected' : 'No models installed';
    $('connection-dot').classList.toggle('offline', !online);
    notice(online ? '' : 'Ollama is running, but no models are installed. Install a model yourself, then refresh.');
  } catch (error) {
    online = false; $('connection').textContent = 'Ollama unavailable';
    $('connection-dot').classList.add('offline'); notice(error.message);
    $('model').replaceChildren(new Option('Ollama unavailable', ''));
  }
  controls();
}
async function refreshList() {
  const list = await (await api('/api/conversations')).json();
  $('conversations').replaceChildren();
  if (!list.length) { const p = document.createElement('p'); p.className = 'empty-list'; p.textContent = 'A fresh start. Your conversations will appear here.'; $('conversations').append(p); }
  list.forEach(c => {
    const button = document.createElement('button'); button.textContent = c.title;
    button.title = c.title; button.classList.toggle('active', c.id === current); button.disabled = busy;
    button.onclick = () => openConversation(c.id).catch(e => notice(e.message));
    $('conversations').append(button);
  });
}
const seconds = value => value == null ? '—' : `${(value / 1000).toFixed(2)}s`;
const number = value => value == null ? '—' : value.toLocaleString(undefined, {maximumFractionDigits:1});
function metricsBar(element, record) {
  element.replaceChildren();
  const t = record.telemetry;
  if (!t) {
    element.textContent = record.status === 'streaming' ? `${record.model || 'Local model'} · Generating…` : `${record.model || 'Local model'} · Detailed telemetry unavailable for this response`;
    return;
  }
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  const total = t.input_tokens != null && t.output_tokens != null ? t.input_tokens + t.output_tokens : null;
  const cost = t.external_api_cost == null ? 'Cost unavailable' : `$${t.external_api_cost.toFixed(4)} API`;
  summary.textContent = `${t.model} · ${t.execution_location === 'local' ? 'Local' : 'Cloud'} · ${seconds(t.latency_ms)} · ${number(total)} tokens · ${cost} · ${t.status}`;
  const more = document.createElement('div');
  more.textContent = `Input: ${number(t.input_tokens)} · Output: ${number(t.output_tokens)} · Generation: ${number(t.tokens_per_second)} tok/s · First token: ${seconds(t.ttft_ms)} · Provider: ${t.provider}`;
  details.append(summary, more); element.append(details);
  if (t.status === 'success') {
    const feedback = document.createElement('div'); feedback.className = 'feedback';
    const label = document.createElement('span'); label.textContent = 'Was this useful?'; feedback.append(label);
    [[1,'👍','Helpful'],[-1,'👎','Not helpful']].forEach(([value, icon, title]) => {
      const button = document.createElement('button'); button.textContent = icon;
      button.title = title; button.setAttribute('aria-label', title); button.setAttribute('aria-pressed', String(t.feedback === value));
      button.onclick = async () => {
        button.disabled = true;
        try {
          const next = t.feedback === value ? null : value;
          await api(`/api/inference/${t.request_id}/feedback`, {method:'PUT', body:JSON.stringify({value:next})});
          t.feedback = next; metricsBar(element, record);
        } catch (e) { notice(e.message); button.disabled = false; }
      };
      feedback.append(button);
    });
    element.append(feedback);
  }
}
function addMessage(m) {
  $('welcome').hidden = true;
  const article = document.createElement('article'); article.className = `message ${m.role}`;
  const heading = document.createElement('div'); heading.className = 'message-heading'; heading.textContent = m.role === 'user' ? 'YOU' : '↗ LOCALFIRST';
  const content = document.createElement('div'); content.className = 'message-content'; content.textContent = m.content;
  const metrics = document.createElement('div'); metrics.className = 'metrics';
  const error = document.createElement('div'); error.className = 'message-error';
  article.append(heading, content, metrics, error); $('messages').append(article);
  let state = {}, entered = false;
  function update(record) {
    const previous = state;
    state = {...state, ...record};
    if (state.content != null && state.content !== previous.content) {
      if (m.role === 'assistant') {
        renderMarkdown(content, state.content);
        if (m.status === 'streaming' && state.content && !entered) {
          entered = true; article.classList.add('response-enter');
        }
      } else content.textContent = state.content;
    }
    if (m.role === 'assistant') {
      if (state.telemetry !== previous.telemetry || state.status !== previous.status || state.model !== previous.model) metricsBar(metrics, state);
      const errorText = state.error || (state.status === 'stopped' ? 'Stopped — incomplete response.' : state.status === 'streaming' ? 'Generating…' : state.status === 'error' ? 'Response failed.' : '');
      if (error.textContent !== errorText) error.textContent = errorText;
    }
  }
  update(m); return {content, update};
}
let followOutput = true;
$('thread').addEventListener('scroll', () => {
  const thread = $('thread');
  followOutput = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 64;
}, {passive:true});
function selectingThreadText() {
  const selection = window.getSelection();
  return selection && !selection.isCollapsed && ($('thread').contains(selection.anchorNode) || $('thread').contains(selection.focusNode));
}
function scrollDown(force = false) {
  if (force) followOutput = true;
  if (force || (followOutput && !selectingThreadText())) $('thread').scrollTop = $('thread').scrollHeight;
}
async function openConversation(id) {
  if (busy) return;
  const c = await (await api(`/api/conversations/${id}`)).json();
  current = id; $('messages').replaceChildren(); $('welcome').hidden = !!c.messages.length;
  $('conversation-title').textContent = c.title; c.messages.forEach(addMessage);
  document.body.classList.remove('sidebar-open'); $('menu').setAttribute('aria-expanded', 'false');
  await refreshList(); scrollDown(true); notice();
}
function newChat() {
  if (busy) return;
  current = null; $('messages').replaceChildren(); $('welcome').hidden = false;
  $('conversation-title').textContent = 'New conversation'; notice();
  document.body.classList.remove('sidebar-open'); $('menu').setAttribute('aria-expanded', 'false');
  refreshList().catch(e => notice(e.message)); $('prompt').focus();
}
$('composer').onsubmit = async event => {
  event.preventDefault();
  const text = $('prompt').value.trim(); if (!text || busy || !online) return;
  busy = true; controller = new AbortController(); controls(); notice();
  const selectedModel = $('model').value;
  let message = null, streaming = null, accumulated = '', finished = false, cancelled = false;
  stopActiveStream = () => {
    cancelled = true;
    streaming?.close();
    controller.abort();
  };
  try {
    if (!current) current = (await (await api('/api/conversations', {method: 'POST', signal: controller.signal})).json()).id;
    addMessage({role:'user', content:text});
    message = addMessage({role:'assistant', content:'', model:selectedModel, status:'streaming'});
    streaming = createStreamBuffer(raw => { message.update({content:raw}); scrollDown(); });
    $('prompt').value = ''; $('prompt').style.height = '';
    $('generation-status').textContent = 'Generating on your Mac…'; scrollDown(true);
    const response = await api(`/api/conversations/${current}/chat`, {method:'POST', signal:controller.signal, body:JSON.stringify({content:text, model:selectedModel})});
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    function consume(line) {
      if (cancelled || finished || !line.trim()) return;
      const packet = JSON.parse(line);
      if (packet.type === 'start') message.id = packet.message_id;
      if (packet.type === 'start' && packet.omitted_messages) notice(`Context includes the latest 12 saved messages plus your prompt. ${packet.omitted_messages} older messages are saved but omitted from this request.`);
      if (packet.type === 'delta') { accumulated += packet.content; streaming.set(accumulated); }
      if (packet.type === 'error') throw new Error(packet.message);
      if (packet.type === 'done') { streaming.close(); finished = true; message.update({...packet, status:'complete'}); scrollDown(); }
    }
    while (true) {
      const {done, value} = await reader.read();
      buffer += decoder.decode(value, {stream:!done});
      const lines = buffer.split('\n'); buffer = lines.pop(); lines.forEach(consume);
      if (done) { if (buffer.trim()) consume(buffer); break; }
    }
    if (!finished) throw new Error('Connection ended before the response completed.');
  } catch (error) {
    streaming?.close();
    controller.abort();
    const stopped = error.name === 'AbortError';
    const text = stopped ? 'Stopped — incomplete response.' : error.message;
    if (message) message.update({model:selectedModel, status:stopped?'stopped':'error', error:text});
    if (!stopped) notice(text);
  } finally {
    streaming?.close(); stopActiveStream = null;
    busy = false; controller = null; $('generation-status').textContent = ''; controls();
    if (!selectingThreadText()) $('prompt').focus();
    if (current) {
      // Reload only the title/list here: preserve streamed output until the next open.
      try { const c = await (await api(`/api/conversations/${current}`)).json(); $('conversation-title').textContent = c.title;
        const saved = c.messages.find(m => m.id === message?.id);
        if (saved && !cancelled) message.update(saved);
        else if (saved?.telemetry && saved.telemetry.status !== 'running') message.update({telemetry:saved.telemetry});
        await refreshList(); }
      catch (error) { notice(error.message); }
    }
  }
};
$('stop').onclick = () => { if (controller) { $('generation-status').textContent = 'Stopping…'; stopActiveStream(); } };
$('new-chat').onclick = newChat;
$('refresh-models').onclick = refreshModels;
$('menu').onclick = () => { const open = document.body.classList.toggle('sidebar-open'); $('menu').setAttribute('aria-expanded', String(open)); };
document.addEventListener('keydown', e => { if (e.key === 'Escape') { document.body.classList.remove('sidebar-open'); $('menu').setAttribute('aria-expanded', 'false'); } });
$('prompt').addEventListener('input', () => { $('prompt').style.height = 'auto'; $('prompt').style.height = Math.min($('prompt').scrollHeight, 160) + 'px'; });
$('prompt').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('composer').requestSubmit(); } });
document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => { $('prompt').value = button.dataset.prompt; $('prompt').focus(); });
Promise.all([refreshModels(), refreshList()]).catch(e => notice(e.message));
