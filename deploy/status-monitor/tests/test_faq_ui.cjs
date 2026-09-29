const test=require('node:test'),assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const {JSDOM}=require('jsdom');

function setup(t,clipboard){
  const template=readFileSync(resolve(__dirname,'../monitor/static/faq.html'),'utf8');
  const content='<details class="troubleshooting-item" id="error-synthetic" open><summary>示例问题</summary><div class="troubleshooting-body"><code id="endpoint">https://example.invalid/v1</code><button data-copy-target="endpoint">复制地址</button><p class="copy-feedback" role="status"></p></div></details>';
  const dom=new JSDOM(template.replace('<!-- PUBLISHED_GUIDES -->',content),{url:'http://127.0.0.1:2466/static/faq.html',runScripts:'outside-only'});
  t.after(()=>dom.window.close());
  Object.defineProperty(dom.window.navigator,'clipboard',{value:{writeText:clipboard}});
  let calls=0;dom.window.fetch=()=>{calls++;throw Error('FAQ must not fetch model or status APIs');};
  dom.window.eval(readFileSync(resolve(__dirname,'../monitor/static/faq.js'),'utf8'));
  return {window:dom.window,document:dom.window.document,calls:()=>calls};
}

test('FAQ has no chat controls and copying an address makes no network call',async t=>{
  let copied;const {document,calls}=setup(t,async text=>{copied=text;});
  assert.equal(document.querySelector('h1').textContent,'常见问题');
  assert.equal(document.querySelector('textarea,form,[id^="assistant-"]'),null);
  assert.equal(document.querySelector('nav [aria-current="page"]').getAttribute('href'),'/static/faq.html');
  document.querySelector('[data-copy-target]').click();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(copied,'https://example.invalid/v1');
  assert.match(document.querySelector('.copy-feedback').textContent,/已复制/);assert.equal(calls(),0);
});

test('denied clipboard access selects the address and keeps the guide readable',async t=>{
  const {window,document,calls}=setup(t,async()=>{throw Error('denied');});
  document.querySelector('[data-copy-target]').click();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(window.getSelection().toString(),'https://example.invalid/v1');
  assert.match(document.querySelector('.copy-feedback').textContent,/复制已选中的地址/);
  assert.equal(document.querySelector('details').open,true);assert.equal(calls(),0);
});
