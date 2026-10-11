import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nextProvider } from "react-i18next";

import { ReliabilityCards, formatRemaining } from "@/features/accounts/components/reliability-cards";
import i18n from "@/i18n";
import type {
  AccountAdmissionBreakersResponse,
  ConversationHistoryCacheStats,
} from "@/features/accounts/schemas";

const cache: ConversationHistoryCacheStats = {
  enabled: true,
  disabledReason: null,
  bytesUsed: 320 * 1024 * 1024,
  bytesCap: 1024 ** 3,
  conversationBytesCap: 32 * 1024 * 1024,
  entries: 4,
  hits: 2,
  replays: 1,
  idleTtlSeconds: 1800,
  minFreeDiskBytes: 512 * 1024 * 1024,
};

const breakers: AccountAdmissionBreakersResponse = {
  enabled: true,
  failureThreshold: 3,
  windowSeconds: 60,
  openSeconds: 300,
  accounts: [
    {
      accountId: "acct_open",
      state: "open",
      consecutiveFailures: 3,
      windowFailures: 3,
      openUntil: new Date(1_000_000).toISOString(),
      probeInFlight: false,
      errorRate1h: 0.2,
      errorRate24h: null,
      requests1h: 10,
      errors1h: 2,
      requests24h: 0,
      errors24h: 0,
    },
  ],
};

describe("ReliabilityCards", () => {
  it("shows an open countdown and a dash for a null error rate", async () => {
    await i18n.changeLanguage("zh-CN");
    render(
      <I18nextProvider i18n={i18n}>
        <ReliabilityCards breakers={breakers} cache={cache} now={1_000_000 - 125_000} />
      </I18nextProvider>,
    );
    expect(screen.getByText("熔断中")).toBeInTheDocument();
    expect(screen.getByTestId("breaker-countdown")).toHaveTextContent("剩余 2:05 恢复");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText(/60 秒内 3\/3/)).toBeInTheDocument();
    expect(screen.getByText("对话数")).toBeInTheDocument();
    expect(screen.getByTestId("breaker-cards")).not.toContainElement(screen.getByTestId("history-cache-card"));
    expect(formatRemaining(breakers.accounts[0].openUntil ?? "", 1_000_000 - 125_000)).toBe("2:05");
  });

  it("shows a grey banner when the breaker is disabled", async () => {
    await i18n.changeLanguage("zh-CN");
    render(
      <I18nextProvider i18n={i18n}>
        <ReliabilityCards breakers={{ ...breakers, enabled: false }} cache={cache} now={0} />
      </I18nextProvider>,
    );
    expect(screen.getByTestId("breaker-disabled-banner")).toHaveTextContent("熔断未启用");
  });

  it("greys out the cache card when disk is low", async () => {
    await i18n.changeLanguage("zh-CN");
    render(
      <I18nextProvider i18n={i18n}>
        <ReliabilityCards
          breakers={{ ...breakers, accounts: [{ ...breakers.accounts[0], state: "closed", openUntil: null }] }}
          cache={{ ...cache, enabled: false, disabledReason: "low_disk" }}
          now={0}
        />
      </I18nextProvider>,
    );
    expect(screen.getByText("磁盘剩余空间不足，已自动停用")).toBeInTheDocument();
    expect(screen.getByTestId("history-cache-card")).toHaveClass("opacity-60");
  });
});
