import { useTranslation } from "react-i18next";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
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

function OutcomeTag({
  label,
  detail,
  className,
  detailsOpen = false,
}: {
  label: string;
  detail?: string;
  className: string;
  detailsOpen?: boolean;
}) {
  const tag = (
    <span className={className} title={detail}>
      {label}
    </span>
  );
  if (!detail) {
    return tag;
  }
  if (detailsOpen) {
    return (
      <span className="inline-flex flex-col items-start gap-1">
        {tag}
        <span className="rounded-md bg-foreground px-2 py-1 text-xs text-background">{detail}</span>
      </span>
    );
  }
  return (
    <Tooltip open={detailsOpen ? true : undefined}>
      <TooltipTrigger asChild>{tag}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {detail}
      </TooltipContent>
    </Tooltip>
  );
}

export function RequestOutcomeBadge({
  request,
  detailsOpen = false,
}: {
  request: RequestLog;
  detailsOpen?: boolean;
}) {
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
      <OutcomeTag
        className="inline-flex rounded-full bg-sky-500/15 px-2 py-0.5 text-xs font-medium text-sky-700 dark:text-sky-300"
        label={t("dashboard.requests.outcome.failover")}
        detail={t("dashboard.requests.outcome.failoverFrom", { account: from })}
        detailsOpen={detailsOpen}
      />
    );
  }
  if (kind === "replay") {
    return (
      <OutcomeTag
        className="inline-flex rounded-full bg-violet-500/15 px-2 py-0.5 text-xs font-medium text-violet-700 dark:text-violet-300"
        label={t("dashboard.requests.outcome.replay")}
        detail={t("dashboard.requests.outcome.replayDetail", {
          reason: request.historyReplayReason,
          tokens: request.historyReplayExtraTokens ?? 0,
        })}
        detailsOpen={detailsOpen}
      />
    );
  }
  return (
    <OutcomeTag
      className={cn("inline-flex rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-700 dark:text-red-300")}
      label={t("dashboard.requests.outcome.error")}
    />
  );
}
