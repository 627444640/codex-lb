import { z } from "zod";
import { get, post, put } from "@/lib/api-client";

export const StatusEmailSchema = z.object({
  enabled: z.boolean(),
  host: z.string(),
  port: z.number(),
  tls: z.enum(["ssl", "starttls"]),
  sender: z.string(),
  username: z.string(),
  recipients: z.array(z.string()),
  passwordConfigured: z.boolean(),
});
export const AnnouncementSchema = z.object({
  id: z.number(),
  title: z.string(),
  body: z.string(),
  level: z.enum(["info", "maintenance", "warning"]),
  status: z.enum(["draft", "published", "withdrawn"]),
  startsAt: z.string(),
  endsAt: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export const StatusQuotaSchema = z.object({
  stale: z.boolean(),
  collectedAt: z.string().nullable(),
  routability: z.enum(["operational", "outage", "unknown"]),
  routabilityDetail: z.string(),
  lowQuotaStatus: z.enum(["operational", "degraded", "unknown"]),
  lowQuotaThreshold: z.number(),
  lowestRemainingPercent: z.number().nullable(),
  activeAccounts: z.number().nullable(),
  quotaReady: z.number().nullable(),
  quotaUnknown: z.number().nullable(),
  quotaExhausted: z.number().nullable(),
  weeklyRemainingPercent: z.number().nullable(),
  weeklyNextResetAt: z.string().nullable(),
});
export const StatusPageSettingsSchema = z.object({
  available: z.boolean(),
  email: StatusEmailSchema.nullable(),
  quota: StatusQuotaSchema.nullable(),
  notices: z.array(AnnouncementSchema),
  events: z.array(
    z.object({
      id: z.number(),
      title: z.string(),
      createdAt: z.string(),
      emailStatus: z.enum([
        "disabled",
        "pending",
        "retry",
        "failed",
        "sent",
        "superseded",
      ]),
      attempts: z.number(),
      lastError: z.string().nullable(),
    }),
  ),
});
export type StatusEmail = z.infer<typeof StatusEmailSchema>;
export type StatusEmailUpdate = Omit<StatusEmail, "passwordConfigured"> & {
  password?: string;
};
export type Announcement = z.infer<typeof AnnouncementSchema>;
export type StatusQuota = z.infer<typeof StatusQuotaSchema>;
export type AnnouncementUpdate = Omit<
  Announcement,
  "id" | "createdAt" | "updatedAt"
>;
const BASE = "/api/settings/status-page";
export const getStatusPageSettings = () => get(BASE, StatusPageSettingsSchema);
export const updateStatusEmail = (body: StatusEmailUpdate) =>
  put(`${BASE}/email`, StatusEmailSchema, { body });
export const saveAnnouncement = (body: AnnouncementUpdate, id?: number) =>
  id === undefined
    ? post(`${BASE}/announcements`, z.object({ id: z.number() }), { body })
    : put(`${BASE}/announcements/${id}`, z.object({ id: z.number() }), {
        body,
      });
