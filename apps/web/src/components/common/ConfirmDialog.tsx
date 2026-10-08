import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { buttonVariants } from "@/components/ui/button";

// "Are you sure?" dialog. The dialog stays open after confirming; the caller closes it (onOpenChange(false))
// when the action succeeded, so a failed action keeps the dialog open and nothing is clicked twice.
interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  variant?: "default" | "destructive";
  isPending?: boolean;
  onConfirm: () => void;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  variant = "default",
  isPending = false,
  onConfirm,
}: ConfirmDialogProps) {
  const { t } = useTranslation();

  function handleConfirm(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    onConfirm();
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description && <AlertDialogDescription>{description}</AlertDialogDescription>}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>{t("common.actions.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            className={buttonVariants({ variant })}
            disabled={isPending}
            aria-busy={isPending}
            onClick={handleConfirm}
          >
            {confirmLabel ?? t("common.actions.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
