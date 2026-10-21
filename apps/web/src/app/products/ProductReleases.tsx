import { ChevronDown, ChevronRight, History } from "lucide-react";
import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useProductRelease, useProductReleases } from "@/lib/api/hooks/products";
import type { ProductRead } from "@/lib/api/types";
import { formatDateTime } from "@/lib/formatDate";
import { getLanguageLabel } from "@/lib/languages";

const COLUMN_COUNT = 5;

// The product's releases, newest first (API.md §3.4). Read only here: creating one (`create_product_release`) comes
// with Raven's release task. A row opens the versions it froze.
export function ProductReleases({ tenantId, product }: { tenantId: string; product: ProductRead }) {
  const { t } = useTranslation();
  const releases = useProductReleases(tenantId, product.id);
  const [openNo, setOpenNo] = useState<number | null>(null);

  let content;
  if (releases.isPending) {
    content = <Spinner />;
  } else if (releases.isError) {
    content = <LoadFailed title={t("products.releases.loadFailed")} onRetry={() => void releases.refetch()} />;
  } else if (releases.data.length === 0) {
    content = (
      <EmptyState
        icon={History}
        title={t("products.releases.emptyTitle")}
        description={t("products.releases.emptyDescription")}
      />
    );
  } else {
    content = (
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("products.releases.release")}</TableHead>
              <TableHead>{t("products.releases.changeNote")}</TableHead>
              <TableHead className="text-right">{t("products.releases.itemCount")}</TableHead>
              <TableHead>{t("products.releases.createdAt")}</TableHead>
              <TableHead>{t("products.releases.createdBy")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {releases.data.map((release) => {
              const isOpen = openNo === release.release_no;
              const Chevron = isOpen ? ChevronDown : ChevronRight;
              return (
                <Fragment key={release.id}>
                  <TableRow>
                    <TableCell className="whitespace-nowrap">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="-ml-2"
                        aria-expanded={isOpen}
                        onClick={() => {
                          setOpenNo(isOpen ? null : release.release_no);
                        }}
                      >
                        <Chevron aria-hidden="true" />
                        {t("products.list.releaseNo", { no: release.release_no })}
                      </Button>
                    </TableCell>
                    <TableCell className="max-w-72">{release.change_note ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{release.item_count}</TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {formatDateTime(release.created_at)}
                    </TableCell>
                    <TableCell>{release.created_by_name ?? "—"}</TableCell>
                  </TableRow>
                  {isOpen && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={COLUMN_COUNT} className="bg-muted/30">
                        <ReleaseItems tenantId={tenantId} productId={product.id} releaseNo={release.release_no} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </div>
    );
  }

  return (
    <section aria-labelledby="product-releases" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="product-releases" className="text-lg font-semibold">
          {t("products.releases.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("products.releases.description")}</p>
      </div>
      {content}
    </section>
  );
}

// The frozen versions of one release, as they were at release time (title, language, folder path).
function ReleaseItems({ tenantId, productId, releaseNo }: { tenantId: string; productId: string; releaseNo: number }) {
  const { t } = useTranslation();
  const release = useProductRelease(tenantId, productId, releaseNo);

  if (release.isPending) {
    return <Spinner />;
  }
  if (release.isError) {
    return <LoadFailed title={t("products.releases.itemsLoadFailed")} onRetry={() => void release.refetch()} />;
  }
  return (
    <ul className="flex flex-col gap-1 py-1" aria-label={t("products.releases.items", { no: releaseNo })}>
      {release.data.items.map((item) => (
        <li key={item.id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <span className="font-medium">{item.title}</span>
          <span className="text-muted-foreground">
            {getLanguageLabel(item.language, t)} · {t("documents.table.versionNo", { no: item.version_no })} ·{" "}
            {item.folder_path}
          </span>
        </li>
      ))}
    </ul>
  );
}
