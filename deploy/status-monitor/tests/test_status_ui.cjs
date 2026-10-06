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
    capacity: { weekly_remaining_percent: 95.5, weekly_next_reset_at: 1791046713 },
    components: [
      { id: 'gateway', name: '网关', status: 'operational', detail: '就绪检查通过' },
      { id: 'source', name: '监控数据', status: 'operational', detail: '只读采集正常' },
      { id: 'quota', name: '号池额度', status: 'operational', detail: '近期额度样本正常' },
      { id: 'requests', name: '真实模型请求', status: 'unknown', detail: '暂无真实模型请求样本，业务质量待调用后确认' },
    ],
    requests: { total: 0, errors: 0, successes: 0, cancelled: 0, error_percent: null, models: [] },
    history: { days: [], samples: 0, readiness_percent: null, since: null },
    incidents: [],
    notices: [],
  };
}

test('capacity renders as accessible energy blocks and idle copy', async t => {
  const template = readFileSync(resolve(__dirname, '../monitor/static/index.html'), 'utf8');
  const script = readFileSync(resolve(__dirname, '../monitor/static/status.js'), 'utf8');
  const dom = new JSDOM(template, { url: 'https://status.example.lan:2467/', runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.setInterval = () => 0;
  dom.window.fetch = async () => ({ ok: true, json: async () => payload() });
  dom.window.AbortSignal = { timeout: () => new dom.window.AbortController().signal };
  dom.window.eval(script);
  await new Promise(resolve => setImmediate(resolve));

  const meter = dom.window.document.querySelector('#weekly-energy');
  assert.equal(meter.children.length, 24);
  assert.equal(meter.querySelectorAll('.filled').length, 23);
  assert.equal(meter.getAttribute('role'), 'progressbar');
  assert.equal(meter.getAttribute('aria-valuenow'), '95.5');
  assert.equal(dom.window.document.querySelector('#status-title').textContent, '基础服务运行正常');
  assert.match(dom.window.document.querySelector('#request-note').textContent, /暂无真实模型请求样本/);
});
