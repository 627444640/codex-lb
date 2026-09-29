const test=require('node:test'),assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {JSDOM}=require('jsdom');
const {pathToFileURL}=require('node:url');
const {resolve}=require('node:path');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const frame=(kind,data)=>new TextEncoder().encode(`event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`);

async function setup(t,{visible=false}={}){
  const dom=new JSDOM(readFileSync(resolve(__dirname,'../monitor/static/troubleshooting.html'),'utf8'),{url:'http://synthetic.invalid',runScripts:'outside-only',pretendToBeVisual:visible});
  const w=dom.window,requests=[],writers=[];t.after(()=>w.close());
  const paints=new Map();let nextPaint=0;
  w.requestAnimationFrame=callback=>{paints.set(++nextPaint,callback);return nextPaint;};
  w.cancelAnimationFrame=id=>paints.delete(id);
  const paint=async()=>{const [id,callback]=paints.entries().next().value;paints.delete(id);callback(w.performance.now());await new Promise(resolve=>setTimeout(resolve,75));await tick();};
  w.AbortController=AbortController;w.AbortSignal=AbortSignal;
  w.readAssistantStream=(await import(pathToFileURL(resolve(__dirname,'../monitor/static/assistant-stream.mjs')))).readAssistantStream;
  w.fetch=async(url,options)=>{
    if(url==="/api/troubleshooting/assistant")return new Response(JSON.stringify({enabled:true}));
    requests.push(JSON.parse(options.body));
    const body=new ReadableStream({start(controller){
      writers.push(controller);
      options.signal.addEventListener('abort',()=>controller.error(new DOMException('Stopped','AbortError')),{once:true});
    }});
    return new Response(body,{headers:{'Content-Type':'text/event-stream'}});
  };
  const script=readFileSync(resolve(__dirname,'../monitor/static/troubleshooting.js'),'utf8').replace(/^import[^\n]+\n/,'');
  w.eval(script);await tick();
  const find=id=>w.document.getElementById(id);
  const submit=async()=>{find('assistant-question').value='payload_too_large';find('assistant-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();};
  return {w,find,submit,requests,writers,paints,paint};
}

test('UI replaces draft text and adds sources/history only after completion',async t=>{
  const {w,find,submit,requests,writers}=await setup(t);
  await submit();assert.equal(requests[0].stream,true);
  writers[0].enqueue(frame('snapshot',{text:'很长的初稿'}));await tick();
  const draft=w.document.querySelector('.assistant-message.draft');assert.ok(draft);
  assert.equal(draft.querySelector('p').textContent,'很长的初稿');assert.equal(w.document.querySelectorAll('.assistant-sources').length,0);
  writers[0].enqueue(frame('snapshot',{text:'短稿'}));await tick();assert.equal(draft.querySelector('p').textContent,'短稿');
  writers[0].enqueue(frame('completed',{answer:'最终建议 <img src=x onerror=alert(1)>',sources:[{title:'指南',url:'/static/troubleshooting.html#error-413'}],model_used:true}));writers[0].close();await tick();
  assert.equal(w.document.querySelectorAll('.draft').length,0);assert.equal(w.document.querySelectorAll('.assistant-sources a').length,1);
  assert.equal(w.document.querySelectorAll('.assistant-messages img').length,0);
  await submit();assert.equal(requests[1].history.length,2);assert.ok(requests[1].history[1].content.startsWith('最终建议'));
  assert.ok(!JSON.stringify(requests[1].history).includes('初稿'));
  find('assistant-stop').click();await tick();
});

test('stop removes draft and does not add it to the next request history',async t=>{
  const {w,find,submit,requests,writers}=await setup(t);
  await submit();writers[0].enqueue(frame('snapshot',{text:'未完成内容'}));await tick();
  find('assistant-stop').click();await tick();
  assert.equal(w.document.querySelectorAll('.draft').length,0);assert.match(find('assistant-feedback').textContent,/已停止/);
  await submit();assert.deepEqual(requests[1].history,[]);find('assistant-stop').click();await tick();
});

test('failed or truncated streams clear provisional answers and preserve retry input',async t=>{
  const {w,find,submit,requests,writers}=await setup(t);
  await submit();writers[0].enqueue(frame('snapshot',{text:'不得保留的草稿'}));await tick();
  writers[0].enqueue(frame('error',{code:'guides_changed',message:'资料已更新'}));writers[0].close();await tick();
  assert.equal(w.document.querySelectorAll('.assistant-message.assistant').length,0);assert.match(find('assistant-feedback').textContent,/资料已更新/);
  assert.equal(find('assistant-question').value,'payload_too_large');
  await submit();assert.deepEqual(requests[1].history,[]);writers[1].enqueue(frame('snapshot',{text:'另一个未完成草稿'}));writers[1].close();await tick();
  assert.equal(w.document.querySelectorAll('.draft').length,0);assert.match(find('assistant-feedback').textContent,/尚未完成/);
});

test('one network chunk visibly presents both real revisions before final sources',async t=>{
  const {w,submit,writers,paint,paints}=await setup(t,{visible:true});
  await submit();
  writers[0].enqueue(Buffer.concat([
    frame('snapshot',{text:'第一版实际内容'}),frame('snapshot',{text:'第二版实际修订'}),
    frame('completed',{answer:'最终答案',sources:[{title:'指南',url:'/static/troubleshooting.html#error-413'}],model_used:true})
  ]));writers[0].close();await tick();
  assert.equal(w.document.querySelector('.draft p').textContent,'第一版实际内容');
  assert.equal(w.document.querySelectorAll('.assistant-sources').length,0);assert.equal(paints.size,1);
  await paint();assert.equal(w.document.querySelector('.draft p').textContent,'第二版实际修订');
  assert.equal(w.document.querySelectorAll('.assistant-sources').length,0);
  await paint();assert.equal(w.document.querySelectorAll('.draft').length,0);
  assert.equal(w.document.querySelector('.assistant-message.assistant p').textContent,'最终答案');
  assert.equal(w.document.querySelectorAll('.assistant-sources a').length,1);
});

test('stop interrupts a pending visible paint and drops the unfinished revision',async t=>{
  const {w,find,submit,writers,paints,requests}=await setup(t,{visible:true});
  await submit();writers[0].enqueue(frame('snapshot',{text:'尚未完成的真实快照'}));await tick();
  assert.equal(paints.size,1);find('assistant-stop').click();await tick();
  assert.equal(paints.size,0);assert.equal(w.document.querySelectorAll('.draft').length,0);
  assert.match(find('assistant-feedback').textContent,/已停止/);
  await submit();assert.deepEqual(requests[1].history,[]);find('assistant-stop').click();await tick();
});
