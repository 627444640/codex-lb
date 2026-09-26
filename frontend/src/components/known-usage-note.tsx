import { useTranslation } from "react-i18next";

export function KnownUsageNote() {
  const { t } = useTranslation();
  return <p className="text-xs text-muted-foreground">{t("usage.knownTotalNotice")}</p>;
}
