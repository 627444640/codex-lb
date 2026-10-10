"use strict";
const $ = (id) => document.getElementById(id);
const labels = {operational:"正常",degraded:"降级",outage:"异常",unknown:"待核对"};
const heads = {operational:"所有观测项运行正常",degraded:"部分服务需要关注",outage:"检测到服务异常",unknown:"部分状态等待确认"};
const date = (ts, short=false) => ts == null ? "—" : new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Taipei",...(short?{}:{month:"2-digit",day:"2-digit"}),hour:"2-digit",minute:"2-digit",...(short?{second:"2-digit"}:{}) ,hour12:false}).format(new Date(ts*1000));
const number = (n) => n == null ? "—" : n.toLocaleString("zh-CN");
const percent = (n) => n == null ? "—" : `${Number(n.toFixed(2))}%`;
const duration = (n) => n == null ? "—" : `${(n/1000).toFixed(2)}s`;
const ENERGY_BLOCKS = 40;
function el(tag, cls, text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;}
function empty(container, mark, title, body){container.replaceChildren();const n=el("div","empty-state");n.append(el("span","empty-mark",mark),el("p","",title),el("span","",body));container.append(n);}
function render(s){
  const state=s.stale||!Object.hasOwn(labels,s.status)?"unknown":s.status;
  const idle=Boolean(s.requests && !s.requests.total);
  const quality=s.request_quality;
  const qualityAttention=Boolean(quality && quality.total >= 10 && quality.errors && quality.error_percent >= 10);
  $("status-banner").className=`status-banner ${state}`;
  $("status-title").textContent=state==="operational"&&idle&&qualityAttention?"基础服务正常，近期请求需关注":state==="operational"&&idle?"基础服务运行正常":heads[state];
  $("status-symbol").textContent={operational:"✓",degraded:"!",outage:"!",unknown:"—"}[state];
  $("status-description").textContent=s.stale?"采样已过期，实时状态暂不可确认。":state==="operational"&&idle&&qualityAttention?`当前 15 分钟无请求；最近 24 小时错误率 ${percent(quality.error_percent)}，请查看请求质量。`:state==="operational"&&idle&&quality?.total?`当前 15 分钟无请求；最近 24 小时有 ${number(quality.total)} 条终态样本，业务质量见下方。`:state==="operational"&&idle?"当前暂无真实模型请求样本，业务质量待调用后确认。":state==="operational"?"当前已配置的观测项正常，详细结果见下方。":"请查看下方各项观测结果，异常连续出现后会进入事件记录。";
  $("banner-label").textContent=s.stale?"DATA STALE":state==="operational"?"OPERATIONAL":labels[state];
  $("last-updated").textContent=s.collected_at?`最后采样 ${date(s.collected_at,true)}`:"等待首次采样";
  const weekly=s.capacity?.weekly_remaining_percent;
  $("weekly-percent").textContent=percent(weekly);
  const energy=$("weekly-energy");
  const known=Number.isFinite(weekly);
  const filled=known?Math.round(Math.max(0,Math.min(100,weekly))/100*ENERGY_BLOCKS):0;
  const energyClass=!known?"unknown":weekly>=60?"healthy":weekly>=20?"warning":"critical";
  $("weekly-percent").className=`weekly-value ${energyClass}`;
  energy.className=`energy-meter ${energyClass}`;
  energy.replaceChildren(...Array.from({length:ENERGY_BLOCKS},(_,i)=>el("span",`energy-block ${known&&i<filled?"filled":""}`)));
  energy.setAttribute("aria-valuenow",known?String(weekly):"0");
  energy.setAttribute("aria-valuetext",known?percent(weekly):"待核对");
  const weeklyReset=s.capacity?.weekly_next_reset_at;
  $("weekly-reset").textContent=weeklyReset==null?"下一次重置：—":`下一次重置：${date(weeklyReset)}`;
  $("components").replaceChildren();
  for(const c of s.components||[]){const row=el("div","component-row"),main=el("div","component-main"),state=el("span",`component-status ${c.status}`),componentLabel=c.id==="requests"&&c.status==="unknown"&&idle?"无样本":labels[c.status];main.append(el("div","component-name",c.name),el("div","component-detail",`${c.detail}${c.latency_ms!=null?` · ${Math.round(c.latency_ms)} ms`:""}`));state.append(el("i","status-dot"),document.createTextNode(componentLabel));row.append(el("span","component-symbol",{gateway:"⇄",source:"▤",quota:"◴",requests:"↗"}[c.id]||"◎"),main,state);$("components").append(row);}
  if(!s.components?.length)$("components").append(el("p","empty-copy","等待健康检查"));
  const h=s.history||{days:[],samples:0};
  $("readiness-percent").textContent=percent(h.readiness_percent);
  $("coverage").textContent=`累计采样 ${h.samples} 次`;
  $("calendar-grid").replaceChildren();$("calendar-months").replaceChildren();
  const first=h.days[0];
  const offset=first?(new Date(`${first.date}T00:00:00Z`).getUTCDay()+6)%7:0;
  const cells=[...Array(offset).fill(null),...h.days];
  while(cells.length%7)cells.push(null);
  for(let i=0;i<cells.length;i+=7){
    const week=el("div","calendar-week");
    const days=cells.slice(i,i+7);const monthStart=days.find(d=>d&&(d.date.endsWith("-01")||d===first));
    $("calendar-months").append(el("span","",monthStart?`${Number(monthStart.date.slice(5,7))}月`:""));
    for(const d of days){
      const grade=!d?"blank":d.percent==null?"unknown":d.percent===100?"perfect":d.percent>=99?"good":d.percent>=95?"fair":d.percent>=80?"degraded":"outage";
      const cell=el(d?"button":"span",`calendar-day ${grade}`);
      if(d){cell.type="button";cell.title=`${d.date} · ${d.percent==null?"无有效样本":`正常率 ${percent(d.percent)}`} · ${d.observed}/${d.samples} 次有效探测`;cell.setAttribute("aria-label",cell.title);cell.addEventListener("click",()=>{$("history-since").textContent=cell.title;});}
      week.append(cell);
    }$("calendar-grid").append(week);
  }
  $("history-since").textContent=h.since?`基础探测观测起于 ${date(h.since)}。不包含真实模型请求结果；灰色日期无有效样本。`:"基础探测正常率只统计就绪检查，不包含真实模型请求结果。";
  const r=s.requests;
  $("request-window").textContent=`最近 ${Math.round((r?.window_seconds||900)/60)} 分钟 · 号池请求`;
  $("request-total").textContent=number(r?.total);$("error-percent").textContent=percent(r?.error_percent);
  $("first-output").textContent=duration(r?.first_output_p50_ms);$("duration-p95").textContent=duration(r?.duration_p95_ms);
  $("first-label").textContent=r?.timing_kind==="first_token"?"首 Token P50":"首输出 P50";
  $("models").replaceChildren();
  for(const m of r?.models||[]){const row=el("tr");for(const v of [m.model,number(m.total),number(m.successes),number(m.errors),number(m.cancelled),date(m.last_success_at,true)])row.append(el("td","",v));$("models").append(row);}
  if(!r?.models?.length){const row=el("tr"),cell=el("td","empty-copy","暂无请求样本，业务可用性待观察");cell.colSpan=6;row.append(cell);$("models").append(row);}
  $("request-note").textContent=idle?"当前暂无真实模型请求样本，业务质量待调用后确认。":`错误率 = 失败 / 总请求；取消单列，不计入错误数。${r?`延迟基于最近 ${r.timing_samples} 条成功请求。`:""}健康接口通过不能代替模型请求成功。`;
  const qualityWindowMinutes=Math.round((quality?.window_seconds||86400)/60);
  $("request-quality-window").textContent=`最近 ${qualityWindowMinutes>=1440?Math.round(qualityWindowMinutes/1440):qualityWindowMinutes} ${qualityWindowMinutes>=1440?"天":"分钟"}`;
  if(!quality){
    $("request-quality-title").textContent="等待采样";
    $("quality-total").textContent=$("quality-error-percent").textContent=$("quality-last-error").textContent="—";
    empty($("request-quality-categories"),"—","暂时无法读取请求质量","采样过期或监控数据不可用");
    $("request-quality-note").textContent="请求质量窗口暂不可用，页面不会使用旧数据代替当前状态。";
  }else{
    const qualityHasSamples=quality.total>0;
    $("request-quality-title").textContent=qualityAttention?"近期请求需要关注":qualityHasSamples?"最近请求质量":"暂无请求样本";
    $("quality-total").textContent=number(quality.total);
    $("quality-error-percent").textContent=percent(quality.error_percent);
    $("quality-last-error").textContent=date(quality.last_error_at,true);
    $("request-quality-categories").replaceChildren();
    if(!quality.categories?.length){
      $("request-quality-categories").append(el("p","empty-copy",qualityHasSamples?"窗口内没有失败请求":"窗口内暂无真实请求样本"));
    }else{
      for(const category of quality.categories){
        const row=el("article","quality-category"),head=el("div","quality-category-head");
        head.append(el("strong","",category.label),el("span","quality-count",`${number(category.count)} · 失败占比 ${percent(category.failure_share_percent)}`));
        const models=category.models?.length?`模型：${category.models.join("、")}`:"模型：—";
        row.append(head,el("p","quality-category-meta",`${models} · 最近 ${date(category.last_error_at,true)}`),el("p","quality-guidance",category.guidance));
        if(category.guide_slug){const guide=document.createElement("a");guide.className="quality-guide";guide.href=`/static/faq.html#${encodeURIComponent(category.guide_slug)}`;guide.textContent="查看处理建议";row.append(guide);}
        $("request-quality-categories").append(row);
      }
    }
    $("request-quality-note").textContent=idle&&qualityHasSamples?`当前 15 分钟无请求；以下为最近 ${qualityWindowMinutes>=1440?Math.round(qualityWindowMinutes/1440):qualityWindowMinutes} ${qualityWindowMinutes>=1440?"天":"分钟"}的终态样本。错误率 = 失败 / 总样本，取消计入样本但不计为错误。`:"错误率 = 失败 / 总样本，取消计入样本但不计为错误；分类按失败终态统计，已排除 Luna 探测和外部模型来源。";
  }
  const incidentSummary=s.incident_summary;
  if(!incidentSummary||!incidentSummary.count){
    $("incident-summary").textContent="最近 24 小时没有请求事件";
    $("incident-summary").className="incident-summary quiet";
  }else{
    const incidentState=incidentSummary.open_count?`处理中 ${incidentSummary.open_count} 次`:"最近一次已恢复";
    $("incident-summary").textContent=`最近 24 小时请求事件 ${number(incidentSummary.count)} 次 · ${incidentState} · 最近打开 ${date(incidentSummary.latest_opened_at,true)}`;
    $("incident-summary").className=`incident-summary ${incidentSummary.open_count?"active":"recovered"}`;
  }
  if(!s.incidents?.length)empty($("incident-list"),"✓","暂无已确认事件","持续观测中的异常将在这里更新");else{
    $("incident-list").replaceChildren();for(const i of s.incidents.slice(0,8)){const item=el("article","event-item"),meta=el("div","event-meta");meta.append(el("span",`tag ${i.closed_at?"":"outage"}`,i.closed_at?"已恢复":"处理中"),el("span","",date(i.opened_at)));item.append(meta,el("h3","",i.title));if(i.closed_at)item.append(el("p","",`恢复于 ${date(i.closed_at)}`));$("incident-list").append(item);}
    if(s.incidents.length>8){const count=Number.isFinite(incidentSummary?.count)?incidentSummary.count:s.incidents.length;const note=el("p","empty-copy",`页面显示最近 8 条；最近 24 小时新开 ${count} 次请求事件。`);$("incident-list").append(note);}
  }
  $("notice-list").replaceChildren();
  if(!s.notices?.length)$("notice-list").append(el("span","announcement-empty","暂无服务公告"));
  else for(const n of s.notices){const item=el("div",`announcement-line ${n.level}`);const copy=el("span","announcement-copy",`${n.title} · ${n.body}`);copy.title=n.body;item.append(el("span",`tag ${n.level}`,{info:"公告",maintenance:"维护",warning:"提醒"}[n.level]),copy);$("notice-list").append(item);}

}
let loading=false;
async function refresh(){if(loading)return;loading=true;$("refresh").disabled=true;try{const res=await fetch("/api/status",{cache:"no-store",signal:AbortSignal.timeout(10000)});if(!res.ok)throw Error("request");const data=await res.json();render(data);$("connection-error").hidden=true;}catch{render({status:"unknown",stale:true});$("connection-error").textContent="暂时无法连接监控服务。页面已停止显示旧数据，请稍后刷新。";$("connection-error").hidden=false;}finally{loading=false;$("refresh").disabled=false;}}
$("refresh").addEventListener("click",refresh);refresh();setInterval(()=>{if(!document.hidden)refresh();},30000);document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});

// 概览页内部锚点不改变顶部页面导航的选中状态。
function updateNavigation(){
  const target="#overview";
  for(const link of document.querySelectorAll('nav[aria-label="页面导航"] a')){
    const active=link.getAttribute("href")===target;
    link.classList.toggle("active",active);
    if(active)link.setAttribute("aria-current","page");else link.removeAttribute("aria-current");
  }
}
window.addEventListener("hashchange",updateNavigation);updateNavigation();
