'use strict';
const $ = id => document.getElementById(id);
let current = null, busy = false, controller = null, online = false, stopActiveStream = null;
let navigation = 0;
let routingMode = 'always_local';
let activeDocument = null, pendingDocument = null;
let webEnabled = false;
let modelsLoading = false;
const pdfMode = () => Boolean(activeDocument || pendingDocument);
const routingLabels = {always_local: 'Always local', manual_handoff: 'Manual handoff',
  automatic_handoff: 'Automatic handoff', always_frontier: 'Always frontier · sends to OpenAI'};
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: {'Content-Type': 'application/json', ...options.headers} });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const error = new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
    error.action = response.headers.get('X-LocalFirst-Action');
    throw error;
  }
  return response;
}
function notice(text = '') { $('notice').textContent = text; $('notice').hidden = !text; }
function controls() {
  $('send').hidden = busy; $('stop').hidden = !busy;
  $('stop').disabled = Boolean(controller?.signal.aborted) || !stopActiveStream;
  $('send').disabled = !online || modelsLoading; $('model').disabled = busy || !online || modelsLoading || (routingMode === 'always_frontier' && !pdfMode() && !webEnabled);
  $('new-chat').disabled = busy; $('refresh-models').disabled = busy;
  $('prompt').disabled = busy; $('thread').setAttribute('aria-busy', String(busy));
  $('attach-pdf').disabled = busy; $('pdf-file').disabled = busy; $('remove-pdf').disabled = busy;
  if (pdfMode()) webEnabled = false;
  $('search-web').disabled = busy || pdfMode() || modelsLoading;
  $('search-web').setAttribute('aria-pressed', String(webEnabled));
  $('web-search-note').hidden = !webEnabled;
  $('search-web').title = pdfMode() ? 'PDF conversations stay offline' : 'Search the web with this message';
  $('routing-mode').textContent = pdfMode() ? 'PDF · stays on this computer' : webEnabled ? 'Web search · answered locally' : routingLabels[routingMode];
  document.querySelectorAll('.handoff-button').forEach(b => { b.disabled = busy; b.hidden = pdfMode(); });
  document.querySelectorAll('#conversations button').forEach(b => b.disabled = busy);
  document.querySelectorAll('.retry-reply select, .retry-reply button').forEach(el => el.disabled = busy || !online);
}
function showDocument() {
  const document = pendingDocument || activeDocument;
  $('pdf-attachment').hidden = !document;
  $('remove-pdf').hidden = !pendingDocument;
  $('pdf-name').textContent = document ? `${document.filename} · ${document.page_count} pages` : '';
  const missing = document?.unreadable_pages.length || 0;
  $('pdf-note').textContent = document ? `${pendingDocument ? 'Ready to send' : 'Available for follow-up questions'} · Text only${missing ? ` · ${missing} pages have no readable text` : ''}` : '';
  controls();
}
async function uploadPDF(file) {
  if (busy || !file) return;
  if (!file.name.toLowerCase().endsWith('.pdf')) { notice('Choose a PDF file (.pdf).'); return; }
  if (file.size > 10 * 1024 * 1024) { notice('Choose a PDF smaller than 10 MB.'); return; }
  busy = true; controller = new AbortController(); stopActiveStream = () => { controller.abort(); controls(); };
  $('generation-status').textContent = `Reading ${file.name} on your computer…`; notice(); controls();
  try {
    if (!current) current = (await (await api('/api/conversations', {method:'POST', signal:controller.signal})).json()).id;
    const document = await (await api(`/api/conversations/${current}/documents?filename=${encodeURIComponent(file.name)}`,
      {method:'POST', headers:{'Content-Type':'application/pdf'}, body:file, signal:controller.signal})).json();
    if (pendingDocument) await api(`/api/conversations/${current}/documents/${pendingDocument.id}`, {method:'DELETE'});
    pendingDocument = document; showDocument();
    await refreshModels(); await refreshList();
  } catch (error) { notice(error.name === 'AbortError' ? 'PDF reading stopped.' : error.message); }
  finally {
    busy = false; controller = null; stopActiveStream = null;
    $('generation-status').textContent = ''; $('pdf-file').value = ''; controls(); $('prompt').focus();
  }
}
$('attach-pdf').onclick = () => $('pdf-file').click();
$('search-web').onclick = () => { webEnabled = !webEnabled; refreshModels(); controls(); $('prompt').focus(); };
$('pdf-file').onchange = () => uploadPDF($('pdf-file').files[0]);
$('remove-pdf').onclick = async () => {
  if (busy || !pendingDocument) return;
  $('remove-pdf').disabled = true;
  try {
    await api(`/api/conversations/${current}/documents/${pendingDocument.id}`, {method:'DELETE'});
    pendingDocument = null; showDocument(); await refreshModels();
  } catch (error) { notice(error.message); }
  finally { controls(); }
};
const dropArea = document.querySelector('main');
dropArea.addEventListener('dragover', event => {
  if (Array.from(event.dataTransfer.types).includes('Files')) {
    event.preventDefault(); if (!busy) $('composer').classList.add('file-dragover');
  }
});
dropArea.addEventListener('dragleave', event => {
  if (!dropArea.contains(event.relatedTarget)) $('composer').classList.remove('file-dragover');
});
dropArea.addEventListener('drop', event => {
  event.preventDefault(); $('composer').classList.remove('file-dragover');
  if (event.dataTransfer.files.length !== 1) { notice('Attach one PDF at a time.'); return; }
  uploadPDF(event.dataTransfer.files[0]);
});
function syncRetryModels(select, preferred = select.value) {
  select.replaceChildren(...Array.from($('model').options, option => option.cloneNode(true)));
  if (online) select.value = Array.from(select.options).some(option => option.value === preferred) ? preferred : $('model').value;
}
async function refreshModels() {
  modelsLoading = true; controls();
  try {
    const settings = await (await api('/api/settings')).json();
    routingMode = settings.mode;
    $('routing-mode').textContent = routingLabels[routingMode];
    const frontier = routingMode === 'always_frontier' && !pdfMode() && !webEnabled;
    $('model-label').textContent = frontier ? 'OpenAI model' : 'Local model';
    $('model').setAttribute('aria-label', frontier ? 'Configured OpenAI model' : 'Select installed model');
    $('refresh-models').hidden = frontier;
    if (frontier) {
      $('model').replaceChildren(new Option(settings.frontier_model || 'OpenAI model not configured', settings.frontier_model || ''));
      online = settings.provider_ready && settings.daily_limit_cents > 0;
      $('connection').textContent = online ? 'OpenAI configured' : 'OpenAI setup required';
      $('connection-dot').classList.toggle('offline', !online);
      notice(online ? '' : 'Configure OpenAI and a positive limit or change modes in Settings.');
      controls();
      return;
    }
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
  } finally { modelsLoading = false; controls(); }
  document.querySelectorAll('.retry-reply select').forEach(select => syncRetryModels(select, select.value || select.dataset.preferred));
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
    element.textContent = record.status === 'streaming' ? `${record.model || 'Local model'} · Generating…` : `${record.model || 'Local model'} · ${seconds(record.latency_ms)} · Detailed telemetry unavailable`;
    return;
  }
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  const total = t.input_tokens != null && t.output_tokens != null ? t.input_tokens + t.output_tokens : null;
  const cost = t.external_api_cost == null ? 'Cost unavailable' : `$${t.external_api_cost.toFixed(4)} API`;
  summary.textContent = `${t.model} · ${t.execution_location === 'local' ? 'Local' : 'Cloud'} · ${seconds(t.latency_ms)} · ${number(total)} tokens · ${cost} · ${t.status}`;
  const more = document.createElement('div');
  more.textContent = `Input: ${number(t.input_tokens)} · Output: ${number(t.output_tokens)} · Generation: ${number(t.tokens_per_second)} tok/s · First token: ${seconds(t.ttft_ms)} · Provider: ${t.provider}`;
  if (record.context_messages != null) more.textContent += ` · Messages sent: ${record.context_messages} · Earlier messages omitted: ${record.omitted_messages}`;
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
  const heading = document.createElement('div'); heading.className = 'message-heading';
  heading.textContent = m.role === 'user' ? 'YOU' : m.retry_of ? '↗ LOCALFIRST · RETRY' : '↗ LOCALFIRST';
  const content = document.createElement('div'); content.className = 'message-content'; content.textContent = m.content;
  const metrics = document.createElement('div'); metrics.className = 'metrics';
  const error = document.createElement('div'); error.className = 'message-error';
  const source = document.createElement('div'); source.className = 'document-coverage'; source.hidden = true;
  const webSources = document.createElement('details'); webSources.className = 'web-sources'; webSources.hidden = true;
  article.append(heading, content, source, webSources, metrics, error); $('messages').append(article);
  let state = {}, entered = false;
  function update(record) {
    const previous = state;
    state = {...state, ...record};
    if (state.web_context && state.web_context !== previous.web_context) {
      const search = state.web_context;
      webSources.hidden = false;
      const summary = document.createElement('summary');
      summary.textContent = search.sources.length ? `Sources · ${search.sources.length}` : 'Web search';
      const note = document.createElement('p');
      note.textContent = `${search.provider} · “${search.query}” · Search excerpts${search.retrieved_at ? ' · Retrieved ' + new Date(search.retrieved_at).toLocaleString() : ''}`;
      const list = document.createElement('ol');
      for (const source of search.sources) {
        let url;
        try { url = new URL(source.url); } catch { continue; }
        if (!['http:', 'https:'].includes(url.protocol)) continue;
        const item = document.createElement('li'), link = document.createElement('a');
        link.textContent = source.title; link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        const domain = document.createElement('span'); domain.textContent = url.hostname.replace(/^www\./, '');
        item.append(link, domain); list.append(item);
      }
      webSources.replaceChildren(summary, note, list);
    }
    if (state.document || state.document_context) {
      source.hidden = false;
      const pdf = state.document || state.document_context;
      const pages = pdf.pages_used;
      source.textContent = state.document ? `PDF · ${pdf.filename} · ${pdf.page_count} pages`
        : `${pdf.filename} · ${pdf.excerpts ? `Excerpts from pages ${pages.join(', ')} of ${pdf.page_count}` : 'All extracted text'} · Text only${pdf.unreadable_pages.length ? ` · No readable text on pages ${pdf.unreadable_pages.join(', ')}` : ''}`;
    }
    if (state.content != null && state.content !== previous.content) {
      if (m.role === 'assistant') {
        renderMarkdown(content, state.content, state.web_context?.sources || []);
        if (m.status === 'streaming' && state.content && !entered) {
          entered = true; article.classList.add('response-enter');
        }
      } else content.textContent = state.content;
    }
    if (m.role === 'assistant') {
      if (state.telemetry !== previous.telemetry || state.status !== previous.status || state.model !== previous.model || state.context_messages !== previous.context_messages) metricsBar(metrics, state);
      const errorText = state.error || (state.status === 'stopped' ? 'Stopped — incomplete response.' : state.status === 'streaming' ? 'Generating…' : state.status === 'error' ? 'Response failed.' : '');
      if (error.textContent !== errorText) error.textContent = errorText;
      const provider = state.telemetry?.provider || state.provider || 'ollama';
      heading.textContent = `${provider === 'openai' ? 'OpenAI' : 'Ollama'} · ${state.model || 'Model'}${state.retry_of ? ' · RETRY' : ''}`;
      if (state.handoff_brief && !article.querySelector('.sent-brief')) {
        const details = document.createElement('details'); details.className = 'sent-brief';
        const summary = document.createElement('summary'); summary.textContent = 'Sent to OpenAI';
        const reason = document.createElement('p'); reason.textContent = state.route_reason;
        const brief = document.createElement('pre'); brief.textContent = state.handoff_brief;
        details.append(summary, reason, brief); article.append(details);
      }
      if (state.status === 'complete' && state.routing_mode === 'manual_handoff' && provider === 'ollama' && !pdfMode()
          && !state.has_handoff && !article.querySelector('.handoff-button')) {
        const button = document.createElement('button'); button.className = 'handoff-button';
        button.type = 'button'; button.textContent = 'Continue with OpenAI'; button.disabled = busy;
        button.onclick = () => previewHandoff(state.id, button);
        article.append(button);
      }
      const retry = article.querySelector('.retry-reply');
      const canRetry = state.id && !state.handoff_of && ['stopped', 'error'].includes(state.status);
      if (retry) retry.hidden = !canRetry;
      if (canRetry && !retry) {
        const form = document.createElement('form'); form.className = 'retry-reply';
        const model = document.createElement('select');
        model.setAttribute('aria-label', 'Model for retry');
        model.dataset.preferred = state.requested_model || state.model || '';
        syncRetryModels(model, model.dataset.preferred);
        const button = document.createElement('button'); button.textContent = 'Retry';
        form.append(model, button); article.append(form);
        form.onsubmit = event => {
          event.preventDefault();
          if (article === $('messages').lastElementChild) generate({retryOf:state.id, selectedModel:model.value});
        };
        model.disabled = button.disabled = busy || !online;
      }
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
  const request = ++navigation;
  const c = await (await api(`/api/conversations/${id}`)).json();
  if (request !== navigation) return;
  current = id; $('messages').replaceChildren(); $('welcome').hidden = !!c.messages.length;
  webEnabled = false;
  pendingDocument = null; activeDocument = c.document || null; showDocument(); await refreshModels();
  $('conversation-title').textContent = c.title; c.messages.forEach(addMessage);
  document.body.classList.remove('sidebar-open'); $('menu').setAttribute('aria-expanded', 'false');
  await refreshList();
  if (request === navigation) { scrollDown(true); if (online) notice(); }
}
function newChat() {
  if (busy) return;
  navigation++;
  current = null; $('messages').replaceChildren(); $('welcome').hidden = false;
  webEnabled = false;
  pendingDocument = null; activeDocument = null; showDocument(); refreshModels();
  $('conversation-title').textContent = 'New conversation'; notice();
  document.body.classList.remove('sidebar-open'); $('menu').setAttribute('aria-expanded', 'false');
  refreshList().catch(e => notice(e.message)); $('prompt').focus();
}
$('composer').onsubmit = event => {
  event.preventDefault();
  const content = $('prompt').value.trim() || (pdfMode() ? 'Summarize this PDF and cite page numbers.' : '');
  if (content) generate({content, selectedModel:$('model').value});
};
async function previewHandoff(mid, button) {
  if (busy) return;
  let feedback = button.parentElement.querySelector('.handoff-feedback');
  if (!feedback) {
    feedback = document.createElement('div'); feedback.className = 'handoff-feedback';
    feedback.setAttribute('role', 'status'); button.insertAdjacentElement('afterend', feedback);
  }
  feedback.replaceChildren();
  busy = true; controller = new AbortController();
  stopActiveStream = () => controller.abort();
  $('generation-status').textContent = 'Preparing a brief on your Mac…';
  controls(); notice();
  const cid = current;
  let preview;
  try {
    const path = `/api/conversations/${cid}/messages/${mid}/handoff/preview`;
    preview = await (await api(path, {method: 'POST', signal: controller.signal})).json();
  } catch (error) {
    if (error.name !== 'AbortError') {
      notice(error.message); feedback.textContent = error.message + ' ';
      if (['connect-openai', 'set-cloud-limit'].includes(error.action)) {
        const link = document.createElement('a');
        link.href = error.action === 'connect-openai'
          ? `/settings?connect=openai&conversation=${encodeURIComponent(cid)}` : '/settings#spending';
        link.textContent = error.action === 'connect-openai' ? 'Connect OpenAI' : 'Set cloud limit';
        feedback.append(link);
      }
    }
    return;
  } finally {
    busy = false; controller = null; stopActiveStream = null;
    $('generation-status').textContent = '';
    controls();
  }
  const dialog = $('handoff-dialog');
  let preparationNote = dialog.querySelector('.preparation-note');
  if (!preparationNote) {
    preparationNote = document.createElement('p'); preparationNote.className = 'preparation-note';
    dialog.querySelector('h2').insertAdjacentElement('afterend', preparationNote);
  }
  preparationNote.textContent = preview.preparation_note || '';
  preparationNote.hidden = !preview.preparation_note;
  const fields = $('brief-fields');
  const names = ['summary', 'facts_and_constraints', 'task', 'latest_request', 'source_excerpts'];
  const inputs = {};
  fields.replaceChildren();
  names.forEach(name => {
    const label = document.createElement('label');
    label.textContent = name.replaceAll('_', ' ');
    const field = document.createElement('textarea');
    field.value = preview.brief[name];
    inputs[name] = field;
    label.append(field); fields.append(label);
  });
  function updateEstimate() {
    const text = names.map(name => {
      const heading = name.charAt(0).toUpperCase() + name.slice(1).replaceAll('_', ' ');
      return `${heading}\n${inputs[name].value}`;
    }).join('\n\n');
    $('outgoing-brief').textContent = text;
    const bytes = new TextEncoder().encode(text).length;
    const valid = bytes <= 8192 && inputs.summary.value.trim() && inputs.task.value.trim();
    const charge = (preview.fixed_nanodollars + bytes * preview.input_nanodollars_per_byte) / 1e9;
    $('brief-estimate').textContent = valid ? `Estimated maximum charge $${charge.toFixed(6)}`
      : 'Supply a summary and task and keep the brief within 8 KB.';
    $('confirm-handoff').disabled = !valid;
  }
  fields.oninput = updateEstimate;
  dialog.returnValue = '';
  dialog.onclose = () => {
    if (dialog.returnValue !== 'send' || current !== cid) return;
    const brief = Object.fromEntries(names.map(name => [name, inputs[name].value]));
    generate({handoffOf: mid, handoff: {...brief, token: preview.token}, handoffButton: button});
  };
  updateEstimate();
  dialog.showModal();
}
async function generate({content, retryOf, selectedModel, handoffOf, handoff, handoffButton}) {
  if (busy || modelsLoading || (!online && !handoffOf)) return;
  navigation++;
  busy = true; controller = new AbortController(); notice();
  let message = null, streaming = null, accumulated = '', finished = false, cancelled = false;
  const attached = !retryOf && !handoffOf ? pendingDocument : null;
  stopActiveStream = () => {
    cancelled = true;
    streaming?.close();
    controller.abort();
    controls();
  };
  controls();
  try {
    if (!current) current = (await (await api('/api/conversations', {method: 'POST', signal: controller.signal})).json()).id;
    $('generation-status').textContent = handoffOf || (routingMode === 'always_frontier' && !pdfMode() && !webEnabled) ? 'Generating with OpenAI…'
      : webEnabled && !retryOf ? 'Searching the web…'
      : retryOf ? 'Retrying on your Mac…' : 'Generating on your Mac…';
    const endpoint = handoffOf ? `messages/${handoffOf}/handoff` : retryOf ? `messages/${retryOf}/retry` : 'chat';
    const response = await api(`/api/conversations/${current}/${endpoint}`, {method:'POST', signal:controller.signal,
      body:JSON.stringify(handoff || {content, model:selectedModel, expected_mode:routingMode, document_id:attached?.id,
        ...(!retryOf ? {web_search:webEnabled} : {})})});
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    function consume(line) {
      if (cancelled || !line.trim()) return;
      const packet = JSON.parse(line);
      if (packet.type === 'start') {
        finished = false; accumulated = '';
        if (packet.handoff_of) {
          $('generation-status').textContent = 'Generating with OpenAI…';
          if (handoffButton) handoffButton.remove();
        }
        if (!retryOf && !packet.handoff_of) {
          addMessage({role:'user', content, document:attached});
          if (attached) { activeDocument = attached; pendingDocument = null; showDocument(); }
          $('prompt').value = ''; $('prompt').style.height = '';
        }
        message = addMessage({id:packet.message_id, role:'assistant', content:'', model:packet.model,
          requested_model:selectedModel, status:'streaming', retry_of:retryOf,
          context_messages:packet.context_messages, omitted_messages:packet.omitted_messages,
          provider:packet.provider, routing_mode:packet.routing_mode, handoff_of:packet.handoff_of,
          route_reason:packet.route_reason, handoff_brief:packet.handoff_brief, document_context:packet.document_context,
          web_context:packet.web_context});
        message.id = packet.message_id;
        streaming = createStreamBuffer(raw => { message.update({content:raw}); scrollDown(); });
        scrollDown(true);
      }
      if (packet.type === 'start' && packet.omitted_messages) notice(`${packet.omitted_messages} older messages are saved but omitted from this request.`);
      if (packet.type === 'preparing') $('generation-status').textContent = 'Assessing the reply on your Mac…';
      if (packet.type === 'handoff_status') notice(packet.message);
      if (packet.type === 'web_status') $('generation-status').textContent = packet.message;
      if (packet.type === 'web_sources') {
        message.update(packet);
        $('generation-status').textContent = 'Answering from search results on your Mac…';
        if (packet.omitted_messages) notice(`${packet.omitted_messages} older messages are saved but omitted from this request.`);
      }
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
    if (!finished && !cancelled) throw new Error('Connection ended before the response completed.');
  } catch (error) {
    streaming?.close();
    controller.abort();
    const stopped = error.name === 'AbortError';
    const text = stopped ? 'Stopped — incomplete response.' : error.message;
    if (message && !finished) message.update({status:stopped?'stopped':'error', error:text});
    if (!stopped) notice(text);
  } finally {
    streaming?.close(); stopActiveStream = null; controls();
    try {
      if (current) {
        // The server may still be saving a stopped attempt when the browser aborts.
        let conversation, saved;
        for (let attempt = 0; attempt < 20; attempt++) {
          conversation = await (await api(`/api/conversations/${current}`)).json();
          saved = conversation.messages.find(m => m.id === message?.id);
          if (!saved || saved.status !== 'streaming') break;
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        $('conversation-title').textContent = conversation.title;
        activeDocument = conversation.document || null; showDocument();
        if (saved && saved.status !== 'streaming') {
          if (cancelled && saved.status === 'stopped') message.update({telemetry:saved.telemetry});
          else message.update(saved);
        }
        await refreshList();
      }
    } catch (error) { notice(error.message); }
    finally {
      busy = false; controller = null; $('generation-status').textContent = ''; controls();
      if (!selectingThreadText() && !retryOf) $('prompt').focus();
    }
  }
}
$('stop').onclick = () => { if (controller) { $('generation-status').textContent = 'Stopping…'; stopActiveStream(); } };
$('new-chat').onclick = newChat;
$('refresh-models').onclick = refreshModels;
$('menu').onclick = () => { const open = document.body.classList.toggle('sidebar-open'); $('menu').setAttribute('aria-expanded', String(open)); };
document.addEventListener('keydown', e => { if (e.key === 'Escape') { document.body.classList.remove('sidebar-open'); $('menu').setAttribute('aria-expanded', 'false'); } });
$('prompt').addEventListener('input', () => { $('prompt').style.height = 'auto'; $('prompt').style.height = Math.min($('prompt').scrollHeight, 160) + 'px'; });
$('prompt').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('composer').requestSubmit(); } });
Promise.all([refreshModels(), refreshList()]).then(() => {
  const cid = new URLSearchParams(location.search).get('conversation');
  if (cid) return openConversation(cid);
}).catch(e => notice(e.message));
