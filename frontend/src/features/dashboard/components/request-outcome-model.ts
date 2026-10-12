import type { RequestLog } from "@/features/dashboard/schemas";

export type RequestOutcomeKind = "failover" | "replay" | "error" | "none";

export function maskAccountId(accountId: string): string {
  if (accountId.length <= 8) {
    return "••••";
  }
  return `${accountId.slice(0, 4)}…${accountId.slice(-4)}`;
}

export function requestOutcome(request: RequestLog): RequestOutcomeKind {
  if (request.historyReplayReason) {
    return "replay";
  }
  if (request.admissionFailoverRetried) {
    return "failover";
  }
  if (request.status !== "ok" && request.status !== "cancelled") {
    return "error";
  }
  return "none";
}
