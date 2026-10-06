# Keep the status banner healthy when there is no request traffic

## Why

When the monitor has no normal request samples, it marks the request component
as unknown. The global status reducer then promotes that idle state to a page
level "部分状态等待确认" banner, even when the gateway, source collector and
quota observations are healthy. This makes an absence of traffic look like a
service problem.

## What Changes

- Treat an idle request component as non-blocking for the page-level status
  when its request aggregate is present and contains zero normal requests.
- Keep the request component itself as an unknown/no-sample observation so the
  page does not claim business-request success without traffic.
- Explain the idle state in the banner and request component:基础服务正常，
  当前暂无真实模型请求样本，业务质量待调用后确认。
- Preserve the existing request incident debounce and Luna probe filtering.

## Impact

This changes status presentation and the top-level aggregate only. It does not
alter request logs, incident creation rules, quota data, or gateway routing.
