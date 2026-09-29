import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { AlertMessage } from "@/components/alert-message";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { getErrorMessageOrNull } from "@/utils/errors";
import { getAssistantConfiguration, saveAssistantConfiguration, testAssistantConnection } from "@/features/settings/troubleshooting-assistant-api";
import type { AssistantConfiguration, AssistantConfigurationUpdate } from "@/features/settings/troubleshooting-assistant-api";

const QUERY_KEY = ["settings", "troubleshooting-assistant"];

function ConfigurationForm({ data, busy, save }: {
  data: AssistantConfiguration; busy: boolean; save: (payload: AssistantConfigurationUpdate) => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState({ enabled: data.enabled, baseUrl: data.baseUrl, model: data.model,
    requestsPerMinute: data.requestsPerMinute, dailyRequestLimit: data.dailyRequestLimit });
  const [key, setKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [modelError, setModelError] = useState(false);
  return <form className="space-y-4" onSubmit={event => {
    event.preventDefault();
    const model = form.model.trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,119}$/.test(model)) {
      setModelError(true); return;
    }
    setModelError(false);
    save({ ...form, model, clearKey, ...(key.trim() && !clearKey ? { apiKey: key.trim() } : {}) });
  }}>
    <div className="flex items-center justify-between gap-3"><Label htmlFor="assistant-enabled">{t("assistantSettings.enabled")}</Label>
      <Switch id="assistant-enabled" checked={form.enabled} disabled={busy || clearKey} onCheckedChange={enabled => setForm({ ...form, enabled })} /></div>
    <div className="space-y-2"><Label htmlFor="assistant-baseUrl">{t("assistantSettings.baseUrl")}</Label>
      <Input id="assistant-baseUrl" type="url" required value={form.baseUrl} disabled={busy} onChange={e => setForm({ ...form, baseUrl: e.target.value })} />
      <p className="text-xs text-muted-foreground">{t("assistantSettings.baseUrlHelp")}</p></div>
    <div className="space-y-2"><Label htmlFor="assistant-model">{t("assistantSettings.model")}</Label>
      <Input id="assistant-model" value={form.model} maxLength={120} required disabled={busy} placeholder="mercury-2.5"
        aria-invalid={modelError} aria-describedby={modelError ? "assistant-model-help assistant-model-error" : "assistant-model-help"}
        onChange={e => { setModelError(false); setForm({ ...form, model: e.target.value }); }}
        onPaste={event => {
          if (/[\r\n]/.test(event.clipboardData.getData("text").trim())) {
            event.preventDefault(); setModelError(true);
          }
        }} />
      <p id="assistant-model-help" className="text-xs text-muted-foreground">{t("assistantSettings.modelHelp")}</p>
      {modelError ? <p id="assistant-model-error" role="alert" className="text-xs text-destructive">{t("assistantSettings.modelSingleError")}</p> : null}</div>
    <div className="space-y-2"><Label htmlFor="assistant-apiKey">{t("assistantSettings.apiKey")}</Label>
      <Input id="assistant-apiKey" type="password" autoComplete="new-password" value={key} maxLength={2048} disabled={busy || clearKey}
        placeholder={t(data.keyConfigured ? "assistantSettings.keyKept" : "assistantSettings.keyMissing")} onChange={e => setKey(e.target.value)} />
      <p className="text-xs text-muted-foreground">{t("assistantSettings.keyHelp")}</p>
      {data.keyConfigured ? <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={clearKey} disabled={busy} onChange={e => {
        setClearKey(e.target.checked); if (e.target.checked) { setKey(""); setForm({ ...form, enabled: false }); }
      }} />{t("assistantSettings.clearKey")}</label> : null}
    </div>
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-2"><Label htmlFor="assistant-perMinute">{t("assistantSettings.perMinute")}</Label>
        <Input id="assistant-perMinute" type="number" min={1} max={60} required value={form.requestsPerMinute} disabled={busy} onChange={e => setForm({ ...form, requestsPerMinute: Number(e.target.value) })} /></div>
      <div className="space-y-2"><Label htmlFor="assistant-daily">{t("assistantSettings.daily")}</Label>
        <Input id="assistant-daily" type="number" min={1} max={10000} required value={form.dailyRequestLimit} disabled={busy} onChange={e => setForm({ ...form, dailyRequestLimit: Number(e.target.value) })} /></div>
    </div>
    <p className="text-xs text-muted-foreground">{t("assistantSettings.limitHelp")}</p>
    <div className="flex justify-end"><Button type="submit" size="sm" disabled={busy}>{t("assistantSettings.save")}</Button></div>
  </form>;
}

export function TroubleshootingAssistantSettings() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const query = useQuery({ queryKey: QUERY_KEY, queryFn: getAssistantConfiguration });
  const [revision, setRevision] = useState(0);
  const refresh = () => client.invalidateQueries({ queryKey: QUERY_KEY });
  const save = useMutation({ mutationFn: saveAssistantConfiguration, onSuccess: result => {
    client.setQueryData(QUERY_KEY, result);
    toast.success(t("assistantSettings.saved")); setRevision(value => value + 1); void refresh();
  } });
  const test = useMutation({ mutationFn: testAssistantConnection, onSuccess: result => {
    toast.success(result.message);
  }, onSettled: () => { void refresh(); } });
  const error = getErrorMessageOrNull(query.error) || getErrorMessageOrNull(save.error) || getErrorMessageOrNull(test.error);
  const busy = save.isPending || test.isPending;
  const data = query.data;
  return <section id="troubleshooting-assistant-settings" className="space-y-4 rounded-xl border bg-card p-4 sm:p-6">
    <div><h2 className="flex items-center gap-2 text-base font-semibold"><MessageSquare className="h-4 w-4" />{t("assistantSettings.title")}</h2>
      <p className="mt-1 text-xs text-muted-foreground">{t("assistantSettings.description")}</p></div>
    {error ? <AlertMessage variant="error">{error}<Button size="sm" variant="ghost" disabled={busy} onClick={() => { save.reset(); test.reset(); void query.refetch(); }}>{t("assistantSettings.refresh")}</Button></AlertMessage> : null}
    {query.isPending ? <p className="text-sm text-muted-foreground">{t("assistantSettings.loading")}</p> : null}
    {data && !data.available ? <p className="text-sm text-muted-foreground">{t("assistantSettings.disconnected")}</p> : null}
    {data?.available ? <>
      <ConfigurationForm key={revision} data={data} busy={busy} save={payload => save.mutate(payload)} />
      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <p className="text-xs text-muted-foreground">{t("assistantSettings.used", { count: data.dailyRequestsUsed, limit: data.dailyRequestLimit })}</p>
        <Button size="sm" variant="outline" disabled={busy || !data.keyConfigured || !data.model} onClick={() => test.mutate()}>{t(test.isPending ? "assistantSettings.testing" : "assistantSettings.test")}</Button>
      </div><p className="text-xs text-muted-foreground">{t("assistantSettings.testHelp")}</p>
    </> : null}
  </section>;
}
