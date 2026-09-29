import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TroubleshootingSettings } from "@/features/settings/components/troubleshooting-settings";
import { deleteGuide, getGuides, restoreGuide, saveGuide } from "@/features/settings/troubleshooting-api";
import type { Guide } from "@/features/settings/troubleshooting-api";

vi.mock("@/features/settings/troubleshooting-api", async importOriginal => {
  const actual = await importOriginal<typeof import("@/features/settings/troubleshooting-api")>();
  return { ...actual, getGuides: vi.fn(), saveGuide: vi.fn(), deleteGuide: vi.fn(), restoreGuide: vi.fn() };
});

const guide: Guide = {
  id: 1, slug: "error-ws", revision: 3, code: "WS", title: "Large request", signature: "payload_too_large",
  scope: "Request is too large", cause: "Many images", solutions: ["Reduce the image"], limitations: "No automatic retry",
  endpointUrl: "", endpointLabel: "API address", endpointHelp: "", status: "published", sortOrder: 20,
  createdAt: "2026-09-28T04:00:00Z", updatedAt: "2026-09-28T04:00:00Z", deletedAt: null,
};

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><TroubleshootingSettings /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getGuides).mockResolvedValue({ available: true, guides: [guide] });
  vi.mocked(saveGuide).mockResolvedValue(guide);
  vi.mocked(deleteGuide).mockResolvedValue({ ...guide, deletedAt: "2026-09-28T05:00:00Z", status: "draft", revision: 4 });
  vi.mocked(restoreGuide).mockResolvedValue({ ...guide, status: "draft", revision: 5 });
});

describe("TroubleshootingSettings", () => {
  it("creates a private draft and previews markup as text", async () => {
    const user = userEvent.setup(); const { container } = mount();
    await user.click(await screen.findByRole("button", { name: "New guide" }));
    for (const [label, value] of [["Error code or identifier", "TEST"], ["Guide title", "New test guide"],
      ["Symptoms", "A symptom"], ["Cause", "<img src=x onerror=alert(1)>"], ["Solution steps", "First step\n\nSecond step"]]) {
      await user.type(screen.getByLabelText(label), value);
    }
    await user.click(screen.getByRole("button", { name: "Preview content" }));
    expect(screen.getByRole("article", { name: "Preview content" })).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(container.querySelector("img")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Save guide draft" }));
    await waitFor(() => expect(saveGuide).toHaveBeenCalledWith(expect.objectContaining({ status: "draft", solutions: ["First step", "Second step"] }), undefined));
  });

  it("edits order and publishes with the captured revision", async () => {
    const user = userEvent.setup(); mount();
    await user.click(await screen.findByRole("button", { name: "Edit Large request" }));
    const order = screen.getByLabelText("Order (lower appears first)");
    await user.clear(order); await user.type(order, "5");
    await user.click(screen.getByRole("button", { name: "Save and publish guide" }));
    await waitFor(() => expect(saveGuide).toHaveBeenCalledWith(expect.objectContaining({ revision: 3, sortOrder: 5, status: "published" }), 1));
  });

  it("searches content, confirms deletion and restores from Deleted", async () => {
    const user = userEvent.setup(); mount();
    const search = await screen.findByRole("textbox", { name: "Search error codes, titles or content" });
    await user.type(search, "no-match"); expect(screen.queryByRole("button", { name: "Edit Large request" })).not.toBeInTheDocument();
    await user.clear(search); await user.type(search, "Reduce the image");
    await user.click(screen.getByRole("button", { name: "Delete Large request" }));
    expect(deleteGuide).not.toHaveBeenCalled();
    vi.mocked(getGuides).mockResolvedValue({ available: true, guides: [{ ...guide, status: "draft", deletedAt: "2026-09-28T05:00:00Z", revision: 4 }] });
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(deleteGuide).toHaveBeenCalledWith(guide, expect.anything()));
    await user.selectOptions(screen.getByLabelText("Filter guide status"), "deleted");
    await user.click(await screen.findByRole("button", { name: "Restore as draft Large request" }));
    await waitFor(() => expect(restoreGuide).toHaveBeenCalledWith(expect.objectContaining({ revision: 4 }), expect.anything()));
  });

  it("retains editor content when saving fails and offers no edits while disconnected", async () => {
    vi.mocked(saveGuide).mockRejectedValue(new Error("Guide changed; refresh first"));
    const user = userEvent.setup(); const view = mount();
    await user.click(await screen.findByRole("button", { name: "Edit Large request" }));
    await user.click(screen.getByRole("button", { name: "Save and publish guide" }));
    await screen.findByText("Guide changed; refresh first");
    expect(screen.getByLabelText("Guide title")).toHaveValue("Large request");
    view.unmount();
    vi.mocked(getGuides).mockResolvedValue({ available: false, guides: [] });
    mount(); await screen.findByText("The status service is not connected yet.");
    expect(screen.queryByRole("button", { name: "New guide" })).not.toBeInTheDocument();
  });
});
