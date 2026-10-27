## Context

The cached read is followed by a repository factory and multiple sequential database reads. A burst can miss the same key before the first caller stores its detached snapshot. Each caller currently creates its own session, which is correct for SQLAlchemy but needlessly duplicates identical reads.

## Decisions

Keep the initial cache-hit check unchanged. On miss, enter a per-key load guard and recheck the cache before opening the repository scope. The first caller loads; waiters subsequently read independent cloned snapshots. Distinct scopes use independent locks, and disabled caching bypasses coordination.

Gate reference counts are adjusted synchronously around lock acquisition. The final owner/waiter removes the gate even on cancellation. Invalidation clears snapshots and advances the existing generation but does not remove live gates. An invalidated load cannot repopulate the cache; waiting calls reload with the current generation.

## Risks / Trade-offs

A waiter now waits for the existing same-scope database read; request deadlines and cancellation still apply. A cancelled owner yields ownership so a waiter can retry. No background loader task is introduced, so there is no new detached-task lifecycle. Miss-path coordination adds no global serialization and cache hits still avoid locks.

## Validation

The public-selection cold-burst regression first reproduces 20 concurrent snapshot loads for 20 requests; after coordination it observes one load and 20 detached account results. Related cache, selection and invalidation suites pass 82 tests, including cancelled owners/waiters, distinct-key progress, disabled caching, generation invalidation and gate retirement. This is a database-work amplification result under a deterministic test, not a production throughput claim.
