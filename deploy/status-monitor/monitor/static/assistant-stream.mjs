export async function readAssistantStream(response, onSnapshot) {
  if (!response.body || !response.headers.get("content-type")?.startsWith("text/event-stream")) {
    throw Error("返回内容不是有效的流式回答。");
  }
  const reader = response.body.getReader(), decoder = new TextDecoder("utf-8", {fatal:true});
  let buffer = "", kind = "", lines = [], eventSize = 0, total = 0;
  function line(value) {
    eventSize += value.length + 1;
    if (eventSize > 262144) throw Error("流式回答过大，请简化问题后再试。");
    if (value !== "") {
      if (value.startsWith("event:")) kind = value.slice(6).trim();
      if (value.startsWith("data:")) lines.push(value.slice(5).replace(/^ /, ""));
      return null;
    }
    const name = kind, data = lines.join("\n");
    kind = ""; lines = []; eventSize = 0;
    if (!data) return null;
    let payload; try {payload = JSON.parse(data);} catch {throw Error("流式回答格式不正确。");}
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw Error("流式回答格式不正确。");
    if (name === "error") throw Error(typeof payload.message === "string" ? payload.message.slice(0,400) : "模型生成未完成。");
    if (name === "snapshot") {
      if (typeof payload.text !== "string" || payload.text.length > 6000) throw Error("流式回答格式不正确。");
      onSnapshot(payload.text); return null;
    }
    if (name !== "completed" || typeof payload.answer !== "string" || !payload.answer || payload.answer.length > 6000 ||
        !Array.isArray(payload.sources) || payload.sources.length > 3 || typeof payload.model_used !== "boolean" ||
        payload.sources.some(source => !source || typeof source.title !== "string" || typeof source.url !== "string" ||
          !source.url.startsWith("/static/troubleshooting.html#"))) throw Error("最终回答未通过校验。");
    return payload;
  }
  try {
    while (true) {
      const {done,value} = await reader.read();
      if (value) {total += value.byteLength; if (total > 8*1024*1024) throw Error("流式回答过大，请稍后再试。");}
      buffer += decoder.decode(value, {stream:!done});
      let match;
      while ((match = /\r\n|\n|\r(?=[\s\S])/.exec(buffer))) {
        const result = line(buffer.slice(0,match.index)); buffer = buffer.slice(match.index+match[0].length);
        if (result) return result;
      }
      if (buffer.length+eventSize > 262144) throw Error("流式回答过大，请稍后再试。");
      if (done) throw Error("连接已结束，但回答尚未完成，请重试。");
    }
  } finally {
    await reader.cancel().catch(()=>{});
    reader.releaseLock();
  }
}
