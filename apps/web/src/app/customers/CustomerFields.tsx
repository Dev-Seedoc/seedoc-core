import type { FieldErrors, UseFormRegister } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { CustomerValues } from "./customerForm";

interface CustomerFieldsProps {
  register: UseFormRegister<CustomerValues>;
  errors: FieldErrors<CustomerValues>;
}

const FIELDS = [
  { name: "name", id: "customer-name", labelKey: "customers.form.name", autoComplete: "organization" },
  { name: "contactName", id: "customer-contact-name", labelKey: "customers.form.contactName", autoComplete: "name" },
  {
    name: "contactEmail",
    id: "customer-contact-email",
    labelKey: "customers.form.contactEmail",
    autoComplete: "email",
  },
] as const;

// Name and contact of a customer: shared by "Kunde anlegen" and the customer's details form.
export function CustomerFields({ register, errors }: CustomerFieldsProps) {
  const { t } = useTranslation();
  return (
    <>
      {FIELDS.map((field) => {
        const error = errors[field.name];
        const errorId = `${field.id}-error`;
        return (
          <div key={field.name} className="flex flex-col gap-2">
            <Label htmlFor={field.id}>{t(field.labelKey)}</Label>
            <Input
              id={field.id}
              type={field.name === "contactEmail" ? "email" : "text"}
              autoComplete={field.autoComplete}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
              {...register(field.name)}
            />
            {error && (
              <p id={errorId} className="text-destructive text-sm">
                {error.message}
              </p>
            )}
          </div>
        );
      })}
    </>
  );
}
