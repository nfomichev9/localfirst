'use strict';
const $ = id => document.getElementById(id);
const num = n => n == null ? '—' : n.toLocaleString(undefined, {maximumFractionDigits:1});
const seconds = n => n == null ? '—' : `${(n/1000).toFixed(2)}s`;
const percent = n => n == null ? '—' : `${num(n)}%`;
const money = n => n == null ? '—' : `$${n.toFixed(4)}`;
function cards(id, items) {
  $(id).replaceChildren(...items.map(([label, value, help]) => {
    const box = document.createElement('div'); box.className = 'stat-card';
    const title = document.createElement('div'); title.textContent = label;
    const stat = document.createElement('strong'); stat.textContent = value;
    const note = document.createElement('small'); note.textContent = help;
    box.append(title, stat, note); return box;
  }));
}
function svgElement(tag, attrs = {}) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
  return el;
}
function chart(id, rows, kind) {
  const host = $(id); host.replaceChildren();
  if (!rows.length) { const p = document.createElement('p'); p.className = 'chart-empty'; p.textContent = 'No activity in this period'; host.append(p); return; }
  const svg = svgElement('svg', {viewBox:'0 0 600 230', role:'img', 'aria-label':`${kind} by day in UTC`});
  const values = rows.map(r => kind === 'Requests' ? r.requests : kind === 'Tokens' ? (r.input_tokens == null && r.output_tokens == null ? null : (r.input_tokens ?? 0)+(r.output_tokens ?? 0)) : r.external_api_cost);
  const observedMax = Math.max(0, ...values.filter(v => v != null));
  const max = Math.max(1, observedMax);
  const step = 540/rows.length, width = Math.max(1, step*.65);
  const axis = svgElement('path', {d:'M40 20V190H585', class:'chart-axis'}); svg.append(axis);
  const top = svgElement('text', {x:4, y:20, class:'chart-label'}); top.textContent = kind === 'API costs' ? money(observedMax) : num(observedMax); svg.append(top);
  rows.forEach((r, i) => {
    const value = values[i];
    const group = svgElement('g', {tabindex:'0', class:'chart-point'});
    const description = kind === 'Requests' ? `${r.requests} requests (${r.local_requests} local, ${r.cloud_requests} cloud)` : kind === 'API costs' ? `${money(value)} API cost` : `${num(value)} known tokens`;
    const title = svgElement('title'); title.textContent = `${r.date}: ${description}`; group.append(title);
    group.setAttribute('aria-label', title.textContent);
    // Full-height transparent hit target makes zero/unknown values inspectable.
    group.append(svgElement('rect', {x:40+i*step,y:20,width:step,height:170,class:'chart-hit'}));
    const height = (value ?? 0)/max*160;
    if (kind === 'Requests') {
      const localHeight = r.local_requests/max*160;
      group.append(svgElement('rect', {x:40+i*step+step*.15,y:190-localHeight,width,height:Math.max(1,localHeight),class:'chart-local'}));
      if (r.cloud_requests) group.append(svgElement('rect', {x:40+i*step+step*.15,y:190-height,width,height:height-localHeight,class:'chart-cloud'}));
    } else group.append(svgElement('rect', {x:40+i*step+step*.15,y:190-height,width,height:Math.max(1,height),class:value == null ? 'chart-unknown' : 'chart-local'}));
    group.addEventListener('mouseenter', () => caption.textContent = title.textContent);
    group.addEventListener('focus', () => caption.textContent = title.textContent);
    svg.append(group);
  });
  (rows.length === 1 ? [0] : [0, rows.length-1]).forEach((i, k) => {
    const label = svgElement('text', {x:k ? 585 : 40,y:218,'text-anchor':k?'end':'start',class:'chart-label'});
    label.textContent = rows[i].date; svg.append(label);
  });
  const caption = document.createElement('p'); caption.className = 'chart-caption'; caption.textContent = 'Hover or focus a bar to inspect the day';
  host.append(svg, caption);
}
let sequence = 0;
async function loadUsage() {
  const version = ++sequence;
  $('usage-status').textContent = 'Loading local usage…';
  try {
    const response = await fetch(`/api/usage?days=${$('period').value}&model=${encodeURIComponent($('filter-model').value)}`);
    if (!response.ok) throw new Error(`Usage could not load (${response.status}).`);
    const data = await response.json(); if (version !== sequence) return;
    const selection = $('filter-model').value;
    $('filter-model').replaceChildren(new Option('All models',''), ...data.models.map(m => new Option(m,m)));
    $('filter-model').value = selection;
    const o = data.overview;
    cards('overview-cards', [
      ['Inference requests', num(o.requests), `${num(o.successful_requests)} successful · ${num(o.running_requests)} running`],
      ['Local inference', percent(o.local_percentage), 'Share of successful requests'],
      ['Cloud inference', percent(o.cloud_percentage), 'Share of successful requests'],
      ['Token-derived API charges', money(o.external_api_cost), `${num(o.cost_samples)} of ${num(o.requests)} requests have known costs`]
    ]);
    cards('performance-cards', [
      ['Average latency', seconds(o.average_latency_ms), `${num(o.latency_samples)} measured attempts`],
      ['Median latency', seconds(o.median_latency_ms), '50th percentile'],
      ['P95 latency', seconds(o.p95_latency_ms), o.latency_samples < 20 ? 'Requires 20 latency samples' : '95th percentile · nearest rank'],
      ['Generation speed', o.average_tokens_per_second == null ? '—' : `${num(o.average_tokens_per_second)} tok/s`, `${num(o.generation_speed_samples)} provider measurements`],
      ['Input tokens', num(o.input_tokens), `${num(o.input_token_samples)} requests with known counts`],
      ['Output tokens', num(o.output_tokens), `${num(o.output_token_samples)} requests with known counts`],
      ['Failure rate', percent(o.failure_rate), 'Errors / all admitted attempts'],
      ['Cancellation rate', percent(o.cancellation_rate), 'Cancelled / all admitted attempts']
    ]);
    $('coverage').textContent = 'Latency includes model discovery, context preparation, and generation. First-token time is measured when nonempty response content arrives. Unknown measurements display —. Rates use all admitted attempts, including running ones.';
    const budget = data.cloud_budget;
    document.getElementById('cloud-budget').textContent =
      `Today’s cloud budget · ${money(budget.reserved_or_charged)} of ${money(budget.limit)} used or reserved · ${money(budget.unresolved_estimate)} estimated for requests with unknown charges.`;
    chart('requests-chart', data.trends, 'Requests'); chart('tokens-chart', data.trends, 'Tokens'); chart('cost-chart', data.trends, 'API costs');
    $('model-rows').replaceChildren(...data.by_model.map(m => {
      const row = document.createElement('tr');
      [m.model,num(m.requests),num(m.successful_requests),seconds(m.average_latency_ms),seconds(m.median_latency_ms),seconds(m.p95_latency_ms),num(m.average_tokens_per_second),`${num(m.input_tokens)} / ${num(m.output_tokens)}`,money(m.external_api_cost),`${percent(m.failure_rate)} / ${percent(m.cancellation_rate)}`].forEach(value => {const cell = document.createElement('td'); cell.textContent = value; row.append(cell);});
      return row;
    }));
    $('usage-status').textContent = o.requests ? 'Showing persisted inference telemetry. Refresh to include new activity.' : 'No inference attempts in this view. Start a chat or choose another filter.';
  } catch (e) { if (version === sequence) $('usage-status').textContent = e.message; }
}
$('period').onchange = loadUsage; $('filter-model').onchange = loadUsage; $('refresh-usage').onclick = loadUsage;
loadUsage();
