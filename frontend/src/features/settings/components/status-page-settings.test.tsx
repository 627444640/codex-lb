import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StatusPageSettings } from "@/features/settings/components/status-page-settings";
import {
  getStatusPageSettings,
  saveAnnouncement,
  updateStatusEmail,
} from "@/features/settings/status-page-api";

vi.mock("@/features/settings/status-page-api", () => ({
  getStatusPageSettings: vi.fn(),
  saveAnnouncement: vi.fn(),
  updateStatusEmail: vi.fn(),
}));

const email = {
  enabled: false,
  host: "smtp.example.invalid",
  port: 465,
  tls: "ssl" as const,
  sender: "sender@example.invalid",
  username: "sender@example.invalid",
  recipients: ["recipient@example.invalid"],
  passwordConfigured: true,
};
const notice = {
  id: 1,
  title: "Planned maintenance",
  body: "Maintenance details",
  level: "maintenance" as const,
  status: "published" as const,
  startsAt: "2026-09-28T04:00:00Z",
  endsAt: null,
  createdAt: "2026-09-28T04:00:00Z",
  updatedAt: "2026-09-28T04:00:00Z",
};

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StatusPageSettings />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getStatusPageSettings).mockResolvedValue({
    available: true,
    email,
    notices: [],
    events: [],
  });
  vi.mocked(updateStatusEmail).mockResolvedValue(email);
  vi.mocked(saveAnnouncement).mockResolvedValue({ id: 1 });
});

describe("StatusPageSettings", () => {
  it("keeps a configured secret when saving another mail field", async () => {
    const user = userEvent.setup();
    mount();
    const sender = await screen.findByLabelText("Sender address");
    await user.clear(sender);
    await user.type(sender, "changed@example.invalid");
    expect(screen.getByLabelText("SMTP authorization code")).toHaveValue("");
    await user.click(
      screen.getByRole("button", { name: "Save email settings" }),
    );
    await waitFor(() => expect(updateStatusEmail).toHaveBeenCalled());
    expect(vi.mocked(updateStatusEmail).mock.calls[0][0]).toMatchObject({
      sender: "changed@example.invalid",
    });
    expect(vi.mocked(updateStatusEmail).mock.calls[0][0]).not.toHaveProperty(
      "password",
    );
  });

  it("publishes an announcement using a timezone-aware schedule", async () => {
    const user = userEvent.setup();
    mount();
    await user.type(
      await screen.findByLabelText("Announcement title"),
      "New announcement",
    );
    await user.type(
      screen.getByLabelText("Announcement body"),
      "Service information",
    );
    await user.click(
      screen.getByRole("button", { name: "Publish announcement" }),
    );
    await waitFor(() => expect(saveAnnouncement).toHaveBeenCalled());
    expect(vi.mocked(saveAnnouncement).mock.calls[0][0]).toMatchObject({
      title: "New announcement",
      body: "Service information",
      status: "published",
    });
    expect(vi.mocked(saveAnnouncement).mock.calls[0][0].startsAt).toMatch(/Z$/);
  });

  it("withdraws an existing notice through the integrated Settings control", async () => {
    vi.mocked(getStatusPageSettings).mockResolvedValue({
      available: true,
      email,
      notices: [notice],
      events: [],
    });
    const user = userEvent.setup();
    mount();
    await user.click(
      await screen.findByRole("button", { name: "Edit Planned maintenance" }),
    );
    await user.click(screen.getByRole("button", { name: "Withdraw" }));
    await waitFor(() =>
      expect(saveAnnouncement).toHaveBeenCalledWith(
        expect.objectContaining({ status: "withdrawn" }),
        1,
      ),
    );
  });

  it("does not offer editable controls while disconnected", async () => {
    vi.mocked(getStatusPageSettings).mockResolvedValue({
      available: false,
      email: null,
      notices: [],
      events: [],
    });
    mount();
    await screen.findByText("The status service is not connected yet.");
    expect(
      screen.queryByRole("button", { name: "Save email settings" }),
    ).not.toBeInTheDocument();
  });
});
