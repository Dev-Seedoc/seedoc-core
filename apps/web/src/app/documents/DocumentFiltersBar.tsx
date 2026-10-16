import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { NativeSelect } from "@/components/common/NativeSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ACCESS_LEVELS, DOC_TYPES, PROCESSING_STATUSES } from "@/lib/documentEnums";
import { SUPPORTED_LANGUAGES } from "@/lib/languages";

import { type DocumentFilters, hasDocumentFilters } from "./documentFilters";

// Typing pauses this long before the title search is sent, so not every key stroke is a request.
const SEARCH_DELAY_MS = 300;

interface DocumentFiltersBarProps {
  filters: DocumentFilters;
  // A change to merge into the current filters; `null` clears them all.
  onChange: (change: Partial<DocumentFilters> | null) => void;
}

export function DocumentFiltersBar({ filters, onChange }: DocumentFiltersBarProps) {
  const { t } = useTranslation();
  const [search, setSearch] = useState(filters.q ?? "");
  // The URL can change the search from outside (back button, "Filter zurücksetzen"): follow it. Not when the URL
  // only caught up with the typing: "Pumpe " (with the space just typed) must stay, although the URL holds "Pumpe".
  const [shownQ, setShownQ] = useState(filters.q);
  if (shownQ !== filters.q) {
    setShownQ(filters.q);
    if ((search.trim() || undefined) !== filters.q) {
      setSearch(filters.q ?? "");
    }
  }

  // Sends the typed search to the URL after a pause; the URL is the external system this effect syncs with.
  useEffect(() => {
    const q = search.trim() || undefined;
    if (q === filters.q) {
      return;
    }
    const timer = setTimeout(() => {
      onChange({ q });
    }, SEARCH_DELAY_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [search, filters, onChange]);

  function setFilter(key: keyof DocumentFilters, value: string) {
    onChange({ [key]: value || undefined });
  }

  return (
    <div className="flex flex-wrap items-end gap-2" role="search" aria-label={t("documents.filters.label")}>
      <div className="relative w-full sm:w-64">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          aria-hidden="true"
        />
        <Input
          type="search"
          className="pl-8"
          placeholder={t("documents.filters.search")}
          aria-label={t("documents.filters.search")}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
          }}
        />
      </div>

      <NativeSelect
        className="w-auto"
        aria-label={t("documents.filters.docType")}
        value={filters.doc_type ?? ""}
        onChange={(event) => {
          setFilter("doc_type", event.target.value);
        }}
      >
        <option value="">{t("documents.filters.allDocTypes")}</option>
        {DOC_TYPES.map((docType) => (
          <option key={docType} value={docType}>
            {t(`common.docType.${docType}`)}
          </option>
        ))}
      </NativeSelect>

      <NativeSelect
        className="w-auto"
        aria-label={t("documents.filters.language")}
        value={filters.language ?? ""}
        onChange={(event) => {
          setFilter("language", event.target.value);
        }}
      >
        <option value="">{t("documents.filters.allLanguages")}</option>
        {SUPPORTED_LANGUAGES.map((language) => (
          <option key={language} value={language}>
            {t(`common.language.${language}`)}
          </option>
        ))}
      </NativeSelect>

      <NativeSelect
        className="w-auto"
        aria-label={t("documents.filters.accessLevel")}
        value={filters.access_level ?? ""}
        onChange={(event) => {
          setFilter("access_level", event.target.value);
        }}
      >
        <option value="">{t("documents.filters.allAccessLevels")}</option>
        {ACCESS_LEVELS.map((level) => (
          <option key={level} value={level}>
            {t(`common.accessLevel.${level}`)}
          </option>
        ))}
      </NativeSelect>

      <NativeSelect
        className="w-auto"
        aria-label={t("documents.filters.status")}
        value={filters.processing_status ?? ""}
        onChange={(event) => {
          setFilter("processing_status", event.target.value);
        }}
      >
        <option value="">{t("documents.filters.allStatuses")}</option>
        {PROCESSING_STATUSES.map((status) => (
          <option key={status} value={status}>
            {t(`common.status.${status}`)}
          </option>
        ))}
      </NativeSelect>

      {hasDocumentFilters(filters) && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            onChange(null);
          }}
        >
          <X aria-hidden="true" />
          {t("documents.filters.reset")}
        </Button>
      )}
    </div>
  );
}
