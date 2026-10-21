import { X } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { NativeSelect } from "@/components/common/NativeSelect";
import { Button } from "@/components/ui/button";
import { getLanguageLabel, SUPPORTED_LANGUAGES } from "@/lib/languages";

interface LanguageListInputProps {
  // Label of the whole field, already translated (also names the list for screen readers).
  label: string;
  value: string[];
  onChange: (languages: string[]) => void;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
}

// `required_languages` of products and deliveries: distinct languages in the chosen order (the first one names the
// rows of the language matrix). New languages are added at the end; at least one always stays.
export function LanguageListInput({ label, value, onChange, disabled, invalid, describedBy }: LanguageListInputProps) {
  const { t } = useTranslation();
  const selectId = useId();
  const available = SUPPORTED_LANGUAGES.filter((language) => !value.includes(language));

  return (
    <div className="flex flex-col gap-2">
      <ul aria-label={label} className="flex flex-wrap gap-2">
        {value.map((language) => {
          const name = getLanguageLabel(language, t);
          return (
            <li key={language} className="bg-muted flex items-center gap-1 rounded-md py-1 pr-1 pl-2.5 text-sm">
              {name}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-6"
                disabled={disabled || value.length === 1}
                aria-label={t("common.languageList.remove", { language: name })}
                onClick={() => {
                  onChange(value.filter((other) => other !== language));
                }}
              >
                <X aria-hidden="true" />
              </Button>
            </li>
          );
        })}
      </ul>
      {available.length > 0 && (
        <div className="flex flex-col gap-1">
          <label htmlFor={selectId} className="sr-only">
            {t("common.languageList.add")}
          </label>
          <NativeSelect
            id={selectId}
            className="sm:w-64"
            value=""
            disabled={disabled}
            aria-invalid={invalid ? true : undefined}
            aria-describedby={describedBy}
            onChange={(event) => {
              if (event.target.value) {
                onChange([...value, event.target.value]);
              }
            }}
          >
            <option value="">{t("common.languageList.add")}</option>
            {available.map((language) => (
              <option key={language} value={language}>
                {getLanguageLabel(language, t)}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}
    </div>
  );
}
