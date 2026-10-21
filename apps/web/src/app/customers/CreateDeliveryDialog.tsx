import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { useMemo } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { z } from "zod";

import { LanguageListInput } from "@/components/common/LanguageListInput";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorMessage } from "@/lib/api/errors";
import { useCreateDelivery } from "@/lib/api/hooks/customers";
import type { CustomerRead, DeliveryCreate, DeliveryKind } from "@/lib/api/types";

// Limits of `Name` and `Code` in apps/api/seedoc/schemas (common.py, deliveries.py).
const NAME_MAX_LENGTH = 200;
const ORDER_NO_MAX_LENGTH = 100;
const KINDS: readonly DeliveryKind[] = ["machine", "system"];

function createDeliverySchema(t: TFunction) {
  return z.object({
    kind: z.enum(["machine", "system"]),
    name: z
      .string()
      .trim()
      .min(1, { error: t("deliveries.create.nameRequired") })
      .max(NAME_MAX_LENGTH, { error: t("deliveries.create.nameTooLong") }),
    orderNo: z
      .string()
      .trim()
      .max(ORDER_NO_MAX_LENGTH, { error: t("deliveries.create.orderNoTooLong") }),
    // "products": the API starts with [] and adds each machine's product languages (API.md §3.5).
    languageMode: z.enum(["products", "fixed"]),
    languages: z.array(z.string()),
  });
}

type DeliveryValues = z.infer<ReturnType<typeof createDeliverySchema>>;

interface CreateDeliveryDialogProps {
  tenantId: string;
  customer: CustomerRead;
  open: boolean;
  onClose: () => void;
}

export function CreateDeliveryDialog({ open, onClose, ...props }: CreateDeliveryDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) {
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-xl" closeLabel={t("common.actions.close")}>
        {/* A fresh form every time the dialog opens. */}
        {open && <CreateDeliveryForm {...props} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function CreateDeliveryForm({ tenantId, customer, onClose }: Omit<CreateDeliveryDialogProps, "open">) {
  const { t } = useTranslation();
  const createDelivery = useCreateDelivery(tenantId);
  const schema = useMemo(() => createDeliverySchema(t), [t]);
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<DeliveryValues>({
    resolver: zodResolver(schema),
    defaultValues: { kind: "machine", name: "", orderNo: "", languageMode: "products", languages: ["de"] },
  });
  const languageMode = useWatch({ control, name: "languageMode" });

  function handleSave(values: DeliveryValues) {
    const body: DeliveryCreate = {
      customer_id: customer.id,
      kind: values.kind,
      name: values.name,
      order_no: values.orderNo || null,
    };
    if (values.languageMode === "fixed") {
      body.required_languages = values.languages;
    }
    createDelivery.mutate(body, {
      onSuccess: (delivery) => {
        toast.success(t("deliveries.create.created", { name: delivery.name }));
        onClose();
      },
    });
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("deliveries.create.title", { customer: customer.name })}</DialogTitle>
        <DialogDescription>{t("deliveries.create.description")}</DialogDescription>
      </DialogHeader>

      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleSave)(event)}>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">{t("deliveries.create.kind")}</legend>
          {KINDS.map((kind) => (
            <label key={kind} className="flex cursor-pointer gap-3 rounded-md border p-3 has-[:checked]:border-primary">
              <input type="radio" value={kind} className="accent-primary mt-0.5" {...register("kind")} />
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-medium">{t(`deliveries.kind.${kind}`)}</span>
                <span className="text-muted-foreground text-xs">{t(`deliveries.kindHint.${kind}`)}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="delivery-name">{t("deliveries.create.name")}</Label>
            <Input
              id="delivery-name"
              autoComplete="off"
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? "delivery-name-error" : undefined}
              {...register("name")}
            />
            {errors.name && (
              <p id="delivery-name-error" className="text-destructive text-sm">
                {errors.name.message}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="delivery-order-no">{t("deliveries.create.orderNo")}</Label>
            <Input
              id="delivery-order-no"
              autoComplete="off"
              aria-invalid={errors.orderNo ? true : undefined}
              aria-describedby={errors.orderNo ? "delivery-order-no-error" : undefined}
              {...register("orderNo")}
            />
            {errors.orderNo && (
              <p id="delivery-order-no-error" className="text-destructive text-sm">
                {errors.orderNo.message}
              </p>
            )}
          </div>
        </div>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">{t("deliveries.create.languages")}</legend>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" value="products" className="accent-primary" {...register("languageMode")} />
            {t("deliveries.create.languagesFromProducts")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" value="fixed" className="accent-primary" {...register("languageMode")} />
            {t("deliveries.create.languagesFixed")}
          </label>
          {languageMode === "fixed" && (
            <Controller
              control={control}
              name="languages"
              render={({ field }) => (
                <LanguageListInput
                  label={t("deliveries.create.languages")}
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />
          )}
          <p className="text-muted-foreground text-xs">{t("deliveries.create.languagesHint")}</p>
        </fieldset>

        {createDelivery.isError && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(createDelivery.error)}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" disabled={createDelivery.isPending} onClick={onClose}>
            {t("common.actions.cancel")}
          </Button>
          <Button type="submit" disabled={createDelivery.isPending}>
            {t("deliveries.create.submit")}
          </Button>
        </DialogFooter>
      </form>
    </>
  );
}
