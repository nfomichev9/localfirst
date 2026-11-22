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
  automatic_handoff: 'Cloud help enabled', always_frontier: 'Sends to OpenAI'};
let replyDetails = readReplyDetails();
async function api(path, options = {}) {
  const request = window.localfirstBrowser?.request || fetch;
  const response = await request(path, { ...options, headers: {'Content-Type': 'application/json', ...options.headers} });
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
  $('routing-mode').hidden = !pdfMode() && !webEnabled && !['automatic_handoff', 'always_frontier'].includes(routingMode);
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
    const localStatus = window.localfirstBrowser?.provider === 'llama.cpp' ? 'llama.cpp ready' : 'Model ready on device';
    $('connection').textContent = online ? (window.localfirstBrowser ? localStatus : 'Ollama connected') : 'No models installed';
    notice(online ? '' : 'Ollama is running, but no models are installed. Install a model yourself, then refresh.');
  } catch (error) {
    const unavailable = window.localfirstBrowser ? 'Local model unavailable' : 'Ollama unavailable';
    online = false; $('connection').textContent = unavailable;
    notice(error.message);
    $('model').replaceChildren(new Option(unavailable, ''));
  } finally { modelsLoading = false; controls(); }
  document.querySelectorAll('.retry-reply select').forEach(select => syncRetryModels(select, select.value || select.dataset.preferred));
  controls();
}
async function refreshList() {
  const list = await (await api('/api/conversations')).json();
  if (!window.localfirstBrowser) $('settings-link').href = '/settings?v=5' + (current ? '&conversation=' + encodeURIComponent(current) : '');
  $('conversations').replaceChildren();
  list.forEach(c => {
    const button = document.createElement('button'); button.textContent = c.title;
    button.title = c.title; button.classList.toggle('active', c.id === current); button.disabled = busy;
    if (c.id === current) button.setAttribute('aria-current', 'true');
    button.onclick = () => openConversation(c.id).catch(e => notice(e.message));
    $('conversations').append(button);
  });
}
const seconds = value => value == null ? '—' : `${(value / 1000).toFixed(2)}s`;
const number = value => value == null ? '—' : value.toLocaleString(undefined, {maximumFractionDigits:1});
function replyButton(label, icon) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'icon-button';
  button.title = label;
  button.setAttribute('aria-label', label);
  button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + icon + '</svg>';
  return button;
}
const copyIcon = '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>';
const thumbIcon = '<path d="M7.5 10.5h-3v9h3zm0 8.5h10a2 2 0 0 0 2-1.7l1-5.5a2 2 0 0 0-2-2.3h-4l.6-3.4A2 2 0 0 0 13 4l-5.5 6.5"/>';
function renderReplyActions(element, record) {
  const detailsOpen = element.querySelector('details')?.open || false;
  element.replaceChildren();
  element.hidden = record.status !== 'complete';
  if (element.hidden) return;

  const copy = replyButton('Copy reply', copyIcon);
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(record.content);
      copy.classList.add('is-copied');
      copy.title = 'Copied';
      $('chat-status').textContent = 'Reply copied.';
      setTimeout(() => { copy.classList.remove('is-copied'); copy.title = 'Copy reply'; }, 1400);
    } catch {
      notice('Could not copy the reply. You can select the text and copy it.');
    }
  };
  element.append(copy);
  const t = record.telemetry;
  if (t?.status === 'success') {
    const votes = [
      [1, replyButton('Helpful', thumbIcon)],
      [-1, replyButton('Not helpful', '<g transform="rotate(180 12 12)">' + thumbIcon + '</g>')],
    ];
    const updateVotes = () => votes.forEach(([value, button]) => button.setAttribute('aria-pressed', String(t.feedback === value)));
    for (const [value, button] of votes) {
      button.onclick = async () => {
        votes.forEach(([, control]) => { control.disabled = true; });
        try {
          const next = t.feedback === value ? null : value;
          await api(`/api/inference/${t.request_id}/feedback`, {method:'PUT', body:JSON.stringify({value:next})});
          t.feedback = next;
          updateVotes();
        } catch (error) { notice(error.message); }
        finally { votes.forEach(([, control]) => { control.disabled = false; }); }
      };
      element.append(button);
    }
    updateVotes();
  }

  if (!Object.values(replyDetails).some(Boolean)) return;
  const details = document.createElement('details');
  details.className = 'metrics';
  details.open = detailsOpen;
  const summary = document.createElement('summary');
  summary.textContent = 'Details';
  const entries = document.createElement('dl');
  entries.className = 'reply-detail-list';
  function entry(label, text) {
    const row = document.createElement('div');
    const term = document.createElement('dt');
    const value = document.createElement('dd');
    term.textContent = label;
    value.textContent = text;
    row.append(term, value);
    entries.append(row);
  }
  if (replyDetails.model) {
    entry('Model', t?.model || record.model || '—');
    const labels = {openai: 'OpenAI · Cloud', browser: 'Browser · On device', 'llama.cpp': 'llama.cpp · Local'};
    entry('Provider', labels[t?.provider || record.provider] || 'Ollama · Local');
  }
  if (replyDetails.timing) {
    entry('Response time', seconds(t?.latency_ms ?? record.latency_ms));
    entry('First token', seconds(t?.ttft_ms));
    entry('Generation speed', t?.tokens_per_second == null ? '—' : number(t.tokens_per_second) + ' tok/s');
  }
  if (replyDetails.tokens) {
    entry('Input tokens', number(t?.input_tokens ?? record.prompt_tokens));
    entry('Output tokens', number(t?.output_tokens ?? record.output_tokens));
  }
  details.append(summary, entries);
  element.append(details);
}
function addMessage(m) {
  $('welcome').hidden = true;
  const article = document.createElement('article'); article.className = `message ${m.role}`;
  article.setAttribute('aria-label', m.role === 'user' ? 'You' : m.retry_of ? 'LocalFirst retry' : 'LocalFirst');
  const cloudLabel = document.createElement('div'); cloudLabel.className = 'cloud-reply';
  cloudLabel.textContent = 'OpenAI'; cloudLabel.hidden = true;
  const content = document.createElement('div'); content.className = 'message-content';
  const actions = document.createElement('div'); actions.className = 'reply-actions'; actions.hidden = true;
  const error = document.createElement('div'); error.className = 'message-error';
  const source = document.createElement('div'); source.className = 'document-coverage'; source.hidden = true;
  const webSources = document.createElement('details'); webSources.className = 'web-sources'; webSources.hidden = true;
  if (m.role === 'assistant') article.append(cloudLabel);
  article.append(content, source, webSources, error);
  if (m.role === 'assistant') article.append(actions);
  $('messages').append(article);
  const reveal = m.status === 'streaming' ? createReplyReveal(content) : null;
  let state = {}, entered = false;
  actions.addEventListener('replydetailschange', () => renderReplyActions(actions, state));
  function update(record) {
    const previous = state;
    state = {...state, ...record};
    if (state.web_context && state.web_context !== previous.web_context) {
      const search = state.web_context;
      const summary = document.createElement('summary');
      summary.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7h13M7 12h13M7 17h13M4 7h.01M4 12h.01M4 17h.01"/></svg>';
      const label = document.createElement('span');
      summary.append(label);
      const list = document.createElement('ol');
      for (const source of search.sources) {
        let url;
        try { url = new URL(source.url); } catch { continue; }
        if (!['http:', 'https:'].includes(url.protocol)) continue;
        const item = document.createElement('li'), link = document.createElement('a');
        link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        const number = document.createElement('span');
        number.className = 'source-number'; number.textContent = source.number;
        const description = document.createElement('span');
        description.className = 'source-description';
        const title = document.createElement('strong');
        title.textContent = source.title || url.hostname;
        const domain = document.createElement('small');
        domain.textContent = url.hostname.replace(/^www\./, '');
        description.append(title, domain);
        link.append(number, description);
        item.append(link); list.append(item);
      }
      const count = list.childElementCount;
      webSources.hidden = !count && !search.retrieved_at;
      label.textContent = count ? `Sources · ${count}` : 'Web search';
      const panel = document.createElement('div');
      panel.className = 'source-panel';
      const note = document.createElement('p');
      note.textContent = count ? `Retrieved via ${search.provider}${search.retrieved_at ? ' · ' + new Date(search.retrieved_at).toLocaleString() : ''}` : 'No sources found.';
      note.title = search.query;
      if (count) panel.append(list);
      panel.append(note);
      webSources.replaceChildren(summary, panel);
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
        const streaming = reveal && state.status === 'streaming' && state.content;
        const before = streaming ? content.textContent : '';
        renderMarkdown(content, state.content, state.web_context?.sources || []);
        if (streaming) {
          if (!entered && !CSS.highlights) article.classList.add('response-enter');
          entered = true;
          reveal.fadeAppended(before);
        }
      } else content.textContent = state.content;
    }
    if (m.role === 'assistant') {
      if (state.status !== 'streaming') {
        reveal?.clear();
        article.classList.remove('response-enter');
      }
      if (state.telemetry !== previous.telemetry || state.status !== previous.status) renderReplyActions(actions, state);
      const errorText = state.error || (state.status === 'stopped' ? 'Stopped — incomplete response.' : state.status === 'error' ? 'Response failed.' : '');
      if (error.textContent !== errorText) error.textContent = errorText;
      const provider = state.telemetry?.provider || state.provider || 'ollama';
      cloudLabel.hidden = provider !== 'openai' || !state.content;
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
function updateJumpButton() {
  const thread = $('thread');
  $('jump-latest').hidden = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 64;
}
$('thread').addEventListener('scroll', () => {
  updateJumpButton();
  followOutput = $('jump-latest').hidden;
}, {passive:true});
function selectingThreadText() {
  const selection = window.getSelection();
  return selection && !selection.isCollapsed && ($('thread').contains(selection.anchorNode) || $('thread').contains(selection.focusNode));
}
function scrollDown(force = false) {
  if (force) followOutput = true;
  if (force || (followOutput && !selectingThreadText())) $('thread').scrollTop = $('thread').scrollHeight;
  updateJumpButton();
}
$('jump-latest').onclick = () => { scrollDown(true); $('thread').focus({preventScroll:true}); };

const drawer = matchMedia('(max-width: 700px)');
function setSidebar(open, restoreFocus = false) {
  document.body.classList.toggle('sidebar-open', open);
  $('menu').setAttribute('aria-expanded', String(open));
  $('sidebar-backdrop').hidden = !open;
  document.querySelector('main').inert = open;
  if (open) $('close-sidebar').focus();
  else {
    $('workspace').open = false;
    if (restoreFocus && drawer.matches) $('menu').focus();
  }
}
function showThinking(label = '') {
  $('thinking').hidden = !label;
  if (label) $('thinking-label').textContent = label;
  $('chat-status').textContent = label;
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
  setSidebar(false, document.body.classList.contains('sidebar-open'));
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
  setSidebar(false); scrollDown(true);
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
  $('chat-status').textContent = 'Thinking…';
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
        if (packet.handoff_of && handoffButton) handoffButton.remove();
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
        showThinking('Thinking…');
        streaming = createStreamBuffer(raw => {
          showThinking();
          message.update({content:raw});
          scrollDown();
        }, 150);
        scrollDown(!packet.handoff_of);
      }
      if (packet.type === 'start' && packet.omitted_messages) notice(`${packet.omitted_messages} older messages are saved but omitted from this request.`);
      if (packet.type === 'preparing') { showThinking('Thinking…'); scrollDown(); }
      if (packet.type === 'handoff_status') notice(packet.message);
      if (packet.type === 'web_status') showThinking(packet.message);
      if (packet.type === 'web_sources') {
        message.update(packet);
        showThinking('Thinking…');
        if (packet.omitted_messages) notice(`${packet.omitted_messages} older messages are saved but omitted from this request.`);
      }
      if (packet.type === 'delta') { accumulated += packet.content; streaming.set(accumulated); }
      if (packet.type === 'error') throw new Error(packet.message);
      if (packet.type === 'done') {
        streaming.close();
        showThinking();
        finished = true;
        message.update({...packet, status:'complete'});
        scrollDown();
      }
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
    if (!stopped && (!message || finished)) notice(text);
  } finally {
    streaming?.close(); showThinking(); stopActiveStream = null; controls();
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
      if (!selectingThreadText() && !retryOf && [document.body, $('stop')].includes(document.activeElement)) $('prompt').focus();
    }
  }
}
$('stop').onclick = () => { if (stopActiveStream) stopActiveStream(); };
$('new-chat').onclick = newChat;
$('refresh-models').onclick = window.localfirstBrowser?.manageModels || refreshModels;
$('menu').onclick = () => setSidebar(true);
$('close-sidebar').onclick = $('sidebar-backdrop').onclick = () => setSidebar(false, true);
drawer.addEventListener('change', event => { if (!event.matches) setSidebar(false); });
document.addEventListener('click', event => {
  if (!$('workspace').contains(event.target)) $('workspace').open = false;
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || $('handoff-dialog').open) return;
  if ($('workspace').open) {
    $('workspace').open = false;
    $('workspace').querySelector('summary').focus();
  } else if (drawer.matches && document.body.classList.contains('sidebar-open')) {
    setSidebar(false, true);
  }
});
function refreshReplyDetails() {
  const next = readReplyDetails();
  if (replyDetailFields.every(key => Boolean(next[key]) === Boolean(replyDetails[key]))) return;
  replyDetails = next;
  document.querySelectorAll('.reply-actions').forEach(actions => actions.dispatchEvent(new Event('replydetailschange')));
  updateJumpButton();
}
window.addEventListener('storage', event => {
  if (event.key === replyDetailsKey || event.key === null) refreshReplyDetails();
});
window.addEventListener('pageshow', refreshReplyDetails);
window.addEventListener('localfirst-display-change', refreshReplyDetails);
$('prompt').addEventListener('input', () => { $('prompt').style.height = 'auto'; $('prompt').style.height = Math.min($('prompt').scrollHeight, 160) + 'px'; });
$('prompt').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('composer').requestSubmit(); } });
Promise.all([refreshModels(), refreshList()]).then(() => {
  const cid = new URLSearchParams(location.search).get('conversation') || window.localfirstBrowser?.initialConversation();
  if (cid) return openConversation(cid);
}).catch(e => notice(e.message));
