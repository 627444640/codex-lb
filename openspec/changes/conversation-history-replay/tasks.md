# Tasks

- [x] Store compressed turn deltas in a separate SQLite file with an in-memory index
- [x] Replay once before the first output on HTTP and websocket, including onto a healthy account when the owner is unavailable
- [x] Enforce size, idle, and free-disk limits and reclaim evicted pages
- [x] Record replay reason and extra tokens, and expose cache stats without conversation text
- [x] Add regression tests and a write-count load comparison
