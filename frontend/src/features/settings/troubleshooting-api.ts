import { z } from "zod";
import { del, get, post, put } from "@/lib/api-client";

export const GuideContentSchema = z.object({
  code: z.string().trim().min(1).max(48),
  title: z.string().trim().min(1).max(100),
  signature: z.string().max(160),
  scope: z.string().trim().min(1).max(1000),
  cause: z.string().trim().min(1).max(3000),
  solutions: z.array(z.string().trim().min(1).max(1000)).min(1).max(12),
  limitations: z.string().max(2000),
  endpointUrl: z.string().max(2048).refine((value) => {
    if (!value) return true;
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password && !/[\s\\]/.test(value);
    } catch { return false; }
  }),
  endpointLabel: z.string().max(80),
  endpointHelp: z.string().max(1000),
  status: z.enum(["draft", "published", "withdrawn"]),
  sortOrder: z.number().int().min(0).max(1000000),
});
export const GuideSchema = GuideContentSchema.extend({
  id: z.number(), slug: z.string(), revision: z.number(),
  createdAt: z.string(), updatedAt: z.string(), deletedAt: z.string().nullable(),
});
const GuideListSchema = z.object({ available: z.boolean(), guides: z.array(GuideSchema) });
export type Guide = z.infer<typeof GuideSchema>;
export type GuideContent = z.infer<typeof GuideContentSchema>;
export type GuideWrite = GuideContent & { revision?: number };
const BASE = "/api/settings/status-page/guides";
export const getGuides = () => get(BASE, GuideListSchema);
export const saveGuide = (body: GuideWrite, id?: number) => id === undefined
  ? post(BASE, GuideSchema, { body })
  : put(`${BASE}/${id}`, GuideSchema, { body });
export const deleteGuide = (guide: Guide) => del(`${BASE}/${guide.id}`, GuideSchema, { body: { revision: guide.revision } });
export const restoreGuide = (guide: Guide) => post(`${BASE}/${guide.id}/restore`, GuideSchema, { body: { revision: guide.revision } });
