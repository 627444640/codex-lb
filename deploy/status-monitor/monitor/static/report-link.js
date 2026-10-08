"use strict";
(() => {
  const address = window.statusPageReportUrl;
  if (typeof address !== "string" || !address || /[\s\\]/.test(address)) return;
  let url;
  try { url = new URL(address); } catch { return; }
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password) return;
  for (const link of document.querySelectorAll("nav .report-link")) {
    link.href = url.href;
    link.hidden = false;
  }
})();
