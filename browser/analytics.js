import {readConversations} from './backend.js';

const dayMs = 86_400_000;
const mean = values => values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
const known = (rows, key) => rows.map(row => row[key]).filter(Number.isFinite);
const sum = values => values.length ? values.reduce((total, value) => total + value, 0) : null;

function aggregate(rows) {
  const requests = rows.length;
  const successful = rows.filter(row => row.status === 'success').length;
  const latencies = known(rows, 'latency_ms').sort((a, b) => a - b);
  const speeds = known(rows, 'tokens_per_second');
  const input = known(rows, 'input_tokens'), output = known(rows, 'output_tokens');
  return {
    requests, successful_requests: successful, running_requests: 0,
    local_percentage: successful ? 100 : null, cloud_percentage: successful ? 0 : null,
    external_api_cost: 0, cost_samples: requests, average_latency_ms: mean(latencies), latency_samples: latencies.length,
    median_latency_ms: mean(latencies.slice(Math.floor((latencies.length - 1) / 2), Math.floor(latencies.length / 2) + 1)),
    p95_latency_ms: latencies.length >= 20 ? latencies[Math.ceil(latencies.length * .95) - 1] : null,
    average_tokens_per_second: mean(speeds), generation_speed_samples: speeds.length,
    input_tokens: sum(input), output_tokens: sum(output), input_token_samples: input.length, output_token_samples: output.length,
    failure_rate: requests ? 100 * rows.filter(row => row.status === 'error').length / requests : null,
    cancellation_rate: requests ? 100 * rows.filter(row => row.status === 'cancelled').length / requests : null,
  };
}

export function browserUsage(search) {
  const params = new URLSearchParams(search);
  const days = Number(params.get('days') ?? '30');
  const selected = params.get('model');
  const recorded = readConversations().flatMap(c => c.messages.flatMap(message => message.telemetry ? [message.telemetry] : []));
  const rows = recorded.filter(row => (!selected || selected === row.model) && (!days || Date.parse(row.timestamp) >= Date.now() - days * dayMs));
  const byDate = Map.groupBy(rows, row => row.timestamp.slice(0, 10));
  const dates = [...byDate.keys()].sort();
  const trends = [];
  if (dates.length) {
    for (let day = Date.parse(dates[0]); day <= Date.parse(dates.at(-1)); day += dayMs) {
      const date = new Date(day).toISOString().slice(0, 10);
      const records = byDate.get(date) || [];
      trends.push({date, ...aggregate(records), local_requests: records.length, cloud_requests: 0,
        ...(!records.length ? {input_tokens: 0, output_tokens: 0} : {})});
    }
  }
  return {
    overview: aggregate(rows), trends,
    by_model: [...Map.groupBy(rows, row => row.model)].map(([model, items]) => ({model, ...aggregate(items)})),
    models: [...new Set(recorded.map(row => row.model))].sort(),
    cloud_budget: {limit: 0, reserved_or_charged: 0, unresolved_estimate: 0},
  };
}
