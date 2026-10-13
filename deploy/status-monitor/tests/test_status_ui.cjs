const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { JSDOM } = require('jsdom');

function payload() {
  return {
    title: 'Codex LB',
    status: 'operational',
    stale: false,
    collected_at: 1790747119,
    official_status: {
      provider: 'OpenAI', status: 'degraded', indicator: 'minor',
      description: 'Partial System Degradation', page_updated_at: 1790747000,
      fetched_at: 1790747119, stale: false, source_url: 'https://status.openai.com/',
      components: [{ id: 'responses', name: 'Responses', status: 'operational' }],
      incidents: [{ id: 'incident-1', name: 'Elevated errors', status: 'monitoring', impact: 'minor', updated_at: 1790747000, url: 'https://status.openai.com/incidents/incident-1' }],
    },
    capacity: { weekly_remaining_percent: 95.5, weekly_next_reset_at: 1791046713 },
    components: [
      { id: 'gateway', name: '网关', status: 'operational', detail: '就绪检查通过' },
      { id: 'source', name: '监控数据', status: 'operational', detail: '只读采集正常' },
      { id: 'quota', name: '可路由状态', status: 'operational', detail: '仍有可路由额度' },
      { id: 'quota_warning', name: '低余量预警', status: 'degraded', detail: '部分账号余量低于安全线', advisory: true },
      { id: 'requests', name: '真实模型请求', status: 'unknown', detail: '暂无真实模型请求样本，业务质量待调用后确认' },
    ],
    requests: { total: 0, errors: 0, successes: 0, cancelled: 0, error_percent: null, models: [] },
    request_quality: {
      window_seconds: 86400,
      total: 12,
      successes: 8,
      cancelled: 1,
      errors: 3,
      error_percent: 25,
      last_sample_at: 1790747119,
      last_error_at: 1790747000,
      categories: [{
        key: 'upstream_overload', label: '上游容量过载', count: 2, failure_share_percent: 66.67,
        last_error_at: 1790747000, models: ['gpt-6-astra'], guidance: '降低并发或稍后重试', guide_slug: 'error-upstream-overload',
      }],
    },
    history: { days: [], samples: 0, readiness_percent: null, since: null },
    incidents: [],
    incident_summary: { window_seconds: 86400, count: 0, open_count: 0, latest_status: 'quiet' },
    notices: [],
  };
}

test('capacity renders as accessible energy blocks and idle copy', async t => {
  const template = readFileSync(resolve(__dirname, '../monitor/static/index.html'), 'utf8');
  const script = readFileSync(resolve(__dirname, '../monitor/static/status.js'), 'utf8');
  const dom = new JSDOM(template, { url: 'https://status.example.lan:2467/', runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.setInterval = () => 0;
  let current = payload();
  dom.window.fetch = async () => ({ ok: true, json: async () => current });
  dom.window.AbortSignal = { timeout: () => new dom.window.AbortController().signal };
  dom.window.eval(script);
  await new Promise(resolve => setImmediate(resolve));

  const meter = dom.window.document.querySelector('#weekly-energy');
  assert.equal(meter.children.length, 40);
  assert.equal(meter.querySelectorAll('.filled').length, 38);
  assert.equal(meter.classList.contains('healthy'), true);
  assert.equal(dom.window.document.querySelector('#weekly-percent').classList.contains('healthy'), true);
  assert.equal(meter.getAttribute('role'), 'progressbar');
  assert.equal(meter.getAttribute('aria-valuenow'), '95.5');
  assert.equal(dom.window.document.querySelector('#status-title').textContent, '基础服务正常，近期请求需关注');
  assert.equal(dom.window.document.querySelector('.component-status.degraded').textContent, '低余量预警');
  assert.match(dom.window.document.querySelector('#components').textContent, /部分账号余量低于安全线/);
  assert.match(dom.window.document.querySelector('#request-note').textContent, /暂无真实模型请求样本/);
  assert.equal(dom.window.document.querySelector('#quality-total').textContent, '12');
  assert.equal(dom.window.document.querySelector('#quality-error-percent').textContent, '25%');
  assert.match(dom.window.document.querySelector('#request-quality-categories').textContent, /上游容量过载/);
  assert.equal(dom.window.document.querySelector('.quality-guide').getAttribute('href'), '/static/faq.html#error-upstream-overload');
  assert.match(dom.window.document.querySelector('#history-since').textContent, /不包含真实模型请求结果/);
  assert.equal(dom.window.document.querySelector('#official-status-state').textContent, '降级');
  assert.match(dom.window.document.querySelector('#official-status-description').textContent, /Partial System Degradation/);
  assert.equal(dom.window.document.querySelector('#official-status-link').href, 'https://status.openai.com/');
  assert.match(dom.window.document.querySelector('#official-status-components').textContent, /Responses/);
  assert.match(dom.window.document.querySelector('#official-status-incidents').textContent, /Elevated errors/);

  current = { ...payload(), capacity: { weekly_remaining_percent: 45, weekly_next_reset_at: 1791046713 } };
  dom.window.document.querySelector('#refresh').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(meter.classList.contains('warning'), true);
  assert.equal(dom.window.document.querySelector('#weekly-percent').classList.contains('warning'), true);
  current = { ...payload(), capacity: { weekly_remaining_percent: 10, weekly_next_reset_at: 1791046713 } };
  dom.window.document.querySelector('#refresh').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(meter.classList.contains('critical'), true);
  assert.equal(dom.window.document.querySelector('#weekly-percent').classList.contains('critical'), true);

  current = {
    ...payload(),
    status: 'outage',
    components: payload().components.map(component =>
      component.id === 'quota'
        ? { ...component, status: 'outage', detail: '额度不足' }
        : component.id === 'quota_warning'
          ? { ...component, status: 'degraded', detail: '部分账号额度已耗尽或余量偏低' }
          : component,
    ),
  };
  dom.window.document.querySelector('#refresh').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(dom.window.document.querySelector('#status-title').textContent, '检测到服务异常');
  assert.match(dom.window.document.querySelector('#components').textContent, /额度不足/);
});
test('official status renders unknown without stale green data', async t => {
  const template = readFileSync(resolve(__dirname, '../monitor/static/index.html'), 'utf8');
  const script = readFileSync(resolve(__dirname, '../monitor/static/status.js'), 'utf8');
  const dom = new JSDOM(template, { url: 'https://status.example.lan:2467/', runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.setInterval = () => 0;
  dom.window.fetch = async () => ({ ok: true, json: async () => ({ ...payload(), official_status: {
    provider: 'OpenAI', status: 'unknown', description: '官方状态采样已过期', fetched_at: 1790747119,
    stale: true, source_url: 'https://status.openai.com/', components: payload().official_status.components,
    incidents: payload().official_status.incidents,
  } }) });
  dom.window.AbortSignal = { timeout: () => new dom.window.AbortController().signal };
  dom.window.eval(script);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(dom.window.document.querySelector('#official-status-state').textContent, '待核对');
  assert.match(dom.window.document.querySelector('#official-status-description').textContent, /过期/);
  assert.equal(dom.window.document.querySelector('#official-status-panel').classList.contains('unknown'), true);
  assert.doesNotMatch(dom.window.document.querySelector('#official-status-components').textContent, /Responses/);
  assert.doesNotMatch(dom.window.document.querySelector('#official-status-incidents').textContent, /Elevated errors/);
  assert.match(dom.window.document.querySelector('#official-status-incidents').textContent, /读取过期/);
});

test('official status distinguishes disabled from a failed local status read', async t => {
  const template = readFileSync(resolve(__dirname, '../monitor/static/index.html'), 'utf8');
  const script = readFileSync(resolve(__dirname, '../monitor/static/status.js'), 'utf8');
  const dom = new JSDOM(template, { url: 'https://status.example.lan:2467/', runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.setInterval = () => 0;
  let current = { ...payload(), official_status: null };
  dom.window.fetch = async () => ({ ok: true, json: async () => current });
  dom.window.AbortSignal = { timeout: () => new dom.window.AbortController().signal };
  dom.window.eval(script);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(dom.window.document.querySelector('#official-status-state').textContent, '未启用');
  assert.match(dom.window.document.querySelector('#official-status-description').textContent, /尚未启用/);
  assert.doesNotMatch(dom.window.document.querySelector('#official-status-note').textContent, /monitor|provider/i);
  assert.match(dom.window.document.querySelector('#official-status-incidents').textContent, /启用后/);

  dom.window.fetch = async () => { throw new Error('connection'); };
  await dom.window.document.querySelector('#refresh').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(dom.window.document.querySelector('#official-status-state').textContent, '暂时无法读取');
  assert.match(dom.window.document.querySelector('#official-status-description').textContent, /无法连接/);
  assert.match(dom.window.document.querySelector('#official-status-note').textContent, /暂时无法读取官方状态/);
  assert.equal(dom.window.document.querySelector('#official-status-link').href, 'https://status.openai.com/');
});

test('official status links stay on the official host and incident names are text', async t => {
  const template = readFileSync(resolve(__dirname, '../monitor/static/index.html'), 'utf8');
  const script = readFileSync(resolve(__dirname, '../monitor/static/status.js'), 'utf8');
  const dom = new JSDOM(template, { url: 'https://status.example.lan:2467/', runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.setInterval = () => 0;
  const official = { ...payload().official_status, source_url: 'https://evil.example/status', incidents: [
    { ...payload().official_status.incidents[0], name: '<img src=x onerror=alert(1)>', url: 'javascript:alert(1)' },
    { ...payload().official_status.incidents[0], id: 'relative', name: 'Relative link', url: '/incidents/relative' },
  ] };
  dom.window.fetch = async () => ({ ok: true, json: async () => ({ ...payload(), official_status: official }) });
  dom.window.AbortSignal = { timeout: () => new dom.window.AbortController().signal };
  dom.window.eval(script);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(dom.window.document.querySelector('#official-status-link').href, 'https://status.openai.com/');
  const incidentLinks = [...dom.window.document.querySelectorAll('#official-status-incidents a')];
  assert.equal(incidentLinks.length, 2);
  assert.equal(incidentLinks[0].href, 'https://status.openai.com/');
  assert.equal(incidentLinks[1].href, 'https://status.openai.com/');
  assert.equal(dom.window.document.querySelectorAll('#official-status-incidents img').length, 0);
  assert.match(dom.window.document.querySelector('#official-status-incidents').textContent, /<img src=x/);
});

test('status navigation resolves below the public status mount', () => {
  const template = readFileSync(resolve(__dirname, '../monitor/static/index.html'), 'utf8');
  const dom = new JSDOM(template, { url: 'https://status.example.invalid/status/' });
  try {
    assert.equal(dom.window.document.querySelector('link[rel="icon"]').href,
      'https://status.example.invalid/status/static/favicon.svg?v=codex-lb');
    assert.equal(dom.window.document.querySelector('nav a[href="static/faq.html"]').href,
      'https://status.example.invalid/status/static/faq.html');
  } finally {
    dom.window.close();
  }
});
