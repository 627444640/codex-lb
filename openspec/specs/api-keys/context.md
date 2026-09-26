# Internal token-limit accounting

## Decision and scope

The internal distribution uses token usage and token limits. It does not price requests, create monetary reservations, enforce cost or price-weighted credit rules, or expose billing controls. Model identity and service-tier metadata remain useful routing and diagnostic evidence; they do not select a retail price.

## Historical data

Preserve existing request costs and pricing versions, stored source-model prices, and old monetary limit rows. Historical API response fields may continue reading stored data, but no query computes a current estimate for a null cost or rewrites an old amount. New request-log amounts and pricing versions are null.

An old cost or credits rule is inert even when exhausted or expired. It must not deny an otherwise permitted request or mutate during token settlement. Token-only rule updates and resets preserve dormant monetary records. New monetary/credits rules are rejected atomically. Existing upstream account quotas and reset credits are provider capacity features, not these retired rules.

For example, a key with 100 tokens remaining and an exhausted old monthly cost limit can admit a request whose token reservation fits. It settles reported tokens exactly once and leaves the old cost counter untouched. A model without a listed price follows the same token-limit contract.

## Operations

This policy does not change account credentials, authentication, model restrictions, success-only quota settlement, or data retention. It requires no monetary data migration. Retain the installed package and separate deployment acceptance from changes in a source checkout.

See [API key requirements](spec.md), [internal usage](../internal-token-usage/spec.md), and [observability](../proxy-runtime-observability/spec.md). Prior retail-rate tables remain in Git history and archived change records rather than the active runtime contract.
