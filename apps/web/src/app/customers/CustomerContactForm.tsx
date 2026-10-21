import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { getErrorMessage } from "@/lib/api/errors";
import { useUpdateCustomer } from "@/lib/api/hooks/customers";
import type { CustomerRead, CustomerUpdate } from "@/lib/api/types";

import { CustomerFields } from "./CustomerFields";
import { createCustomerSchema, type CustomerValues, emptyToNull, isFieldRejected } from "./customerForm";

function toValues(customer: CustomerRead): CustomerValues {
  return { name: customer.name, contactName: customer.contact_name ?? "", contactEmail: customer.contact_email ?? "" };
}

// Only what really changed (API.md §3.5: a field left out stays; `null` clears a contact field).
function changedFields(customer: CustomerRead, values: CustomerValues): CustomerUpdate {
  const body: CustomerUpdate = {};
  if (values.name !== customer.name) {
    body.name = values.name;
  }
  const contactName = emptyToNull(values.contactName);
  if (contactName !== customer.contact_name) {
    body.contact_name = contactName;
  }
  // The API stores addresses lower-case, so "Erika@Muster.de" over "erika@muster.de" is not a change.
  const contactEmail = emptyToNull(values.contactEmail);
  if (contactEmail?.toLowerCase() !== customer.contact_email?.toLowerCase()) {
    body.contact_email = contactEmail;
  }
  return body;
}

// Name and contact of a customer.
export function CustomerContactForm({ tenantId, customer }: { tenantId: string; customer: CustomerRead }) {
  const { t } = useTranslation();
  const update = useUpdateCustomer(tenantId, customer.id);
  const schema = useMemo(() => createCustomerSchema(t), [t]);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty },
  } = useForm<CustomerValues>({
    resolver: zodResolver(schema),
    // Follows the customer when it is reloaded, without overwriting what is being typed.
    values: toValues(customer),
    resetOptions: { keepDirtyValues: true },
  });

  // react-hook-form applies `resetOptions` to every reset(); ours must drop what was typed, not keep it.
  function resetTo(values: CustomerValues) {
    reset(values, { keepDirtyValues: false });
  }

  function handleSave(values: CustomerValues) {
    const body = changedFields(customer, values);
    if (Object.keys(body).length === 0) {
      resetTo(toValues(customer));
      return;
    }
    update.mutate(body, {
      onSuccess: (saved) => {
        toast.success(t("customers.form.saved"));
        resetTo(toValues(saved));
      },
      onError: (error) => {
        if (isFieldRejected(error, "contact_email")) {
          setError("contactEmail", { message: t("customers.form.emailInvalid") }, { shouldFocus: true });
        }
      },
    });
  }

  const showAlert = update.isError && !isFieldRejected(update.error, "contact_email");
  return (
    <section aria-labelledby="customer-contact" className="flex flex-col gap-4 rounded-lg border p-4">
      <h2 id="customer-contact" className="text-lg font-semibold">
        {t("customers.form.title")}
      </h2>
      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleSave)(event)}>
        <div className="grid gap-4 sm:grid-cols-3">
          <CustomerFields register={register} errors={errors} />
        </div>

        {showAlert && (
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
              resetTo(toValues(customer));
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
