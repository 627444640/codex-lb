import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiTrendChart } from "./api-trend-chart";

vi.mock("@/components/lazy-recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AreaChart: ({ children, data }: { children: ReactNode; data: unknown[] }) => (
    <div data-testid="token-trend" data-points={JSON.stringify(data)}>{children}</div>
  ),
  Area: ({ dataKey }: { dataKey: string }) => <span data-testid="trend-series">{dataKey}</span>,
  XAxis: () => null,
  YAxis: ({ yAxisId }: { yAxisId: string }) => <span data-testid="trend-axis">{yAxisId}</span>,
  CartesianGrid: () => null,
  Tooltip: () => null,
}));

describe("ApiTrendChart", () => {
  it("renders the token series and axis with chronological usage points", () => {
    render(<ApiTrendChart tokens={[
      { t: "2026-09-24T01:00:00Z", v: 300 },
      { t: "2026-09-24T00:00:00Z", v: 100 },
    ]} />);

    expect(screen.getAllByTestId("trend-series")).toHaveLength(1);
    expect(screen.getByTestId("trend-series")).toHaveTextContent("tokens");
    expect(screen.getAllByTestId("trend-axis")).toHaveLength(1);
    expect(screen.getByTestId("trend-axis")).toHaveTextContent("tokens");
    expect(JSON.parse(screen.getByTestId("token-trend").getAttribute("data-points") ?? "[]")).toEqual([
      { t: "2026-09-24T00:00:00Z", tokens: 100 },
      { t: "2026-09-24T01:00:00Z", tokens: 300 },
    ]);
    expect(screen.queryByText(/cost/i)).not.toBeInTheDocument();
  });

  it("shows the ordinary empty state without a monetary series", () => {
    render(<ApiTrendChart tokens={[]} />);
    expect(screen.queryByTestId("token-trend")).not.toBeInTheDocument();
    expect(screen.queryByTestId("trend-series")).not.toBeInTheDocument();
  });
});
