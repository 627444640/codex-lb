import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import App from "@/App";
import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/utils";

describe("internal dashboard flow", () => {
  it("loads dashboard and settings without anonymous telemetry requests or controls", async () => {
    const user = userEvent.setup({ delay: null });
    const telemetryRequests: string[] = [];
    server.use(
      http.all("/api/settings/telemetry", ({ request }) => {
        telemetryRequests.push(request.method);
        return new HttpResponse(null, { status: 404 });
      }),
    );
    window.history.pushState({}, "", "/dashboard");
    const { queryClient } = renderWithProviders(<App />);
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Request Logs" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Show advanced settings" }));
    expect(await screen.findByRole("heading", { name: "Firewall" })).toBeInTheDocument();
    await waitFor(() => expect(queryClient.isFetching()).toBe(0));
    expect(screen.queryByText("Anonymous telemetry")).not.toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Enable anonymous telemetry" })).not.toBeInTheDocument();
    expect(telemetryRequests).toEqual([]);
  });
});
