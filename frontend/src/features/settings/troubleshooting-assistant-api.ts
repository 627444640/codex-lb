import { z } from "zod";
import { get, post, put } from "@/lib/api-client";

export const AssistantConfigurationSchema = z.object({
  available: z.boolean(), enabled: z.boolean(), baseUrl: z.string(), model: z.string(),
  requestsPerMinute: z.number(), dailyRequestLimit: z.number(), keyConfigured: z.boolean(), dailyRequestsUsed: z.number(),
});
export type AssistantConfiguration = z.infer<typeof AssistantConfigurationSchema>;
export type AssistantConfigurationUpdate = Omit<AssistantConfiguration, "available" | "keyConfigured" | "dailyRequestsUsed"> & { apiKey?: string; clearKey: boolean };
const BASE = "/api/settings/status-page/assistant";
export const getAssistantConfiguration = () => get(BASE, AssistantConfigurationSchema);
export const saveAssistantConfiguration = (body: AssistantConfigurationUpdate) => put(BASE, AssistantConfigurationSchema, { body });
export const testAssistantConnection = () => post(`${BASE}/test`, z.object({ ok: z.boolean(), message: z.string() }), { body: {}, signal: AbortSignal.timeout(60000) });
