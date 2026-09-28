import { useTranslation } from "react-i18next";

import { Switch } from "@/components/ui/switch";

export type ApiKeyAuthToggleProps = {
  enabled: boolean;
  disabled?: boolean;
  requiredByDeployment?: boolean;
  onChange: (enabled: boolean) => void;
};

export function ApiKeyAuthToggle({ enabled, disabled = false, requiredByDeployment = false, onChange }: ApiKeyAuthToggleProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-between rounded-lg border p-3">
      <div className="space-y-1">
        <p className="text-sm font-medium">{t("apiKeys.authToggle.title")}</p>
        <p className="text-xs text-muted-foreground">{t("apiKeys.authToggle.description")}</p>
        {requiredByDeployment ? <p className="text-xs text-muted-foreground">{t("settings.deploymentAuth.apiKeyRequired")}</p> : null}
      </div>
      <Switch checked={enabled} disabled={disabled || (requiredByDeployment && enabled)} onCheckedChange={onChange} />
    </div>
  );
}
