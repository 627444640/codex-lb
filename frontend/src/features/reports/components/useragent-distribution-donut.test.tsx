import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UseragentDistributionDonut } from "./useragent-distribution-donut";

vi.mock("@/components/lazy-recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/lazy-recharts")>();

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
    PieChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    Pie: ({
      data,
      dataKey,
      onMouseEnter,
      onMouseLeave,
      shape,
    }: {
      data: Array<{ useragent: string }>;
      dataKey: string;
      onMouseEnter?: (entry: { useragent: string }, index: number) => void;
      onMouseLeave?: (entry: { useragent: string }, index: number) => void;
      shape?: unknown;
    }) => (
      <div
        data-testid="useragent-distribution-pie"
        data-key={dataKey}
        data-shape={shape ? "true" : "false"}
      >
        {data.map((entry, index) => (
          <button
            key={entry.useragent}
            type="button"
            data-testid={`useragent-slice-${index}`}
            onMouseEnter={() => onMouseEnter?.(entry, index)}
            onMouseLeave={() => onMouseLeave?.(entry, index)}
          >
            {entry.useragent}
          </button>
        ))}
      </div>
    ),
    Cell: () => null,
  };
});

describe("UseragentDistributionDonut", () => {
  it("highlights the matching legend row when a legend item is hovered", () => {
    render(
      <UseragentDistributionDonut
        data={[
          { useragent: "CLI", costUsd: 12.5, requests: 8, percentage: 62.5 },
          { useragent: "SDK", costUsd: 7.5, requests: 4, percentage: 37.5 },
        ]}
      />,
    );

    const legendRow = screen.getByTestId("useragent-distribution-legend-0");

    expect(screen.getByTestId("useragent-distribution-pie")).toHaveAttribute("data-shape", "true");
    expect(legendRow).toHaveAttribute("data-active", "false");

    fireEvent.mouseEnter(legendRow);
    expect(legendRow).toHaveAttribute("data-active", "true");

    fireEvent.mouseLeave(legendRow);
    expect(legendRow).toHaveAttribute("data-active", "false");
  });

  it("highlights the matching legend row when a pie slice is hovered", () => {
    render(
      <UseragentDistributionDonut
        data={[
          { useragent: "CLI", costUsd: 12.5, requests: 8, percentage: 62.5 },
          { useragent: "SDK", costUsd: 7.5, requests: 4, percentage: 37.5 },
        ]}
      />,
    );

    fireEvent.mouseEnter(screen.getByTestId("useragent-slice-0"));
    expect(screen.getByTestId("useragent-distribution-legend-0")).toHaveAttribute("data-active", "true");
  });

  it("limits the legend viewport to four visible rows before scrolling", () => {
    render(
      <UseragentDistributionDonut
        data={Array.from({ length: 5 }, (_, index) => ({
          useragent: `UA-${index + 1}`,
          costUsd: index + 1,
          requests: index + 1,
          percentage: 20,
        }))}
      />,
    );

    // jsdom 30 simplifies calc() during serialization; authored: calc(4 * 2rem)
    expect(screen.getByTestId("useragent-distribution-legend-list").style.maxHeight).toBe("calc(8rem)");
    expect(screen.getByTestId("useragent-distribution-legend-4")).toBeInTheDocument();
  });

  it("renders Missing User-Agent with a fixed grey legend dot", () => {
    render(
      <UseragentDistributionDonut
        data={[
          { useragent: "Missing User-Agent", costUsd: 12.5, requests: 8, percentage: 62.5 },
          { useragent: "SDK", costUsd: 7.5, requests: 4, percentage: 37.5 },
        ]}
      />,
    );

    const unknownLegendLabel = screen.getAllByText("Missing User-Agent").at(-1);
    const unknownLegendRow = unknownLegendLabel?.closest("div.flex.items-center.gap-2");

    expect(unknownLegendLabel).toBeDefined();
    expect(unknownLegendRow).not.toBeNull();
    expect((unknownLegendRow?.firstElementChild as HTMLElement) ?? null).toHaveStyle({
      background: "#9ca3af",
    });
  });

  it("keeps a real Unknown bucket on the normal palette", () => {
    render(
      <UseragentDistributionDonut
        data={[
          { useragent: "Unknown", costUsd: 12.5, requests: 8, percentage: 62.5 },
          { useragent: "SDK", costUsd: 7.5, requests: 4, percentage: 37.5 },
        ]}
      />,
    );

    const unknownLegendLabel = screen.getAllByText("Unknown").at(-1);
    const unknownLegendRow = unknownLegendLabel?.closest("div.flex.items-center.gap-2");

    expect(unknownLegendLabel).toBeDefined();
    expect(unknownLegendRow).not.toBeNull();
    expect((unknownLegendRow?.firstElementChild as HTMLElement) ?? null).toHaveStyle({
      background: "#3b82f6",
    });
  });

  it("pads legend value cells to the longest formatted request total", async () => {

    render(
      <UseragentDistributionDonut
        data={[
          { useragent: "CLI", costUsd: 12.5, requests: 8, percentage: 10 },
          { useragent: "SDK", costUsd: 120.75, requests: 1200, percentage: 90 },
        ]}
      />,
    );


    const smallRequestLegendValue = screen.getAllByText(/^8$/).at(-1);
    const largeRequestLegendValue = screen.getAllByText("1.2K").at(-1);

    expect(smallRequestLegendValue).toBeDefined();
    expect(largeRequestLegendValue).toBeDefined();
    // jsdom 30's getComputedStyle converts lengths to px, so assert the raw inline style
    expect(smallRequestLegendValue?.style.minWidth).toBe("4ch");
    expect(largeRequestLegendValue?.style.minWidth).toBe("4ch");
  });

  it("uses request counts and percentages regardless of legacy monetary fields", async () => {

    render(
      <UseragentDistributionDonut
        data={[
          { useragent: "CLI", costUsd: 12.5, requests: 8, percentage: 62.5 },
          { useragent: "SDK", costUsd: 7.5, requests: 4, percentage: 37.5 },
        ]}
      />,
    );


    expect(screen.getByText("66.7%")).toBeInTheDocument();
    expect(screen.getByText("33.3%")).toBeInTheDocument();
    expect(screen.getByText(/^4$/)).toBeInTheDocument();
    expect(screen.getByTestId("useragent-distribution-center-value")).toHaveTextContent("12");
    expect(screen.getByTestId("useragent-distribution-pie")).toHaveAttribute("data-key", "requests");
    expect(screen.queryByRole("button", { name: /^cost$/i })).not.toBeInTheDocument();
  });

  it("uses compact request totals in the center and legend without a monetary selector", async () => {

    render(
      <UseragentDistributionDonut
        data={[
          { useragent: "CLI", costUsd: 12.5, requests: 500_000_000, percentage: 40 },
          { useragent: "SDK", costUsd: 7.5, requests: 1_000_000_000, percentage: 60 },
        ]}
      />,
    );


    expect(screen.getByTestId("useragent-distribution-center-value")).toHaveTextContent("1.5B");
    expect(screen.getByText("500M")).toBeInTheDocument();
    expect(screen.getByText("1B")).toBeInTheDocument();
  });

  it("scrolls the hovered pie item into view in the legend list", () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });

    render(
      <UseragentDistributionDonut
        data={Array.from({ length: 5 }, (_, index) => ({
          useragent: `UA-${index + 1}`,
          costUsd: 5 - index,
          requests: index + 1,
          percentage: 20,
        }))}
      />,
    );

    fireEvent.mouseEnter(screen.getByTestId("useragent-slice-4"));

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest", inline: "nearest" });
  });
});
