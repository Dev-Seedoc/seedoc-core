import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { Controller, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { LanguageListInput } from "@/components/common/LanguageListInput";
import { NativeSelect } from "@/components/common/NativeSelect";
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
import { useSpaces } from "@/lib/api/hooks/documents";
import { useCreateProduct } from "@/lib/api/hooks/products";
import type { ProductRead } from "@/lib/api/types";

import { createProductSchema, DEFAULT_LANGUAGES, type ProductValues } from "./productForm";

interface CreateProductDialogProps {
  tenantId: string;
  open: boolean;
  onClose: () => void;
  onCreated: (product: ProductRead) => void;
}

export function CreateProductDialog({ tenantId, open, onClose, onCreated }: CreateProductDialogProps) {
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
      <DialogContent closeLabel={t("common.actions.close")}>
        {/* A fresh form every time the dialog opens. */}
        {open && <CreateProductForm tenantId={tenantId} onClose={onClose} onCreated={onCreated} />}
      </DialogContent>
    </Dialog>
  );
}

function CreateProductForm({ tenantId, onClose, onCreated }: Omit<CreateProductDialogProps, "open">) {
  const { t } = useTranslation();
  const createProduct = useCreateProduct(tenantId);
  const spaces = useSpaces(tenantId);
  const schema = useMemo(() => createProductSchema(t), [t]);
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<ProductValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", spaceId: "", languages: DEFAULT_LANGUAGES },
  });

  function handleSave(values: ProductValues) {
    createProduct.mutate(
      { name: values.name, space_id: values.spaceId || null, required_languages: values.languages },
      {
        onSuccess: (product) => {
          toast.success(t("products.create.created", { name: product.name }));
          onCreated(product);
        },
      },
    );
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("products.create.title")}</DialogTitle>
        <DialogDescription>{t("products.create.description")}</DialogDescription>
      </DialogHeader>

      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleSave)(event)}>
        <div className="flex flex-col gap-2">
          <Label htmlFor="product-name">{t("products.form.name")}</Label>
          <Input
            id="product-name"
            autoComplete="off"
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? "product-name-error" : undefined}
            {...register("name")}
          />
          {errors.name && (
            <p id="product-name-error" className="text-destructive text-sm">
              {errors.name.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="product-space">{t("products.form.space")}</Label>
          {/* Controlled, so the saved space shows once the space list has arrived (an uncontrolled select would keep
              "no space" when its options come later). */}
          <Controller
            control={control}
            name="spaceId"
            render={({ field }) => (
              <NativeSelect id="product-space" {...field}>
                <option value="">{t("products.form.noSpace")}</option>
                {spaces.data?.map((space) => (
                  <option key={space.id} value={space.id}>
                    {space.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          />
          <p className="text-muted-foreground text-xs">{t("products.form.spaceHint")}</p>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-sm leading-none font-medium">{t("products.form.languages")}</span>
          <Controller
            control={control}
            name="languages"
            render={({ field }) => (
              <LanguageListInput
                label={t("products.form.languages")}
                value={field.value}
                onChange={field.onChange}
                invalid={errors.languages !== undefined}
              />
            )}
          />
          <p className="text-muted-foreground text-xs">{t("products.form.languagesHint")}</p>
        </div>

        {createProduct.isError && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(createProduct.error)}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" disabled={createProduct.isPending} onClick={onClose}>
            {t("common.actions.cancel")}
          </Button>
          <Button type="submit" disabled={createProduct.isPending}>
            {t("products.create.submit")}
          </Button>
        </DialogFooter>
      </form>
    </>
  );
}
