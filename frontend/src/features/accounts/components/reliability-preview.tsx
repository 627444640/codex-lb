import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ReliabilityCards } from "@/features/accounts/components/reliability-cards";
import type {
  AccountAdmissionBreakersResponse,
  ConversationHistoryCacheStats,
} from "@/features/accounts/schemas";

const OPEN_UNTIL = new Date(Date.now() + 4 * 60 * 1000 + 12 * 1000).toISOString();

const healthyCache: ConversationHistoryCacheStats = {
  enabled: true,
  disabledReason: null,
  bytesUsed: 320 * 1024 * 1024,
  bytesCap: 1024 ** 3,
  conversationBytesCap: 32 * 1024 * 1024,
  entries: 42,
  hits: 18,
  replays: 3,
  idleTtlSeconds: 1800,
  minFreeDiskBytes: 512 * 1024 * 1024,
};

function breakers(state: string): AccountAdmissionBreakersResponse {
  if (state === "null-rates") {
    return {
      enabled: true,
      failureThreshold: 3,
      windowSeconds: 60,
      openSeconds: 300,
      accounts: [
        {
          accountId: "acct_quiet",
          state: "closed",
          consecutiveFailures: 0,
          windowFailures: 0,
          openUntil: null,
          probeInFlight: false,
          errorRate1h: null,
          errorRate24h: null,
          requests1h: 0,
          errors1h: 0,
          requests24h: 0,
          errors24h: 0,
        },
      ],
    };
  }
  if (state === "open") {
    return {
      enabled: true,
      failureThreshold: 3,
      windowSeconds: 60,
      openSeconds: 300,
      accounts: [
        {
          accountId: "acct_sick",
          state: "open",
          consecutiveFailures: 3,
          windowFailures: 3,
          openUntil: OPEN_UNTIL,
          probeInFlight: false,
          errorRate1h: 0.22,
          errorRate24h: 0.08,
          requests1h: 40,
          errors1h: 9,
          requests24h: 200,
          errors24h: 16,
        },
      ],
    };
  }
  return {
    enabled: true,
    failureThreshold: 3,
    windowSeconds: 60,
    openSeconds: 300,
    accounts: [
      {
        accountId: "acct_ok",
        state: "closed",
        consecutiveFailures: 0,
        windowFailures: 1,
        openUntil: null,
        probeInFlight: false,
        errorRate1h: 0.02,
        errorRate24h: 0.01,
        requests1h: 50,
        errors1h: 1,
        requests24h: 400,
        errors24h: 4,
      },
      {
        accountId: "acct_probe",
        state: "half_open",
        consecutiveFailures: 0,
        windowFailures: 0,
        openUntil: null,
        probeInFlight: true,
        errorRate1h: 0.06,
        errorRate24h: 0.04,
        requests1h: 20,
        errors1h: 1,
        requests24h: 80,
        errors24h: 3,
      },
    ],
  };
}

function cacheFor(state: string): ConversationHistoryCacheStats {
  if (state === "low-disk") {
    return { ...healthyCache, enabled: false, disabledReason: "low_disk", bytesUsed: 900 * 1024 * 1024 };
  }
  return healthyCache;
}

export function ReliabilityPreview() {
  const { i18n } = useTranslation();
  const [params] = useSearchParams();
  const state = params.get("state") ?? "normal";
  useEffect(() => {
    void i18n.changeLanguage("zh-CN");
  }, [i18n]);
  return (
    <div className="mx-auto max-w-5xl p-6">
      <ReliabilityCards breakers={breakers(state)} cache={cacheFor(state)} now={Date.now()} />
    </div>
  );
}
