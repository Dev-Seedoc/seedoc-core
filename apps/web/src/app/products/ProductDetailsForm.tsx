import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { Controller, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { LanguageListInput } from "@/components/common/LanguageListInput";
import { NativeSelect } from "@/components/common/NativeSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorMessage } from "@/lib/api/errors";
import { useSpaces } from "@/lib/api/hooks/documents";
import { useUpdateProduct } from "@/lib/api/hooks/products";
import type { ProductRead, ProductUpdate } from "@/lib/api/types";

import { createProductSchema, type ProductValues } from "./productForm";

function toValues(product: ProductRead): ProductValues {
  return { name: product.name, spaceId: product.space_id ?? "", languages: product.required_languages };
}

function sameLanguages(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((language, index) => language === b[index]);
}

// Only what really changed (API.md §3.4: a field left out stays; `space_id: null` clears the space).
function changedFields(product: ProductRead, values: ProductValues): ProductUpdate {
  const body: ProductUpdate = {};
  if (values.name !== product.name) {
    body.name = values.name;
  }
  const spaceId = values.spaceId || null;
  if (spaceId !== product.space_id) {
    body.space_id = spaceId;
  }
  if (!sameLanguages(values.languages, product.required_languages)) {
    body.required_languages = values.languages;
  }
  return body;
}

// Name, space and required languages of a product.
export function ProductDetailsForm({ tenantId, product }: { tenantId: string; product: ProductRead }) {
  const { t } = useTranslation();
  const update = useUpdateProduct(tenantId, product.id);
  const spaces = useSpaces(tenantId);
  const schema = useMemo(() => createProductSchema(t), [t]);
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<ProductValues>({
    resolver: zodResolver(schema),
    // Follows the product when it is reloaded, without overwriting what is being typed.
    values: toValues(product),
    resetOptions: { keepDirtyValues: true },
  });

  // react-hook-form applies `resetOptions` to every reset(); ours must drop what was typed, not keep it.
  function resetTo(values: ProductValues) {
    reset(values, { keepDirtyValues: false });
  }

  function handleSave(values: ProductValues) {
    const body = changedFields(product, values);
    if (Object.keys(body).length === 0) {
      resetTo(values);
      return;
    }
    update.mutate(body, {
      onSuccess: (saved) => {
        toast.success(t("products.form.saved"));
        resetTo(toValues(saved));
      },
    });
  }

  return (
    <section aria-labelledby="product-details" className="flex flex-col gap-4 rounded-lg border p-4">
      <h2 id="product-details" className="text-lg font-semibold">
        {t("products.form.title")}
      </h2>
      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleSave)(event)}>
        <div className="grid gap-4 sm:grid-cols-2">
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
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-sm leading-none font-medium">{t("products.form.languages")}</span>
          <Controller
            control={control}
            name="languages"
            render={({ field }) => (
              <LanguageListInput label={t("products.form.languages")} value={field.value} onChange={field.onChange} />
            )}
          />
          <p className="text-muted-foreground text-xs">{t("products.form.languagesHint")}</p>
        </div>

        {update.isError && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(update.error)}
          </p>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={!isDirty || update.isPending}
            onClick={() => {
              resetTo(toValues(product));
              update.reset();
            }}
          >
            {t("common.actions.discard")}
          </Button>
          <Button type="submit" disabled={!isDirty || update.isPending}>
            {t("common.actions.save")}
          </Button>
        </div>
      </form>
    </section>
  );
}
