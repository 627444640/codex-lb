const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { JSDOM } = require('jsdom');

function setup(t, page, address) {
  const root = resolve(__dirname, '../monitor/static');
  const dom = new JSDOM(readFileSync(resolve(root, page), 'utf8'), {
    url: 'https://status.example.invalid/' + page, runScripts: 'outside-only',
  });
  t.after(() => dom.window.close());
  dom.window.fetch = () => { throw Error('Navigation must not fetch external data'); };
  dom.window.eval(readFileSync(resolve(root, 'report-config.js'), 'utf8'));
  if (address !== undefined) dom.window.statusPageReportUrl = address;
  dom.window.eval(readFileSync(resolve(root, 'report-link.js'), 'utf8'));
  return dom.window.document;
}

for (const page of ['index.html', 'faq.html']) {
  test(`${page} links to the configured form after FAQ without changing the current page`, t => {
    const document = setup(t, page, 'https://forms.example.invalid/report');
    const link = document.querySelector('nav .report-link');
    assert.equal(link.hidden, false);
    assert.equal(link.previousElementSibling.textContent, '常见问题');
    assert.equal(link.textContent, '问题上报');
    assert.equal(link.href, 'https://forms.example.invalid/report');
    assert.equal(link.target, '_blank');
    assert.equal(link.rel, 'noopener noreferrer');
    assert.equal(document.querySelector('nav [aria-current="page"]').textContent, page === 'index.html' ? '概览' : '常见问题');
    assert.equal(link.hasAttribute('aria-current'), false);
  });

  test(`${page} hides unconfigured or unsafe report destinations`, t => {
    for (const address of [undefined, '', 'not a url', 'javascript:alert(1)', 'http://forms.example.invalid/',
      'https://user:password@forms.example.invalid/', ' https://forms.example.invalid/', 'https://forms.example.invalid/\\x']) {
      const document = setup(t, page, address);
      const link = document.querySelector('nav .report-link');
      assert.equal(link.hidden, true);
      assert.equal(link.hasAttribute('href'), false);
    }
  });
}
