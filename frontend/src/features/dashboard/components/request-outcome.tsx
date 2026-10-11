import { useTranslation } from "react-i18next";

import type { RequestLog } from "@/features/dashboard/schemas";
import { cn } from "@/lib/utils";

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

export function RequestOutcomeBadge({ request }: { request: RequestLog }) {
  const { t } = useTranslation();
  const kind = requestOutcome(request);
  if (kind === "none") {
    return null;
  }
  if (kind === "failover") {
    const from = request.admissionFailoverFromAccountId
      ? maskAccountId(request.admissionFailoverFromAccountId)
      : "••••";
    return (
      <span
        className="inline-flex rounded-full bg-sky-500/15 px-2 py-0.5 text-xs font-medium text-sky-700 dark:text-sky-300"
        title={t("dashboard.requests.outcome.failoverFrom", { account: from })}
      >
        {t("dashboard.requests.outcome.failover")}
      </span>
    );
  }
  if (kind === "replay") {
    return (
      <span
        className="inline-flex rounded-full bg-violet-500/15 px-2 py-0.5 text-xs font-medium text-violet-700 dark:text-violet-300"
        title={t("dashboard.requests.outcome.replayDetail", {
          reason: request.historyReplayReason,
          tokens: request.historyReplayExtraTokens ?? 0,
        })}
      >
        {t("dashboard.requests.outcome.replay")}
      </span>
    );
  }
  return (
    <span className={cn("inline-flex rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-700 dark:text-red-300")}>
      {t("dashboard.requests.outcome.error")}
    </span>
  );
}
