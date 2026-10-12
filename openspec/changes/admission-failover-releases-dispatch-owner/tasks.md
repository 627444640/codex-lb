## 1. Implementation

- [x] 1.1 Add a predicate for bodies that name upstream objects only their dispatch account can resolve.
- [x] 1.2 Release the HTTP dispatch-owner binding when the one pre-output admission failover is spent, unless a continuity owner applies.
- [x] 1.3 Request sticky reallocation with that release.
- [x] 1.4 Pass failover and history-replay marks explicitly to each attempt's request-log write.
- [x] 1.5 Skip the terminal retry-exhaustion row when the failed attempt already wrote one; otherwise record the failed account and the marks.
- [x] 1.6 Check the WebSocket and HTTP bridge paths for the same dead end.

## 2. Regression coverage

- [x] 2.1 HTTP: A is overloaded before output and B is healthy. The request completes on B, and only B's row carries the failover flags, with A as the source.
- [x] 2.2 HTTP: B is unavailable. The overload surfaces, with one row on A and no accountless row.
- [x] 2.3 HTTP: B also fails. The second failure surfaces with no third send and no accountless row.
- [x] 2.4 A file pin or an anchor cache miss does not fail over.
- [x] 2.5 Output already started does not fail over.
- [x] 2.6 History replay and admission failover share the one resend.
- [x] 2.7 The predicate keeps the binding for file, container, vector-store, item-reference, and anchor references.
