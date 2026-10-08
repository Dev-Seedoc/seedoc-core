import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type de from "@/i18n/de.json";
import { cn } from "@/lib/utils";

// Every value with a label in `common.status.*` (NAMING §8).
export type Status = keyof (typeof de)["common"]["status"];

type Tone = "success" | "progress" | "danger" | "neutral";

const STATUS_TONE: Record<Status, Tone> = {
  ready: "success",
  published: "success",
  active: "success",
  pending: "progress",
  processing: "progress",
  running: "progress",
  failed: "danger",
  locked: "danger",
  draft: "neutral",
  archived: "neutral",
  disabled: "neutral",
  inactive: "neutral",
  expired: "neutral",
};

const TONE_CLASS: Record<Tone, string> = {
  success: "border-transparent bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  progress: "border-transparent bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  danger: "border-transparent bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  neutral: "border-transparent bg-muted text-muted-foreground",
};

interface StatusBadgeProps {
  status: Status;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const { t } = useTranslation();

  return (
    <Badge variant="outline" data-tone={STATUS_TONE[status]} className={cn(TONE_CLASS[STATUS_TONE[status]], className)}>
      {t(`common.status.${status}`)}
    </Badge>
  );
}
