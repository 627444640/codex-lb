import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Megaphone } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { AlertMessage } from "@/components/alert-message";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getErrorMessageOrNull } from "@/utils/errors";
import {
  getStatusPageSettings,
  saveAnnouncement,
  updateStatusEmail,
} from "@/features/settings/status-page-api";
import type {
  Announcement,
  AnnouncementUpdate,
  StatusEmail,
  StatusEmailUpdate,
} from "@/features/settings/status-page-api";

const QUERY_KEY = ["settings", "status-page"];
const inputTime = (iso: string) =>
  new Date(new Date(iso).getTime() + 8 * 3600000).toISOString().slice(0, 16);
const isoTime = (value: string) => new Date(`${value}:00+08:00`).toISOString();
const displayTime = (iso: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Taipei",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));

function EmailForm({
  email,
  busy,
  save,
}: {
  email: StatusEmail;
  busy: boolean;
  save: (data: StatusEmailUpdate) => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState(email);
  const [password, setPassword] = useState("");
  const [recipients, setRecipients] = useState(email.recipients.join(", "));
  const field = (key: "host" | "sender" | "username", type = "text") => (
    <div className="space-y-2">
      <Label htmlFor={`status-email-${key}`}>{t(`statusPage.${key}`)}</Label>
      <Input
        id={`status-email-${key}`}
        type={type}
        value={form[key]}
        disabled={busy}
        required
        onChange={(event) => setForm({ ...form, [key]: event.target.value })}
      />
    </div>
  );
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        save({
          enabled: form.enabled,
          host: form.host,
          port: form.port,
          tls: form.tls,
          sender: form.sender,
          username: form.username,
          recipients: recipients
            .split(/[,，;；\n]/)
            .map((s) => s.trim())
            .filter(Boolean),
          ...(password ? { password } : {}),
        });
        setPassword("");
      }}
    >
      <div className="flex items-center justify-between gap-4">
        <div>
          <Label htmlFor="status-email-enabled">
            {t("statusPage.emailEnabled")}
          </Label>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("statusPage.emailHelp")}
          </p>
        </div>
        <Switch
          id="status-email-enabled"
          checked={form.enabled}
          disabled={busy}
          onCheckedChange={(enabled) => setForm({ ...form, enabled })}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {field("sender", "email")}
        {field("username")}
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="status-email-recipients">
            {t("statusPage.recipients")}
          </Label>
          <Input
            id="status-email-recipients"
            value={recipients}
            disabled={busy}
            required
            onChange={(e) => setRecipients(e.target.value)}
          />
        </div>
        {field("host")}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor="status-email-port">{t("statusPage.port")}</Label>
            <Input
              id="status-email-port"
              type="number"
              min={1}
              max={65535}
              value={form.port}
              disabled={busy}
              required
              onChange={(e) =>
                setForm({ ...form, port: Number(e.target.value) })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="status-email-tls">
              {t("statusPage.encryption")}
            </Label>
            <Select
              value={form.tls}
              disabled={busy}
              onValueChange={(tls: "ssl" | "starttls") =>
                setForm({ ...form, tls })
              }
            >
              <SelectTrigger id="status-email-tls">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ssl">SSL / TLS</SelectItem>
                <SelectItem value="starttls">STARTTLS</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="status-email-password">
            {t("statusPage.password")}
          </Label>
          <Input
            id="status-email-password"
            type="password"
            autoComplete="new-password"
            maxLength={1024}
            value={password}
            disabled={busy}
            placeholder={t(
              email.passwordConfigured
                ? "statusPage.passwordKept"
                : "statusPage.passwordNeeded",
            )}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            {t("statusPage.passwordHelp")}
          </p>
        </div>
      </div>
      <div className="flex justify-end">
        <Button size="sm" type="submit" variant="outline" disabled={busy}>
          {t("statusPage.saveEmail")}
        </Button>
      </div>
    </form>
  );
}

function AnnouncementForm({
  notice,
  busy,
  save,
  reset,
}: {
  notice: Announcement | null;
  busy: boolean;
  save: (data: AnnouncementUpdate, id?: number) => void;
  reset: () => void;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState(notice?.title ?? "");
  const [body, setBody] = useState(notice?.body ?? "");
  const [level, setLevel] = useState<AnnouncementUpdate["level"]>(
    notice?.level ?? "info",
  );
  const [starts, setStarts] = useState(
    inputTime(notice?.startsAt ?? new Date().toISOString()),
  );
  const [ends, setEnds] = useState(
    notice?.endsAt ? inputTime(notice.endsAt) : "",
  );
  const [invalid, setInvalid] = useState(false);
  const submit = (status: AnnouncementUpdate["status"]) => {
    if (
      !title.trim() ||
      !body.trim() ||
      !starts ||
      !Number.isFinite(new Date(`${starts}:00+08:00`).getTime()) ||
      (ends &&
        (!Number.isFinite(new Date(`${ends}:00+08:00`).getTime()) ||
          ends <= starts))
    ) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    save(
      {
        title: title.trim(),
        body: body.trim(),
        level,
        status,
        startsAt: isoTime(starts),
        endsAt: ends ? isoTime(ends) : null,
      },
      notice?.id,
    );
  };
  return (
    <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          {t(notice ? "statusPage.editNotice" : "statusPage.newNotice")}
        </h3>
        {notice ? (
          <Button size="sm" variant="ghost" onClick={reset}>
            {t("statusPage.newNotice")}
          </Button>
        ) : null}
      </div>
      <div className="space-y-2">
        <Label htmlFor="status-notice-title">
          {t("statusPage.noticeTitle")}
        </Label>
        <Input
          id="status-notice-title"
          value={title}
          maxLength={100}
          disabled={busy}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="status-notice-body">{t("statusPage.noticeBody")}</Label>
        <textarea
          className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          id="status-notice-body"
          value={body}
          maxLength={4000}
          rows={4}
          disabled={busy}
          onChange={(e) => setBody(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="status-notice-level">
          {t("statusPage.noticeLevel")}
        </Label>
        <Select
          value={level}
          disabled={busy}
          onValueChange={(value: AnnouncementUpdate["level"]) =>
            setLevel(value)
          }
        >
          <SelectTrigger id="status-notice-level">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(["info", "maintenance", "warning"] as const).map((value) => (
              <SelectItem key={value} value={value}>
                {t(`statusPage.level.${value}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="status-notice-start">{t("statusPage.starts")}</Label>
          <Input
            id="status-notice-start"
            type="datetime-local"
            value={starts}
            disabled={busy}
            onChange={(e) => setStarts(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="status-notice-end">{t("statusPage.ends")}</Label>
          <Input
            id="status-notice-end"
            type="datetime-local"
            value={ends}
            disabled={busy}
            onChange={(e) => setEnds(e.target.value)}
          />
        </div>
      </div>
      {invalid ? (
        <AlertMessage variant="error">
          {t("statusPage.invalidNotice")}
        </AlertMessage>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => submit("draft")}
        >
          {t("statusPage.saveDraft")}
        </Button>
        <Button size="sm" disabled={busy} onClick={() => submit("published")}>
          {t("statusPage.publish")}
        </Button>
        {notice?.status === "published" ? (
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => submit("withdrawn")}
          >
            {t("statusPage.withdraw")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function StatusPageSettings() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: getStatusPageSettings,
  });
  const [editing, setEditing] = useState<Announcement | null>(null);
  const [revision, setRevision] = useState(0);
  const refresh = () => client.invalidateQueries({ queryKey: QUERY_KEY });
  const emailMutation = useMutation({
    mutationFn: updateStatusEmail,
    onSuccess: () => {
      toast.success(t("statusPage.saved"));
      void refresh();
    },
  });
  const noticeMutation = useMutation({
    mutationFn: ({ data, id }: { data: AnnouncementUpdate; id?: number }) =>
      saveAnnouncement(data, id),
    onSuccess: () => {
      toast.success(t("statusPage.saved"));
      setEditing(null);
      setRevision((r) => r + 1);
      void refresh();
    },
  });
  const error =
    getErrorMessageOrNull(query.error) ||
    getErrorMessageOrNull(emailMutation.error) ||
    getErrorMessageOrNull(noticeMutation.error);
  const data = query.data;
  const busy = emailMutation.isPending || noticeMutation.isPending;
  return (
    <section
      id="status-page-settings"
      className="space-y-5 rounded-xl border bg-card p-4 sm:p-6"
    >
      <div>
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <Bell className="h-4 w-4" />
          {t("statusPage.title")}
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("statusPage.description")}
        </p>
      </div>
      {error ? (
        <AlertMessage variant="error">
          {error}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void query.refetch()}
          >
            {t("statusPage.retry")}
          </Button>
        </AlertMessage>
      ) : null}
      {query.isPending ? (
        <p className="text-sm text-muted-foreground">
          {t("statusPage.loading")}
        </p>
      ) : null}
      {data && !data.available ? (
        <p className="text-sm text-muted-foreground">
          {t("statusPage.disconnected")}
        </p>
      ) : null}
      {data?.available && data.email ? (
        <>
          <EmailForm
            key={JSON.stringify(data.email)}
            email={data.email}
            busy={busy}
            save={(value) => emailMutation.mutate(value)}
          />
          <div className="space-y-4 border-t pt-5">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Megaphone className="h-4 w-4" />
              {t("statusPage.announcements")}
            </h2>
            {data.notices.map((notice) => (
              <div
                key={notice.id}
                className="flex items-center justify-between gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{notice.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {t(`statusPage.state.${notice.status}`)} ·{" "}
                    {displayTime(notice.startsAt)} UTC+8
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  aria-label={`${t("statusPage.edit")} ${notice.title}`}
                  onClick={() => setEditing(notice)}
                >
                  {t("statusPage.edit")}
                </Button>
              </div>
            ))}
            {!data.notices.length ? (
              <p className="text-xs text-muted-foreground">
                {t("statusPage.noNotices")}
              </p>
            ) : null}
            <AnnouncementForm
              key={`${editing?.id ?? "new"}:${revision}`}
              notice={editing}
              busy={busy}
              save={(value, id) => noticeMutation.mutate({ data: value, id })}
              reset={() => {
                setEditing(null);
                setRevision((r) => r + 1);
              }}
            />
          </div>
          <div className="space-y-3 border-t pt-5">
            <h3 className="text-sm font-semibold">
              {t("statusPage.deliveries")}
            </h3>
            {data.events.slice(0, 10).map((event) => (
              <div key={event.id} className="text-xs">
                <p>{event.title}</p>
                <p className="mt-1 text-muted-foreground">
                  {displayTime(event.createdAt)} ·{" "}
                  {t(`statusPage.delivery.${event.emailStatus}`)}
                  {event.lastError ? ` · ${event.lastError}` : ""}
                </p>
              </div>
            ))}
            {!data.events.length ? (
              <p className="text-xs text-muted-foreground">
                {t("statusPage.noEvents")}
              </p>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
