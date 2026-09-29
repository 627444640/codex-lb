import {readAssistantStream} from "./assistant-stream.mjs";
for(const button of document.querySelectorAll("[data-copy-target]")){
  button.addEventListener("click",async()=>{
    const target=document.getElementById(button.dataset.copyTarget);
    const feedback=button.closest(".troubleshooting-body").querySelector(".copy-feedback");
    try{
      await navigator.clipboard.writeText(target.textContent);
      feedback.textContent="地址已复制。";
    }catch{
      const range=document.createRange();range.selectNodeContents(target);
      const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
      feedback.textContent="浏览器未允许自动复制，请复制已选中的地址。";
    }
  });
}

const assistantForm=document.getElementById("assistant-form");
if(assistantForm){
  const question=document.getElementById("assistant-question"),send=document.getElementById("assistant-send");
  const clear=document.getElementById("assistant-clear"),messages=document.getElementById("assistant-messages");
  const stop=document.getElementById("assistant-stop");
  const feedback=document.getElementById("assistant-feedback"),state=document.getElementById("assistant-state");
  let enabled=false,busy=false,history=[],controller=null;
  function bubble(role,text,sources=[],draft=false){
    const item=document.createElement("article");item.className=`assistant-message ${role}`;
    if(draft){item.classList.add("draft");item.setAttribute("aria-busy","true");}
    const label=document.createElement("strong");label.textContent=role==="user"?"你":draft?"排查助手 · 生成中，内容仍会修订":"排查助手";
    const copy=document.createElement("p");copy.textContent=text;item.append(label,copy);
    if(sources.length){
      const refs=document.createElement("div");refs.className="assistant-sources";
      const caption=document.createElement("span");caption.textContent="依据指南：";refs.append(caption);
      for(const source of sources){
        if(typeof source.url!=="string"||!source.url.startsWith("/static/troubleshooting.html#"))continue;
        const link=document.createElement("a");link.href=source.url;link.textContent=source.title;link.target="_blank";link.rel="noopener";refs.append(link);
      }
      item.append(refs);
    }
    messages.hidden=false;messages.append(item);
    while(messages.children.length>12)messages.firstElementChild.remove();
    messages.scrollTop=messages.scrollHeight;
    return item;
  }
  function setBusy(value){busy=value;send.disabled=busy||!enabled;question.disabled=busy||!enabled;clear.disabled=busy;stop.hidden=!busy;send.textContent=busy?"生成中…":"发送问题";}
  async function availability(){
    try{
      const response=await fetch("/api/troubleshooting/assistant",{cache:"no-store",signal:AbortSignal.timeout(8000)});
      if(!response.ok)throw Error("availability");
      const info=await response.json();enabled=info.enabled===true;
      state.textContent=enabled?"根据指南回答":"暂未启用";
      feedback.textContent=enabled?"":"管理员尚未启用智能排查，你可以先阅读下方指南。";
    }catch{state.textContent="暂时不可用";feedback.textContent="暂时无法连接智能排查服务，请先阅读下方指南。";}
    setBusy(false);
  }
  question.addEventListener("keydown",event=>{
    if(event.key==="Enter"&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();if(!busy&&enabled)assistantForm.requestSubmit();}
  });
  assistantForm.addEventListener("submit",async event=>{
    event.preventDefault();const text=question.value.trim();if(!text||busy||!enabled)return;
    bubble("user",text);setBusy(true);feedback.textContent="正在查阅指南，生成内容会逐步修订…";
    controller=new AbortController();let timedOut=false,draft=null;
    const timeout=setTimeout(()=>{timedOut=true;controller?.abort();},60000);
    try{
      const response=await fetch("/api/troubleshooting/chat",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({question:text,history:history.slice(-4),stream:true}),signal:controller.signal});
      if(!response.ok){
        let error;try{error=await response.json();}catch{throw Error("智能排查暂时不可用，请稍后再试。");}
        throw Error(error.error?.message||error.detail||"智能排查暂时不可用，请稍后再试。");
      }
      const result=await readAssistantStream(response,snapshot=>{
        if(!draft)draft=bubble("assistant","",[],true);
        draft.querySelector("p").textContent=snapshot||"正在整理回答…";
        messages.scrollTop=messages.scrollHeight;
      });
      draft?.remove();draft=null;
      bubble("assistant",result.answer,result.sources);
      history.push({role:"user",content:text},{role:"assistant",content:result.answer.slice(0,2000)});history=history.slice(-4);
      question.value="";feedback.textContent=result.model_used?"建议基于上方所列指南，请结合实际情况核对。":"暂未找到匹配指南，请按提示补充信息。";
    }catch(error){draft?.remove();feedback.textContent=timedOut?"等待模型响应超时，未保留生成草稿；请稍后再试。":error.name==="AbortError"?"已停止生成，未完成的回答不会加入后续对话。":error.message||"智能排查暂时不可用，请稍后再试。";}
    finally{clearTimeout(timeout);controller=null;setBusy(false);question.focus();}
  });
  stop.addEventListener("click",()=>controller?.abort());
  window.addEventListener("pagehide",()=>controller?.abort());
  clear.addEventListener("click",()=>{history=[];messages.replaceChildren();messages.hidden=true;question.value="";feedback.textContent=enabled?"对话已清空。":"管理员尚未启用智能排查。";});
  availability();
}
