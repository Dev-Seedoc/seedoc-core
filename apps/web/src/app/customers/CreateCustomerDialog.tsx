import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getErrorMessage } from "@/lib/api/errors";
import { useCreateCustomer } from "@/lib/api/hooks/customers";
import type { CustomerRead } from "@/lib/api/types";

import { CustomerFields } from "./CustomerFields";
import { createCustomerSchema, type CustomerValues, emptyToNull, isFieldRejected } from "./customerForm";

interface CreateCustomerDialogProps {
  tenantId: string;
  open: boolean;
  onClose: () => void;
  onCreated: (customer: CustomerRead) => void;
}

export function CreateCustomerDialog({ tenantId, open, onClose, onCreated }: CreateCustomerDialogProps) {
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
        {open && <CreateCustomerForm tenantId={tenantId} onClose={onClose} onCreated={onCreated} />}
      </DialogContent>
    </Dialog>
  );
}

function CreateCustomerForm({ tenantId, onClose, onCreated }: Omit<CreateCustomerDialogProps, "open">) {
  const { t } = useTranslation();
  const createCustomer = useCreateCustomer(tenantId);
  const schema = useMemo(() => createCustomerSchema(t), [t]);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<CustomerValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", contactName: "", contactEmail: "" },
  });

  function handleSave(values: CustomerValues) {
    createCustomer.mutate(
      {
        name: values.name,
        contact_name: emptyToNull(values.contactName),
        contact_email: emptyToNull(values.contactEmail),
      },
      {
        onSuccess: (customer) => {
          toast.success(t("customers.create.created", { name: customer.name }));
          onCreated(customer);
        },
        onError: (error) => {
          // The API checks the address too; its answer goes under the field like our own check.
          if (isFieldRejected(error, "contact_email")) {
            setError("contactEmail", { message: t("customers.form.emailInvalid") }, { shouldFocus: true });
          }
        },
      },
    );
  }

  const showAlert = createCustomer.isError && !isFieldRejected(createCustomer.error, "contact_email");
  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("customers.create.title")}</DialogTitle>
        <DialogDescription>{t("customers.create.description")}</DialogDescription>
      </DialogHeader>

      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleSave)(event)}>
        <CustomerFields register={register} errors={errors} />

        {showAlert && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(createCustomer.error)}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" disabled={createCustomer.isPending} onClick={onClose}>
            {t("common.actions.cancel")}
          </Button>
          <Button type="submit" disabled={createCustomer.isPending}>
            {t("customers.create.submit")}
          </Button>
        </DialogFooter>
      </form>
    </>
  );
}
