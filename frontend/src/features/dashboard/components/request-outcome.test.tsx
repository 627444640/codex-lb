import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { RequestOutcomeBadge } from "@/features/dashboard/components/request-outcome";
import { RequestLogSchema, type RequestLog } from "@/features/dashboard/schemas";
import i18n from "@/i18n";

function request(partial: Record<string, unknown>): RequestLog {
  return RequestLogSchema.parse({
    requestedAt: "2026-10-11T08:00:00+00:00",
    accountId: "acct_ok",
    requestId: "req",
    model: "gpt-5.4",
    status: "ok",
    errorCode: null,
    errorMessage: null,
    tokens: 1,
    cachedInputTokens: 0,
    reasoningEffort: null,
    costUsd: null,
    latencyMs: 1,
    ...partial,
  });
}

describe("RequestOutcomeBadge", () => {
  it("shows the three Chinese outcome tags", async () => {
    await i18n.changeLanguage("zh-CN");
    render(
      <I18nextProvider i18n={i18n}>
        <TooltipProvider>
          <RequestOutcomeBadge
            request={request({
              admissionFailoverRetried: true,
              admissionFailoverFromAccountId: "acct_from_9f3a",
            })}
          />
          <RequestOutcomeBadge
            request={request({
              historyReplayReason: "stream_incomplete",
              historyReplayExtraTokens: 128,
            })}
          />
          <RequestOutcomeBadge
            request={request({ status: "error", errorCode: "server_error", errorMessage: "overloaded" })}
          />
        </TooltipProvider>
      </I18nextProvider>,
    );
    expect(screen.getByText("已换号")).toHaveAttribute("title", "从 acct…9f3a 换来");
    expect(screen.getByText("已重发")).toHaveAttribute("title", "stream_incomplete +128 tokens");
    expect(screen.getByText("报错")).toBeInTheDocument();
  });
});
