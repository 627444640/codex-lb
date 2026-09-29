import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TroubleshootingAssistantSettings } from "@/features/settings/components/troubleshooting-assistant-settings";
import { getAssistantConfiguration, saveAssistantConfiguration, testAssistantConnection } from "@/features/settings/troubleshooting-assistant-api";

vi.mock("@/features/settings/troubleshooting-assistant-api", () => ({
  getAssistantConfiguration: vi.fn(), saveAssistantConfiguration: vi.fn(), testAssistantConnection: vi.fn(),
}));
const data = { available: true, enabled: false, baseUrl: "http://127.0.0.1:2455/v1", model: "mercury-2.5",
  requestsPerMinute: 6, dailyRequestLimit: 200, keyConfigured: true, dailyRequestsUsed: 0 };
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><TroubleshootingAssistantSettings /></QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks(); vi.mocked(getAssistantConfiguration).mockResolvedValue(data);
  vi.mocked(saveAssistantConfiguration).mockResolvedValue(data);
  vi.mocked(testAssistantConnection).mockResolvedValue({ ok: true, message: "Synthetic generation completed" });
});
describe("TroubleshootingAssistantSettings", () => {
  it("keeps an existing key blank and does not run a model when saving", async () => {
    const user = userEvent.setup(); mount();
    const model = await screen.findByLabelText("Model ID");
    expect(model).toHaveValue("mercury-2.5");
    expect(screen.getByLabelText("Model API key")).toHaveValue("");
    await user.clear(model); await user.type(model, "updated-synthetic-model");
    await user.click(screen.getByRole("button", { name: "Save model settings" }));
    await waitFor(() => expect(saveAssistantConfiguration).toHaveBeenCalled());
    expect(vi.mocked(saveAssistantConfiguration).mock.calls[0][0]).not.toHaveProperty("apiKey");
    expect(vi.mocked(saveAssistantConfiguration).mock.calls[0][0].model).toBe("updated-synthetic-model");
    expect(vi.mocked(saveAssistantConfiguration).mock.calls[0][0]).not.toHaveProperty("models");
    expect(testAssistantConnection).not.toHaveBeenCalled();
  });
  it("supports clearing the key and explicitly testing saved settings", async () => {
    const user = userEvent.setup(); mount();
    await user.click(await screen.findByRole("button", { name: "Test saved model" }));
    await waitFor(() => expect(testAssistantConnection).toHaveBeenCalled());
    await user.click(screen.getByLabelText("Clear the saved key and disable the assistant"));
    await user.click(screen.getByRole("button", { name: "Save model settings" }));
    await waitFor(() => expect(saveAssistantConfiguration).toHaveBeenCalledWith(expect.objectContaining({ enabled: false, clearKey: true }), expect.anything()));
  });
  it("shows no usable model controls while disconnected", async () => {
    vi.mocked(getAssistantConfiguration).mockResolvedValue({ ...data, available: false });
    mount(); await screen.findByText("The status service is not connected yet.");
    expect(screen.queryByLabelText("Model API key")).not.toBeInTheDocument();
  });
  it.each(["mercury2.5,second", "mercury2.5 second", "mercury2.5;second"])("rejects a multi-model value %s even when disabled", async value => {
    const user = userEvent.setup(); mount();
    const model = await screen.findByLabelText("Model ID");
    await user.clear(model); await user.type(model, value);
    await user.click(screen.getByRole("button", { name: "Save model settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter exactly one model ID");
    expect(saveAssistantConfiguration).not.toHaveBeenCalled();
    expect(testAssistantConnection).not.toHaveBeenCalled();
  });
  it("rejects a pasted multiline model list without silently joining the names", async () => {
    const user = userEvent.setup(); mount();
    const model = await screen.findByLabelText("Model ID");
    await user.click(model); await user.paste("mercury2.5\nsecond");
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter exactly one model ID");
    expect(model).toHaveValue("mercury-2.5");
    expect(saveAssistantConfiguration).not.toHaveBeenCalled();
  });
  it("requires a model even when disabled", async () => {
    const user = userEvent.setup(); mount();
    const model = await screen.findByLabelText("Model ID");
    await user.clear(model);
    await user.click(screen.getByRole("button", { name: "Save model settings" }));
    expect(model).toBeRequired();
    expect(model).toBeInvalid();
    expect(saveAssistantConfiguration).not.toHaveBeenCalled();
  });
});
