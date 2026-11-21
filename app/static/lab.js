'use strict';
const $ = id => document.getElementById(id);
let activeTask = null, dirty = false, busy = false, online = false, draftId = null, controller = null, stopBuffer = null, saving = false, sourceTurn = null;
const verdicts = ['uncertain','pass','fail','insufficient_context'];
function text(tag, value, className) { const el = document.createElement(tag); el.textContent = value; if (className) el.className = className; return el; }
function status(message, error = false) {
  $('lab-status').textContent = message;
  $('lab-status').dataset.error = String(error);
  $('lab-status').hidden = !message;
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers:{'Content-Type':'application/json'}});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(d => d.msg).join(' ') : `Request failed (${response.status}).`;
    throw Error(detail);
  }
  return response;
}
function syncControls() {
  document.querySelectorAll('#task-form input, #task-form textarea, #task-form select, #task-form button, #lab-model, #prepared-prompt, #added-context, #confirm-draft, .example-actions button, #new-task, #task-picker, #trial-history button, #trial-history select, #trial-history textarea, #preparation-records button, #preparation-result button, #chat-turns button, #rate-answer, #start-review, #refresh-chat-turns, #more-chat-turns').forEach(el => el.disabled = busy || saving);
  document.querySelectorAll('#task-list button').forEach(el => el.disabled = busy || saving || dirty);
  $('prepare-task').disabled = $('run-original').disabled = busy || saving || !online || !activeTask || dirty;
  $('run-prepared').disabled = busy || saving || !online || !activeTask || dirty || !$('prepared-prompt').value.trim() || !$('confirm-draft').checked;
  $('stop-lab').hidden = !busy;
  $('stop-lab').disabled = !busy || Boolean(controller?.signal.aborted);
  $('task-version').textContent = activeTask ? `Revision ${activeTask.revision}${dirty ? ' · Unsaved changes: save before running.' : ' · Saved. Each trial keeps its own snapshot.'}` : 'Save before running. Tasks and results remain on this machine.';
}
function fields() {
  return {title:$('task-title').value, prompt:$('task-prompt').value, context:$('task-context').value,
    criteria:$('task-criteria').value.split('\n').map(v => v.trim()).filter(Boolean),
    check_mode:$('check-mode').value, reference:$('task-reference').value};
}
function clearDraft() {
  draftId = null; $('prepared-prompt').value = ''; $('added-context').value = ''; $('confirm-draft').checked = false;
  $('draft-source').textContent = 'Manual draft. Original source context and criteria will also be sent.';
  $('preparation-result').replaceChildren(text('p', 'No context check yet. You can also write a prepared prompt yourself.', 'lab-empty'));
}
function fillTask(task) {
  activeTask = task; dirty = false;
  $('task-title').value = task?.title || ''; $('task-prompt').value = task?.prompt || '';
  $('task-context').value = task?.context || ''; $('task-criteria').value = task?.criteria.join('\n') || '';
  $('check-mode').value = task?.check_mode || 'none'; $('task-reference').value = task?.reference || '';
  sourceTurn = null;
  $('task-prompt').readOnly = $('task-context').readOnly = false;
  $('save-task').textContent = 'Save experiment';
  $('chat-source').hidden = true;
  $('lab-empty').hidden = true;
  $('experiment-tools').open = false;
  markSelectedTurn();
  clearDraft(); renderHistory(task?.operations || []); syncControls();
}
async function refreshTasks() {
  const tasks = await (await api('/api/lab/tasks')).json();
  $('task-list').replaceChildren(); $('task-picker').replaceChildren(new Option('Choose a saved experiment',''));
  if (!tasks.length) $('task-list').append(text('p','Saved experiments will appear here.','lab-empty'));
  tasks.forEach(task => {
    const button = text('button',task.title); button.classList.toggle('active', task.id === activeTask?.id);
    button.onclick = () => openTask(task.id).catch(e => status(e.message,true)); $('task-list').append(button);
    $('task-picker').append(new Option(task.title,task.id));
  });
  $('task-picker').value = activeTask?.id || ''; syncControls();
}
async function openTask(id) {
  if (busy) return;
  const task = await (await api(`/api/lab/tasks/${id}`)).json(); fillTask(task);
  const recent = task.operations.find(o => o.kind === 'prepare' && o.revision === task.revision);
  if (recent) renderPreparation(recent);
  if (!task.operations.some(operation => operation.kind === 'run')) $('experiment-tools').open = true;
  await refreshTasks(); status('');
}
function useDraft(record) {
  $('prepared-prompt').value = record.result.prepared_prompt; draftId = record.id;
  $('confirm-draft').checked = false;
  $('draft-source').textContent = `Draft from local context check · task revision ${record.revision}. Review any missing information and assumptions.`;
  syncControls();
}
function renderPreparation(record) {
  const host = $('preparation-result'); host.replaceChildren();
  if (record.status !== 'success' || !record.result) {
    host.append(text('p',record.error || `Context check ${record.status}.`, 'lab-error'));
    const details = document.createElement('details'); details.append(text('summary','Saved partial / raw output'),text('pre',record.output,'lab-input')); host.append(details); return;
  }
  host.append(text('h3', record.result.context_sufficient ? 'Model suggests context is sufficient' : 'Model flags missing context'));
  host.append(text('p','Advisory suggestion; confirm it yourself.','lab-note'));
  [['Missing information','missing_information'],['Clarifying questions','clarifying_questions'],['Assumptions','assumptions']].forEach(([label,key]) => {
    host.append(text('h3',label));
    if (!record.result[key].length) host.append(text('p','None identified.','lab-note'));
    else {const list = document.createElement('ul'); record.result[key].forEach(item => list.append(text('li',item))); host.append(list);}
  });
  const draft = document.createElement('details'); draft.append(text('summary','Inspect suggested prompt'),text('p',record.result.prepared_prompt)); host.append(draft);
  const button = text('button','Use this draft'); button.onclick = () => useDraft(record); host.append(button);
}
const seconds = value => value == null ? '—' : `${(value/1000).toFixed(2)}s`;
const num = value => value == null ? '—' : value.toLocaleString(undefined,{maximumFractionDigits:1});
function metrics(record) {
  const t = record.telemetry;
  if (!t) return 'Measurements unavailable';
  return `${t.model} · Local · ${seconds(t.latency_ms)} · ${num(t.input_tokens)} input / ${num(t.output_tokens)} output tokens · ${num(t.tokens_per_second)} tok/s · First content ${seconds(t.ttft_ms)} · ${t.external_api_cost == null ? 'Cost unknown' : '$'+t.external_api_cost.toFixed(4)+' API'}`;
}
function reviewForm(record) {
  const form = document.createElement('form'); form.className = 'review-form';
  form.append(text('h3','Your assessment'));
  const choices = [];
  function select(label, value) {
    const wrapper = text('label',label), el = document.createElement('select');
    verdicts.forEach(v => el.append(new Option(v.replaceAll('_',' '),v))); el.value = value || 'uncertain'; wrapper.append(el); form.append(wrapper); return el;
  }
  record.snapshot.criteria.forEach((criterion,i) => choices.push(select(`Criterion ${i+1}: ${criterion}`, record.review?.criteria[i])));
  const verdict = select('Overall verdict', record.review?.verdict);
  const label = text('label','Evidence / rationale'); const notes = document.createElement('textarea'); notes.required = true; notes.maxLength = 4000; notes.rows = 2; notes.value = record.review?.notes || ''; label.append(notes); form.append(label);
  const button = text('button','Save assessment'); button.type = 'submit'; form.append(button);
  form.onsubmit = async event => {
    event.preventDefault(); button.disabled = true;
    try {
      await api(`/api/lab/operations/${record.id}/review`, {method:'PUT',body:JSON.stringify({verdict:verdict.value, criteria:choices.map(el => el.value), notes:notes.value})});
      await reloadHistory(); status('Human assessment saved. It is separate from the string check and inference status.');
    } catch (e) {status(e.message,true); button.disabled = false;}
  };
  return form;
}
function renderHistory(operations) {
  const runs = operations.filter(o => o.kind === 'run'); $('trial-history').replaceChildren();
  const baseline = runs.findIndex(record => record.origin === 'chat');
  if (baseline > 0) runs.unshift(runs.splice(baseline, 1)[0]);
  $('evaluation-results').hidden = !runs.length;
  $('history-count').textContent = `${runs.length} ${runs.length === 1 ? 'trial' : 'trials'}`;
  runs.forEach(record => {
    const card = document.createElement('article'); card.className = 'lab-panel lab-trial'; card.dataset.operationId = record.id;
    card.append(text('h3', record.origin === 'chat' ? 'Saved chat answer · baseline' : record.variant === 'original' ? 'Original prompt' : record.added_context ? 'Prepared + added context' : 'Prepared · same source context'));
    card.append(text('p',`Revision ${record.revision} · ${record.status} · ${new Date(record.created_at).toLocaleString()}`, 'lab-note'));
    card.append(text('h4','Request'), text('p',record.prepared_prompt || record.snapshot.prompt,'lab-request'));
    const summary = document.createElement('div'); summary.className = 'report-summary';
    const cost = document.createElement('section');
    cost.append(text('h4','Local cost'), text('strong',apiCharge(record.telemetry)), text('p',runtimeAndElectricity(record.telemetry),'lab-note'));
    const quality = document.createElement('section');
    quality.append(text('h4','Answer quality'), text('p',record.review ? `Human verdict: ${record.review.verdict.replaceAll('_',' ')}` : 'Human verdict: not assessed', 'lab-verdict'));
    if (record.review) quality.append(text('p',record.review.notes,'lab-request'));
    summary.append(cost,quality); card.append(summary);

    if (record.origin === 'chat') card.append(text('p', `Imported without rerunning or adding usage. Criteria were declared after this answer. Context: ${record.snapshot.source.context_source}.`, 'lab-note'));
    else if (record.snapshot.source) card.append(text('p', `Chat-derived trial. Original roles/context are replayed when source fields are unchanged; later edits create a custom variation. Context source: ${record.snapshot.source.context_source}.`, 'lab-note'));
    card.append(text('h4','Answer'));
    const output = document.createElement('div'); output.className = 'message-content'; renderMarkdown(output,record.output); card.append(output);
    if (record.error) card.append(text('p',record.error,'lab-error'));
    if (record.result) card.append(text('p',`${record.result.method === 'exact' ? 'Exact string check' : 'Contains string check'}: ${record.result.passed ? 'matched' : 'did not match'}. This is not a task-success verdict.`, 'lab-check-result'));
    if (record.status === 'success') {
      const review = document.createElement('details'); review.className = 'trial-review';
      review.append(text('summary',record.review ? 'Edit human assessment' : 'Assess this trial'),reviewForm(record));
      card.append(review);
    }
    if (record.snapshot.source) {
      const link = text('a','Open source conversation','usage-link');
      link.href = `/?conversation=${encodeURIComponent(record.snapshot.source.conversation_id)}`;
      card.append(link);
    }
    const inputs = document.createElement('details'); inputs.append(text('summary','Inspect exact inputs & criteria'));
    inputs.append(text('p',metrics(record),'lab-metrics'));
    inputs.append(text('pre',record.submitted_prompt,'lab-input'));
    inputs.append(text('p',`Draft source: ${record.variant === 'original' ? 'original task' : record.preparation_id ? 'local model draft, reviewed / possibly edited by user' : 'manual rewrite'}. Added context: ${record.added_context || '(none)'}`, 'lab-note'));
    inputs.append(text('p',`Reference check: ${record.snapshot.check_mode}. Reference (withheld from generation): ${record.snapshot.reference || '(none)'}`, 'lab-note'));
    card.append(inputs);
    $('trial-history').append(card);
  });
  $('preparation-records').replaceChildren();
  operations.filter(o => o.kind === 'prepare').forEach(record => {
    const details = document.createElement('details'); details.append(text('summary',`Revision ${record.revision} · ${record.status} · ${new Date(record.created_at).toLocaleString()}`));
    details.append(text('p',metrics(record),'lab-note'),text('pre',record.output,'lab-input'));
    if (record.status === 'success' && record.revision === activeTask?.revision) {const button = text('button','Inspect this context check'); button.onclick = () => renderPreparation(record); details.append(button);}
    $('preparation-records').append(details);
  });
  syncControls();
}
async function reloadHistory(settleId = null) {
  if (!activeTask) return;
  let task;
  // HTTP abort and SQLite finalization can race. Wait briefly for this operation
  // to settle instead of leaving a stopped trial displayed as running forever.
  for (let attempt=0; attempt<30; attempt++) {
    task = await (await api(`/api/lab/tasks/${activeTask.id}`)).json();
    if (!settleId || !task.operations.some(o => o.id === settleId && o.status === 'running')) break;
    await new Promise(resolve => setTimeout(resolve,100));
  }
  activeTask.operations = task.operations; renderHistory(task.operations);
  if (settleId && task.operations.some(o => o.id === settleId && o.status === 'running')) status('The server is still finishing this operation. Reopen the experiment to refresh its status.');
}
async function operate(kind, variant) {
  if (busy || !activeTask || dirty) return;
  busy = true; controller = new AbortController(); syncControls();
  $('live-operation').hidden = false; $('live-output').replaceChildren(); $('live-label').textContent = kind === 'prepare' ? 'Checking context locally…' : `Running ${variant} locally…`;
  const stream = createStreamBuffer(raw => renderMarkdown($('live-output'),raw));
  stopBuffer = stream;
  let raw = '', complete = false, operationId = null;
  const body = {expected_revision:activeTask.revision, model:$('lab-model').value};
  if (kind === 'run') Object.assign(body,{variant, ...(variant === 'prepared' ? {prepared_prompt:$('prepared-prompt').value, added_context:$('added-context').value, confirmed:$('confirm-draft').checked, preparation_id:draftId} : {})});
  status(kind === 'prepare' ? 'Inspecting the saved request. Nothing will be sent to a frontier model.' : 'Running a saved trial. Assess task success after reviewing the answer.');
  try {
    const response = await api(`/api/lab/tasks/${activeTask.id}/${kind === 'prepare' ? 'prepare' : 'runs'}`, {method:'POST',body:JSON.stringify(body),signal:controller.signal});
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
    function consume(line) {
      if (!line.trim() || controller.signal.aborted || complete) return;
      const packet = JSON.parse(line);
      if (packet.type === 'start') operationId = packet.operation.id;
      if (packet.type === 'delta') {raw += packet.content; stream.set(raw);}
      if (packet.type === 'error') throw Error(packet.message);
      if (packet.type === 'done') {
        complete = true; stream.close();
        if (kind === 'prepare') renderPreparation(packet.operation);
        status(kind === 'prepare' ? 'Context check saved. Inspect its suggestions, then choose whether to use the draft.' : 'Trial saved. Generation completed; task success still needs your assessment.');
      }
    }
    while (true) {const {done,value} = await reader.read(); buffer += decoder.decode(value,{stream:!done}); const lines = buffer.split('\n'); buffer = lines.pop(); lines.forEach(consume); if (done) {if (buffer.trim()) consume(buffer); break;}}
    if (!complete) throw Error('Stream ended before completion. Partial output is retained.');
  } catch (e) {
    controller.abort(); stream.close();
    status(e.name === 'AbortError' ? 'Stopped. Partial output is retained; this attempt has no task-success verdict.' : e.message, e.name !== 'AbortError');
  } finally {
    stream.close(); syncControls();
    try {await reloadHistory(operationId); if (kind === 'prepare' && !complete) {const recent = activeTask.operations.find(o => o.kind === 'prepare'); if (recent) renderPreparation(recent);}} catch(e) {status(e.message,true);}
    finally {busy = false; controller = null; stopBuffer = null; syncControls();}
  }
}
function apiCharge(telemetry) {
  const charge = telemetry?.external_api_cost;
  return charge == null ? 'API charge unavailable' : `$${charge === 0 ? '0' : charge.toFixed(4)} API charge`;
}
function runtimeAndElectricity(telemetry) {
  const runtime = telemetry?.latency_ms == null ? 'runtime unavailable' : `${seconds(telemetry.latency_ms)} runtime`;
  return `${runtime} · electricity unmeasured`;
}
function markSelectedTurn() {
  const selected = String(sourceTurn?.message_id || activeTask?.source?.message_id || '');
  $('chat-turns').querySelectorAll('button').forEach(button => {
    button.setAttribute('aria-current', String(button.dataset.messageId === selected));
  });
}
function showChatSource(turn) {
  $('chat-source').hidden = false;
  $('chat-source-request').textContent = turn.prompt;
  $('chat-source-model').textContent = turn.model || 'Model unavailable';
  $('chat-source-cost').textContent = apiCharge(turn.metrics);
  $('chat-source-runtime').textContent = runtimeAndElectricity(turn.metrics);
  $('chat-source-info').textContent = `${turn.title} · ${turn.model || 'Model unavailable'} · ${turn.context_source === 'recorded' ? 'Recorded message input sent to Ollama' : 'Context reconstructed from saved messages; exact original request was not recorded'}. The model may have truncated context internally.`;
  renderMarkdown($('chat-source-answer'),turn.output);
  $('chat-source-link').href = `/?conversation=${encodeURIComponent(turn.conversation_id)}`;
}
async function selectChatTurn(mid, scroll = false) {
  if (busy || saving) return;
  const turn = await (await api(`/api/lab/chat-turns/${mid}`)).json();
  if (turn.task_id) {
    await openTask(turn.task_id);
    if (scroll) $('evaluation-results').scrollIntoView({block:'nearest'});
    return;
  }
  fillTask(null); sourceTurn = turn;
  $('task-title').value = turn.title;
  $('task-prompt').value = turn.prompt; $('task-context').value = turn.context;
  $('task-prompt').readOnly = $('task-context').readOnly = true;
  $('task-criteria').value = "Addresses the user's request using the available context.\nAvoids unsupported claims and identifies essential missing information.";
  $('save-task').textContent = 'Create experiment from this answer';
  showChatSource(turn); markSelectedTurn(); syncControls();
  if (scroll) $('chat-source').scrollIntoView({block:'nearest'});
  status('');
}
let chatOffset = 0;
async function refreshChatTurns(append = false) {
  if (!append) {chatOffset = 0; $('chat-turns').replaceChildren();}
  const data = await (await api(`/api/lab/chat-turns?limit=50&offset=${chatOffset}`)).json();
  if (!data.total) $('chat-turns').append(text('p','Your completed chat answers will appear here automatically. Start a conversation, then return to evaluate it.','lab-empty'));
  data.items.forEach(turn => {
    const button = document.createElement('button'); button.className = 'chat-turn';
    button.dataset.messageId = turn.message_id;
    button.append(text('strong',turn.prompt_preview || turn.title),
      text('small',`${turn.model || 'Model unavailable'} · ${new Date(turn.created_at).toLocaleDateString()}`));
    button.onclick = () => selectChatTurn(turn.message_id, true).catch(e => status(e.message,true));
    $('chat-turns').append(button);
  });
  chatOffset += data.items.length; $('more-chat-turns').hidden = !data.has_more; markSelectedTurn(); syncControls();
  return data.items[0];
}
$('rate-answer').onclick = () => $('task-form').requestSubmit();
$('start-review').onclick = () => {
  $('experiment-tools').open = true;
  $('task-criteria').focus();
};
$('refresh-chat-turns').onclick = async () => {
  try {
    const latest = await refreshChatTurns();
    if (!$('lab-empty').hidden && latest) await selectChatTurn(latest.message_id);
  } catch (e) { status(e.message,true); }
};
$('more-chat-turns').onclick = () => refreshChatTurns(true).catch(e => status(e.message,true));
$('task-form').onsubmit = async event => {
  event.preventDefault(); if (busy || saving) return;
  saving = true; syncControls();
  try {
    const data = fields(); if (activeTask) data.expected_revision = activeTask.revision;
    const endpoint = sourceTurn ? `/api/lab/chat-turns/${sourceTurn.message_id}/import` : '/api/lab/tasks'+(activeTask ? '/'+activeTask.id : '');
    const payload = sourceTurn ? {criteria:data.criteria,title:data.title,check_mode:data.check_mode,reference:data.reference} : data;
    const task = await (await api(endpoint,{method:activeTask?'PUT':'POST',body:JSON.stringify(payload)})).json();
    const imported = Boolean(sourceTurn);
    await openTask(task.id); await refreshChatTurns();
    $('experiment-tools').open = !imported;
    if (imported) {
      const review = $('trial-history').querySelector('.review-form');
      if (review) review.parentElement.open = true;
      $('evaluation-results').scrollIntoView();
    }
    status(imported ? '' : `Saved revision ${task.revision}.`);
  } catch(e) {status(e.message,true);}
  finally {saving = false; syncControls();}
};
$('task-form').addEventListener('input', () => {dirty = true; syncControls();});
$('prepared-prompt').oninput = $('added-context').oninput = () => {$('confirm-draft').checked = false; syncControls();};
$('confirm-draft').onchange = syncControls;
function newTask() {fillTask(null); $('experiment-tools').open = true; $('experiment-tools').scrollIntoView(); refreshTasks().catch(e => status(e.message,true)); status('Define a task and success criteria before running.');}
$('new-task').onclick = newTask;
$('task-picker').onchange = () => {if ($('task-picker').value) openTask($('task-picker').value).catch(e => status(e.message,true));};
$('prepare-task').onclick = () => operate('prepare'); $('run-original').onclick = () => operate('run','original'); $('run-prepared').onclick = () => operate('run','prepared');
$('stop-lab').onclick = () => {stopBuffer?.close(); controller?.abort(); syncControls();};
$('example-math').onclick = () => {fillTask({title:'Arithmetic sanity check',prompt:'Calculate 17 × 23. Respond with only the number.',context:'',criteria:['Return the correct product.','Output only the number.'],check_mode:'exact',reference:'391',operations:[]}); activeTask = null; dirty = true; $('experiment-tools').open = true; syncControls();};
$('example-context').onclick = () => {fillTask({title:'An email without the email',prompt:'Help me reply to the email I received.',context:'',criteria:['Address the actual sender’s request.','Do not invent the email contents.'],check_mode:'none',reference:'',operations:[]}); activeTask = null; dirty = true; $('experiment-tools').open = true; syncControls();};
(async () => {
  fillTask(null); await refreshTasks(); const latest = await refreshChatTurns();
  const message = new URLSearchParams(location.search).get('message');
  const experiment = new URLSearchParams(location.search).get('experiment');
  if (message && /^\d+$/.test(message)) await selectChatTurn(message);
  else if (experiment) await openTask(experiment);
  else if (latest) await selectChatTurn(latest.message_id);
  else $('lab-empty').hidden = false;
  try {const catalog = await (await api('/api/models')).json(); $('lab-model').replaceChildren(...catalog.models.map(m => new Option(catalog.labels?.[m] || m,m))); if (catalog.default) $('lab-model').value = catalog.default; online = catalog.models.length > 0; if (!online) status('No local model is available for new trials. Saved answers are still available.',true);} catch(e) {status(e.message,true);}
  syncControls();
})().catch(e => status(e.message,true));
