import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ModelDistributionDonut } from "./model-distribution-donut";

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
      data: Array<{ model: string }>;
      dataKey: string;
      onMouseEnter?: (entry: { model: string }, index: number) => void;
      onMouseLeave?: (entry: { model: string }, index: number) => void;
      shape?: unknown;
    }) => (
      <div
        data-testid="model-distribution-pie"
        data-key={dataKey}
        data-shape={shape ? "true" : "false"}
      >
        {data.map((entry, index) => (
          <button
            key={entry.model}
            type="button"
            data-testid={`model-slice-${index}`}
            onMouseEnter={() => onMouseEnter?.(entry, index)}
            onMouseLeave={() => onMouseLeave?.(entry, index)}
          >
            {entry.model}
          </button>
        ))}
      </div>
    ),
    Cell: () => null,
  };
});

describe("ModelDistributionDonut", () => {
  it("highlights the matching legend row when a legend item is hovered", () => {
    render(
      <ModelDistributionDonut
        data={[
          { model: "gpt-5", costUsd: 42.02, requests: 2, percentage: 70 },
          { model: "o3", costUsd: 18.03, requests: 8, percentage: 30 },
        ]}
      />,
    );

    const legendRow = screen.getByTestId("model-distribution-legend-0");

    expect(screen.getByTestId("model-distribution-pie")).toHaveAttribute("data-shape", "true");
    expect(legendRow).toHaveAttribute("data-active", "false");

    fireEvent.mouseEnter(legendRow);
    expect(legendRow).toHaveAttribute("data-active", "true");

    fireEvent.mouseLeave(legendRow);
    expect(legendRow).toHaveAttribute("data-active", "false");
  });

  it("highlights the matching legend row when a pie slice is hovered", () => {
    render(
      <ModelDistributionDonut
        data={[
          { model: "gpt-5", costUsd: 42.02, requests: 2, percentage: 70 },
          { model: "o3", costUsd: 18.03, requests: 8, percentage: 30 },
        ]}
      />,
    );

    const slice = screen.getByTestId("model-slice-0");
    const legendRow = screen.getByTestId("model-distribution-legend-0");

    fireEvent.mouseEnter(slice);
    expect(legendRow).toHaveAttribute("data-active", "true");
  });

  it("limits the legend viewport to four visible rows before scrolling", () => {
    render(
      <ModelDistributionDonut
        data={Array.from({ length: 5 }, (_, index) => ({
          model: `model-${index + 1}`,
          costUsd: index + 1,
          requests: index + 1,
          percentage: 20,
        }))}
      />,
    );

    // jsdom 30 simplifies calc() during serialization; authored: calc(4 * 2rem)
    expect(screen.getByTestId("model-distribution-legend-list").style.maxHeight).toBe("calc(8rem)");
    expect(screen.getByTestId("model-distribution-legend-4")).toBeInTheDocument();
  });

  it("uses request counts and percentages regardless of legacy monetary fields", async () => {

    render(
      <ModelDistributionDonut
        data={[
          { model: "gpt-5", costUsd: 42.02, requests: 2, percentage: 70 },
          { model: "o3", costUsd: 18.03, requests: 8, percentage: 30 },
        ]}
      />,
    );


    expect(screen.getByText("20.0%")).toBeInTheDocument();
    expect(screen.getByText("80.0%")).toBeInTheDocument();
    expect(screen.getByText(/^8$/)).toBeInTheDocument();
    expect(screen.getByTestId("model-distribution-center-value")).toHaveTextContent("10");
    expect(screen.getByTestId("model-distribution-pie")).toHaveAttribute("data-key", "requests");
    expect(screen.queryByRole("button", { name: /^cost$/i })).not.toBeInTheDocument();
  });

  it("uses compact request totals in the center and legend without a monetary selector", async () => {

    render(
      <ModelDistributionDonut
        data={[
          { model: "gpt-5", costUsd: 42.02, requests: 500_000_000, percentage: 40 },
          { model: "o3", costUsd: 18.03, requests: 1_000_000_000, percentage: 60 },
        ]}
      />,
    );


    expect(screen.getByTestId("model-distribution-center-value")).toHaveTextContent("1.5B");
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
      <ModelDistributionDonut
        data={Array.from({ length: 5 }, (_, index) => ({
          model: `model-${index + 1}`,
          costUsd: 5 - index,
          requests: index + 1,
          percentage: 20,
        }))}
      />,
    );

    fireEvent.mouseEnter(screen.getByTestId("model-slice-4"));

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest", inline: "nearest" });
  });
});
