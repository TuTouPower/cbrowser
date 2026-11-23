import { useI18n } from "../../i18n";
import { CONFIG_PENDING_DESCRIPTOR } from "../presentation";
import { Banner } from "./Banner";
import { Button } from "./Button";
import { StatusBadge } from "./StatusBadge";
import { cn } from "./cn";

export function ConfigPendingNotice({
  pending,
  onApply,
  isPending = false,
  variant = "banner",
  testId,
  applyTestId,
}: {
  pending: boolean;
  onApply: () => void;
  isPending?: boolean;
  variant?: "banner" | "inline";
  testId?: string;
  applyTestId?: string;
}) {
  const { t } = useI18n();
  if (!pending) return null;
  const label = t(CONFIG_PENDING_DESCRIPTOR.label);
  const action = (
    <Button
      size="sm"
      data-testid={applyTestId}
      disabled={isPending}
      onClick={onApply}
    >
      {t("detailApplyAndRestart")}
    </Button>
  );
  if (variant === "banner") {
    return (
      <Banner tone="warning" testId={testId}>
        <span>{label}</span>
        {action}
      </Banner>
    );
  }
  return (
    <span
      data-testid={testId}
      className={cn("inline-flex items-center gap-xs")}
    >
      <StatusBadge tone={CONFIG_PENDING_DESCRIPTOR.tone} label={label} />
      {action}
    </span>
  );
}
