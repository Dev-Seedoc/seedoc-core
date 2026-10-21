import { Check, Languages, Minus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useProductLanguageMatrix } from "@/lib/api/hooks/products";
import type { LanguageMatrixRow, ProductRead } from "@/lib/api/types";
import { getLanguageLabel } from "@/lib/languages";

// The product's language matrix (API.md §3.4, BUSINESS_RULES §6): one row per document group of the set, one column
// per required language. Only documents in the set count; products never have waived cells.
export function ProductLanguages({ tenantId, product }: { tenantId: string; product: ProductRead }) {
  const { t } = useTranslation();
  const matrix = useProductLanguageMatrix(tenantId, product.id);

  let content;
  if (matrix.isPending) {
    content = <Spinner />;
  } else if (matrix.isError) {
    content = <LoadFailed title={t("products.languages.loadFailed")} onRetry={() => void matrix.refetch()} />;
  } else if (matrix.data.rows.length === 0) {
    content = (
      <EmptyState
        icon={Languages}
        title={t("products.languages.emptyTitle")}
        description={t("products.languages.emptyDescription")}
      />
    );
  } else {
    const { languages, rows } = matrix.data;
    const missingCount = rows.reduce(
      (sum, row) => sum + languages.filter((language) => row.cells[language]?.status !== "present").length,
      0,
    );
    content = (
      <>
        <p className="text-sm" role="status">
          {missingCount === 0
            ? t("products.languages.complete")
            : t("products.languages.missingCount", { count: missingCount })}
        </p>
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("products.languages.document")}</TableHead>
                {languages.map((language) => (
                  <TableHead key={language} className="text-center">
                    {getLanguageLabel(language, t)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <MatrixRow key={row.group_id} row={row} languages={languages} />
              ))}
            </TableBody>
          </Table>
        </div>
      </>
    );
  }

  return (
    <section aria-labelledby="product-languages" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="product-languages" className="text-lg font-semibold">
          {t("products.languages.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("products.languages.description")}</p>
      </div>
      {content}
    </section>
  );
}

function MatrixRow({ row, languages }: { row: LanguageMatrixRow; languages: string[] }) {
  const { t } = useTranslation();
  return (
    <TableRow>
      <TableCell>
        <div className="flex flex-col">
          <span className="font-medium">{row.title}</span>
          <span className="text-muted-foreground text-xs">{t(`common.docType.${row.doc_type}`)}</span>
        </div>
      </TableCell>
      {languages.map((language) => {
        const cell = row.cells[language];
        const name = getLanguageLabel(language, t);
        return (
          <TableCell key={language} className="text-center">
            {cell?.status === "present" && cell.document_id ? (
              <Link
                to={`/documents/${cell.document_id}`}
                className="inline-flex text-emerald-700 hover:text-emerald-900 dark:text-emerald-400"
                aria-label={t("products.languages.present", { title: row.title, language: name })}
              >
                <Check className="size-4" aria-hidden="true" />
              </Link>
            ) : (
              <span
                className="text-destructive inline-flex"
                role="img"
                aria-label={t("products.languages.missing", { title: row.title, language: name })}
              >
                <Minus className="size-4" aria-hidden="true" />
              </span>
            )}
          </TableCell>
        );
      })}
    </TableRow>
  );
}
