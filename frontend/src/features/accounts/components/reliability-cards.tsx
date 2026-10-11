import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type {
  AccountAdmissionBreakerStatus,
  AccountAdmissionBreakersResponse,
  ConversationHistoryCacheStats,
} from "@/features/accounts/schemas";
import { cn } from "@/lib/utils";

const POLL_HINT_MS = 15_000;

export function useSecondClock(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) {
    const gb = bytes / 1024 ** 3;
    return `${gb >= 10 ? gb.toFixed(0) : gb.toFixed(1)} GB`;
  }
  if (bytes >= 1024 ** 2) {
    return `${Math.round(bytes / 1024 ** 2)} MB`;
  }
  return `${Math.round(bytes / 1024)} KB`;
}

export function formatRemaining(openUntil: string, now: number): string {
  const end = Date.parse(openUntil);
  if (Number.isNaN(end)) {
    return "0:00";
  }
  const seconds = Math.max(0, Math.floor((end - now) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

function rateText(rate: number | null): string {
  if (rate == null) {
    return "—";
  }
  return `${(rate * 100).toFixed(1)}%`;
}

function rateClass(rate: number | null): string {
  if (rate == null) {
    return "text-foreground";
  }
  if (rate > 0.15) {
    return "text-red-600 dark:text-red-400";
  }
  if (rate > 0.05) {
    return "text-orange-600 dark:text-orange-400";
  }
  return "text-foreground";
}

function RateBlock({
  label,
  rate,
  errors,
  requests,
}: {
  label: string;
  rate: number | null;
  errors: number;
  requests: number;
}) {
  const { t } = useTranslation();
  return (
    <div>
      <div className={cn("text-2xl font-semibold tabular-nums", rateClass(rate))}>{rateText(rate)}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xs text-muted-foreground">
        {rate == null ? t("accounts.reliability.noSamples") : t("accounts.reliability.errorFraction", { errors, requests })}
      </div>
    </div>
  );
}

function BreakerCard({
  account,
  threshold,
  windowSeconds,
  now,
}: {
  account: AccountAdmissionBreakerStatus;
  threshold: number;
  windowSeconds: number;
  now: number;
}) {
  const { t } = useTranslation();
  const stateLabel =
    account.state === "open"
      ? t("accounts.reliability.state.open")
      : account.state === "half_open"
        ? t("accounts.reliability.state.halfOpen")
        : t("accounts.reliability.state.closed");
  const stateClass =
    account.state === "open"
      ? "bg-red-500/15 text-red-700 dark:text-red-300"
      : account.state === "half_open"
        ? "bg-amber-500/15 text-amber-800 dark:text-amber-300"
        : "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
  return (
    <article
      data-testid={`breaker-card-${account.accountId}`}
      data-state={account.state}
      className="rounded-xl border bg-card p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-medium">{account.accountId}</p>
        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", stateClass)}>
          {account.probeInFlight ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
          {stateLabel}
        </span>
      </div>
      {account.state === "open" && account.openUntil ? (
        <p className="mt-2 text-sm text-red-700 dark:text-red-300" data-testid="breaker-countdown">
          {t("accounts.reliability.remaining", { time: formatRemaining(account.openUntil, now) })}
        </p>
      ) : null}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <RateBlock
          label={t("accounts.reliability.rate1h")}
          rate={account.errorRate1h}
          errors={account.errors1h}
          requests={account.requests1h}
        />
        <RateBlock
          label={t("accounts.reliability.rate24h")}
          rate={account.errorRate24h}
          errors={account.errors24h}
          requests={account.requests24h}
        />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        {t("accounts.reliability.footer", {
          consecutive: account.consecutiveFailures,
          window: account.windowFailures,
          windowSeconds,
          threshold,
        })}
      </p>
    </article>
  );
}

export function ReliabilityCards({
  breakers,
  cache,
  now,
}: {
  breakers: AccountAdmissionBreakersResponse;
  cache: ConversationHistoryCacheStats;
  now: number;
}) {
  const { t } = useTranslation();
  const ratio = cache.bytesCap > 0 ? cache.bytesUsed / cache.bytesCap : 0;
  const barClass = ratio > 0.95 ? "bg-red-500" : ratio > 0.8 ? "bg-orange-500" : "bg-primary";
  const disabled = cache.disabledReason != null;
  const disabledText =
    cache.disabledReason === "low_disk"
      ? t("accounts.reliability.cache.lowDisk")
      : cache.disabledReason === "disk_check_failed"
        ? t("accounts.reliability.cache.diskCheckFailed")
        : cache.disabledReason === "disabled"
          ? t("accounts.reliability.cache.disabled")
          : null;
  return (
    <section className="space-y-3" data-poll-ms={POLL_HINT_MS}>
      {breakers.enabled ? null : (
        <p
          data-testid="breaker-disabled-banner"
          className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground"
        >
          {t("accounts.reliability.disabledBanner")}
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="breaker-cards">
        {breakers.accounts.map((account) => (
          <BreakerCard
            key={account.accountId}
            account={account}
            threshold={breakers.failureThreshold}
            windowSeconds={breakers.windowSeconds}
            now={now}
          />
        ))}
      </div>
      <article
        data-testid="history-cache-card"
        aria-disabled={disabled}
        className={cn("max-w-md rounded-xl border bg-card p-4", disabled && "opacity-60")}
      >
        <p className="text-sm font-medium">{t("accounts.reliability.cache.title")}</p>
        {disabledText ? <p className="mt-2 text-sm text-muted-foreground">{disabledText}</p> : null}
        <p className="mt-2 text-sm tabular-nums">
          {formatBytes(cache.bytesUsed)} / {formatBytes(cache.bytesCap)}
        </p>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
          <div className={cn("h-full", barClass)} style={{ width: `${Math.min(100, ratio * 100)}%` }} />
        </div>
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
          <div>
            <dt className="text-xs text-muted-foreground">{t("accounts.reliability.cache.entries")}</dt>
            <dd className="text-lg font-semibold tabular-nums">{cache.entries}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{t("accounts.reliability.cache.hits")}</dt>
            <dd className="text-lg font-semibold tabular-nums">{cache.hits}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{t("accounts.reliability.cache.replays")}</dt>
            <dd className="text-lg font-semibold tabular-nums">{cache.replays}</dd>
          </div>
        </dl>
      </article>
    </section>
  );
}
