import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RecentRequestsTable } from "@/features/dashboard/components/recent-requests-table";
import { RequestLogSchema, type RequestLog } from "@/features/dashboard/schemas";
import { createRequestLogEntry } from "@/test/mocks/factories";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/features/conversation-archive/components/request-archive-panel", () => ({
  RequestArchivePanel: () => null,
}));

function renderUsage(overrides: Partial<RequestLog>) {
  const request = createRequestLogEntry(overrides);
  renderWithProviders(
    <RecentRequestsTable
      requests={[request]}
      accounts={[]}
      total={1}
      limit={25}
      offset={0}
      hasMore={false}
      visibleColumns={["tokens", "details"]}
      onLimitChange={vi.fn()}
      onOffsetChange={vi.fn()}
    />,
  );
  return within(screen.getAllByRole("row")[1]);
}

function openDetails() {
  fireEvent.click(screen.getByRole("button", { name: "View Details" }));
  return within(screen.getByRole("dialog"));
}

describe("reported token completeness", () => {
  it("labels a known lower bound and leaves absent output unknown", () => {
    const row = renderUsage({
      tokens: 120, inputTokens: 100, outputTokens: null, outputTokensRaw: null,
      reasoningTokens: 20, cachedInputTokens: 30, cacheWriteTokens: 10, usageStatus: "partial",
    });
    expect(row.getByText("≥ 120")).toBeInTheDocument();
    expect(row.getByText("Partial usage")).toBeInTheDocument();
    const dialog = openDetails();
    expect(dialog.getByText("Partial usage")).toBeInTheDocument();
    expect(dialog.getByText("Output tokens (includes reasoning)").closest(".space-y-1")).toHaveTextContent("Unknown");
    expect(dialog.getByText(/The known total is a lower bound/)).toBeInTheDocument();
  });

  it("shows measured zero as complete rather than missing", () => {
    const row = renderUsage({
      tokens: 0, inputTokens: 0, outputTokens: 0, outputTokensRaw: 0,
      reasoningTokens: null, cachedInputTokens: null, usageStatus: "complete",
    });
    expect(row.getByText("0")).toBeInTheDocument();
    expect(row.queryByText("Unknown")).not.toBeInTheDocument();
    expect(row.queryByText("Partial usage")).not.toBeInTheDocument();
    expect(openDetails().getByText("Complete usage")).toBeInTheDocument();
  });

  it("does not display missing usage as a zero measurement", () => {
    const row = renderUsage({
      tokens: null, inputTokens: null, outputTokens: null, outputTokensRaw: null,
      reasoningTokens: null, cachedInputTokens: null, usageStatus: "missing",
    });
    expect(row.getByText("Unknown")).toBeInTheDocument();
    expect(row.queryByText("0")).not.toBeInTheDocument();
    const dialog = openDetails();
    expect(dialog.getByText("Usage missing")).toBeInTheDocument();
    expect(dialog.getByText(/unknown usage, not measured zero/)).toBeInTheDocument();
  });

  it("accepts an older response without completeness metadata without inventing a status", () => {
    const row = renderUsage({ tokens: 120, usageStatus: undefined });
    expect(row.getByText("120")).toBeInTheDocument();
    expect(row.queryByText("Partial usage")).not.toBeInTheDocument();
    expect(openDetails().queryByText("Complete usage")).not.toBeInTheDocument();
  });

  it("rejects an unrecognized completeness status", () => {
    expect(RequestLogSchema.safeParse({ ...createRequestLogEntry(), usageStatus: "estimated" }).success).toBe(false);
  });
});
