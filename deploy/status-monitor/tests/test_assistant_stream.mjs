import test from 'node:test';
import assert from 'node:assert/strict';
import {readAssistantStream} from '../monitor/static/assistant-stream.mjs';

const encode=new TextEncoder();
const event=(kind,data)=>`event: ${kind}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
const final={answer:'最终中文建议',sources:[{title:'指南',url:'/static/troubleshooting.html#error-413'}],model_used:true};
function response(text,size=1){
  const bytes=encode.encode(text);let offset=0;
  return new Response(new ReadableStream({pull(controller){
    if(offset===bytes.length){controller.close();return;}
    const next=bytes.slice(offset,offset+size);offset+=next.length;controller.enqueue(next);
  }}),{headers:{'Content-Type':'text/event-stream'}});
}
test('split UTF-8 snapshots replace earlier text and return validated final sources',async()=>{
  const snapshots=[];
  const result=await readAssistantStream(response(event('snapshot',{text:'很长的旧稿'})+event('snapshot',{text:'短稿'})+event('completed',final)),text=>snapshots.push(text));
  assert.deepEqual(snapshots,['很长的旧稿','短稿']);assert.deepEqual(result,final);
});
test('truncation never becomes a completed answer',async()=>{
  await assert.rejects(readAssistantStream(response(event('snapshot',{text:'尚未完成'})),()=>{}),/尚未完成/);
});
test('server error after a draft rejects and does not return sources',async()=>{
  await assert.rejects(readAssistantStream(response(event('snapshot',{text:'草稿'})+event('error',{message:'资料已更新'})),()=>{}),/资料已更新/);
});
test('invalid final source and malformed frames fail closed',async()=>{
  for(const text of (['event: snapshot\ndata: broken\n\n',event('completed',{...final,sources:[{title:'错误',url:'javascript:alert(1)'}]})])){
    await assert.rejects(readAssistantStream(response(text),()=>{}));
  }
});
test('SSE comments and multiline data are decoded',async()=>{
  const text=':keepalive\n\nevent: completed\ndata: {"answer":"好了",\ndata: "sources":[],"model_used":false}\n\n';
  assert.equal((await readAssistantStream(response(text,3),()=>{})).answer,'好了');
});
test('unterminated oversized frame is bounded',async()=>{
  await assert.rejects(readAssistantStream(response('data: '+ 'x'.repeat(262145),4096),()=>{}),/过大/);
});
