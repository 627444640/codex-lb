import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Plus, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { AlertMessage } from "@/components/alert-message";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { deleteGuide, getGuides, GuideContentSchema, restoreGuide, saveGuide } from "@/features/settings/troubleshooting-api";
import type { Guide, GuideContent, GuideWrite } from "@/features/settings/troubleshooting-api";
import { getErrorMessageOrNull } from "@/utils/errors";

const QUERY_KEY = ["settings", "troubleshooting"];
const EMPTY: GuideContent = {
  code: "", title: "", signature: "", scope: "", cause: "", solutions: [], limitations: "",
  endpointUrl: "", endpointLabel: "API 基地址", endpointHelp: "", status: "draft", sortOrder: 100,
};
const TEXTAREA = "w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function GuideEditor({ guide, busy, save, close }: {
  guide: Guide | null; busy: boolean; save: (data: GuideWrite, id?: number) => void; close: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<GuideContent>(() => guide ? GuideContentSchema.parse(guide) : { ...EMPTY });
  const [steps, setSteps] = useState(guide?.solutions.join("\n\n") ?? "");
  const [invalid, setInvalid] = useState(false);
  const [preview, setPreview] = useState(false);
  const field = (key: keyof Pick<GuideContent, "code" | "title" | "signature" | "scope" | "cause" | "limitations" | "endpointUrl" | "endpointLabel" | "endpointHelp">, limit: number, rows?: number) => (
    <div className="space-y-2">
      <Label htmlFor={`guide-${key}`}>{t(`troubleshooting.${key}`)}</Label>
      {rows ? <textarea id={`guide-${key}`} className={TEXTAREA} rows={rows} maxLength={limit} value={form[key]} disabled={busy}
        onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
        : <Input id={`guide-${key}`} maxLength={limit} value={form[key]} disabled={busy}
          onChange={(event) => setForm({ ...form, [key]: event.target.value })} />}
    </div>
  );
  const submit = (status: GuideContent["status"]) => {
    const parsed = GuideContentSchema.safeParse({ ...form, status, solutions: steps.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean) });
    setInvalid(!parsed.success);
    if (parsed.success) save({ ...parsed.data, ...(guide ? { revision: guide.revision } : {}) }, guide?.id);
  };
  return <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-medium">{t(guide ? "troubleshooting.editGuide" : "troubleshooting.newGuide")}</h3>
      <Button variant="ghost" size="sm" disabled={busy} onClick={close}>{t("troubleshooting.closeEditor")}</Button>
    </div>
    <div className="grid gap-4 sm:grid-cols-2">{field("code", 48)}{field("title", 100)}{field("signature", 160)}
      <div className="space-y-2"><Label htmlFor="guide-sortOrder">{t("troubleshooting.sortOrder")}</Label>
        <Input id="guide-sortOrder" type="number" min={0} max={1000000} step={1} value={form.sortOrder} disabled={busy}
          onChange={e => setForm({ ...form, sortOrder: Number(e.target.value) })} /></div>
    </div>
    {field("scope", 1000, 2)}{field("cause", 3000, 3)}
    <div className="space-y-2"><Label htmlFor="guide-solutions">{t("troubleshooting.solutions")}</Label>
      <textarea id="guide-solutions" className={TEXTAREA} rows={6} maxLength={12024} value={steps} disabled={busy} onChange={e => setSteps(e.target.value)} />
      <p className="text-xs text-muted-foreground">{t("troubleshooting.solutionsHelp")}</p>
    </div>
    {field("limitations", 2000, 2)}
    <details className="rounded-md border p-3" open={Boolean(form.endpointUrl) || undefined}>
      <summary className="cursor-pointer text-sm">{t("troubleshooting.optionalAddress")}</summary>
      <div className="mt-3 space-y-3">{field("endpointUrl", 2048)}{field("endpointLabel", 80)}{field("endpointHelp", 1000, 2)}</div>
    </details>
    {invalid ? <AlertMessage variant="error">{t("troubleshooting.invalid")}</AlertMessage> : null}
    <div className="flex flex-wrap justify-end gap-2">
      <Button size="sm" variant="ghost" onClick={() => setPreview(!preview)}>{t("troubleshooting.preview")}</Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => submit("draft")}>{t("troubleshooting.saveDraft")}</Button>
      {guide?.status === "published" ? <Button size="sm" variant="outline" disabled={busy} onClick={() => submit("withdrawn")}>{t("troubleshooting.withdraw")}</Button> : null}
      <Button size="sm" disabled={busy} onClick={() => submit("published")}>{t("troubleshooting.publish")}</Button>
    </div>
    {preview ? <article aria-label={t("troubleshooting.preview")} className="space-y-3 break-words rounded-lg border bg-background p-4 text-sm [overflow-wrap:anywhere]">
      <h3 className="font-semibold">{form.code} · {form.title}</h3><p className="text-muted-foreground">{form.signature}</p>
      <p className="whitespace-pre-line">{form.scope}</p><h4 className="font-medium">{t("troubleshooting.cause")}</h4><p className="whitespace-pre-line">{form.cause}</p>
      <h4 className="font-medium">{t("troubleshooting.solutions")}</h4><ol className="list-decimal space-y-2 pl-5">{steps.split(/\n\s*\n/).filter(Boolean).map((step, index) => <li className="whitespace-pre-line" key={index}>{step}</li>)}</ol>
      {form.endpointUrl ? <p>{form.endpointLabel}: <code>{form.endpointUrl}</code><br />{form.endpointHelp}</p> : null}
      <p className="whitespace-pre-line text-muted-foreground">{form.limitations}</p>
    </article> : null}
  </div>;
}

export function TroubleshootingSettings() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const query = useQuery({ queryKey: QUERY_KEY, queryFn: getGuides });
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("active");
  const [editor, setEditor] = useState<Guide | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<Guide | null>(null);
  const refresh = () => client.invalidateQueries({ queryKey: QUERY_KEY });
  const saved = () => { toast.success(t("troubleshooting.saved")); setEditor(undefined); void refresh(); };
  const save = useMutation({ mutationFn: ({ data, id }: { data: GuideWrite; id?: number }) => saveGuide(data, id), onSuccess: saved });
  const remove = useMutation({ mutationFn: deleteGuide, onSuccess: () => { saved(); setDeleting(null); } });
  const restore = useMutation({ mutationFn: restoreGuide, onSuccess: saved });
  const busy = save.isPending || remove.isPending || restore.isPending;
  const error = getErrorMessageOrNull(query.error) || getErrorMessageOrNull(save.error) || getErrorMessageOrNull(remove.error) || getErrorMessageOrNull(restore.error);
  const guides = (query.data?.guides ?? []).filter(guide => {
    const state = guide.deletedAt ? "deleted" : guide.status;
    return (filter === "active" ? state !== "deleted" : state === filter)
      && [guide.code, guide.title, guide.signature, guide.scope, guide.cause, ...guide.solutions].join(" ").toLocaleLowerCase().includes(search.trim().toLocaleLowerCase());
  });
  return <section id="troubleshooting-settings" className="space-y-4 rounded-xl border bg-card p-4 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-3"><div>
      <h2 className="flex items-center gap-2 text-base font-semibold"><BookOpen className="h-4 w-4" />{t("troubleshooting.titleHeading")}</h2>
      <p className="mt-1 text-xs text-muted-foreground">{t("troubleshooting.description")}</p>
    </div>{query.data?.available ? <Button size="sm" disabled={busy} onClick={() => setEditor(null)}><Plus className="mr-1 h-4 w-4" />{t("troubleshooting.newGuide")}</Button> : null}</div>
    {error ? <AlertMessage variant="error">{error}<Button variant="ghost" size="sm" disabled={busy} onClick={() => {
      save.reset(); remove.reset(); restore.reset(); void query.refetch();
    }}>{t("troubleshooting.refresh")}</Button></AlertMessage> : null}
    {query.isPending ? <p className="text-sm text-muted-foreground">{t("troubleshooting.loading")}</p> : null}
    {query.data && !query.data.available ? <p className="text-sm text-muted-foreground">{t("troubleshooting.disconnected")}</p> : null}
    {query.data?.available ? <>
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input className="pl-9" aria-label={t("troubleshooting.search")} placeholder={t("troubleshooting.search")} value={search} onChange={e => setSearch(e.target.value)} /></div>
        <select aria-label={t("troubleshooting.filter")} className="rounded-md border bg-background px-3 py-2 text-sm" value={filter} onChange={e => setFilter(e.target.value)}>
          {["active", "published", "draft", "withdrawn", "deleted"].map(state => <option key={state} value={state}>{t(`troubleshooting.state.${state}`)}</option>)}
        </select>
      </div>
      <div className="space-y-2">{guides.map(guide => <div key={guide.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
        <div className="min-w-0 flex-1"><p className="break-words text-sm font-medium">{guide.code} · {guide.title}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t(`troubleshooting.state.${guide.deletedAt ? "deleted" : guide.status}`)} · {t("troubleshooting.orderValue", { value: guide.sortOrder })} · {new Date(guide.updatedAt).toLocaleDateString("zh-CN", { timeZone: "Asia/Taipei" })}</p></div>
        <div className="flex gap-2">{guide.deletedAt ? <Button size="sm" variant="outline" disabled={busy} aria-label={`${t("troubleshooting.restore")} ${guide.title}`} onClick={() => restore.mutate(guide)}>{t("troubleshooting.restore")}</Button> : <>
          <Button size="sm" variant="outline" disabled={busy} aria-label={`${t("troubleshooting.edit")} ${guide.title}`} onClick={() => setEditor(guide)}>{t("troubleshooting.edit")}</Button>
          <Button size="sm" variant="ghost" disabled={busy} aria-label={`${t("troubleshooting.delete")} ${guide.title}`} onClick={() => setDeleting(guide)}>{t("troubleshooting.delete")}</Button>
        </>}</div>
      </div>)}{!guides.length ? <p className="py-3 text-sm text-muted-foreground">{t("troubleshooting.empty")}</p> : null}</div>
      {editor !== undefined ? <GuideEditor key={editor ? `${editor.id}:${editor.revision}` : "new"} guide={editor} busy={busy} close={() => setEditor(undefined)} save={(data, id) => save.mutate({ data, id })} /> : null}
    </> : null}
    <AlertDialog open={deleting !== null} onOpenChange={open => { if (!open && !busy) setDeleting(null); }}>
      <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t("troubleshooting.deleteTitle")}</AlertDialogTitle>
        <AlertDialogDescription>{t("troubleshooting.deleteHelp", { title: deleting?.title ?? "" })}</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel disabled={busy}>{t("troubleshooting.cancel")}</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={busy} onClick={() => { if (deleting) remove.mutate(deleting); }}>{t("troubleshooting.confirmDelete")}</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </section>;
}
