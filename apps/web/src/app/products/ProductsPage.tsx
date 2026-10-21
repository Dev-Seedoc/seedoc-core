import { Package, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCurrentTenant } from "@/hooks/useCurrentTenant";
import { useSpaces } from "@/lib/api/hooks/documents";
import { useProducts } from "@/lib/api/hooks/products";
import type { ProductRead } from "@/lib/api/types";
import { getLanguageLabel } from "@/lib/languages";

import { CreateProductDialog } from "./CreateProductDialog";

// `/products` (NAMING §7): every product of the tenant, by name (API order).
export function ProductsPage() {
  const { currentTenant } = useCurrentTenant();
  // AppLayout renders pages only for users with a tenant.
  return currentTenant ? <ProductList tenantId={currentTenant.tenant_id} /> : null;
}

function ProductList({ tenantId }: { tenantId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const products = useProducts(tenantId);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const createButton = (
    <Button
      onClick={() => {
        setIsCreateOpen(true);
      }}
    >
      <Plus aria-hidden="true" />
      {t("products.create.open")}
    </Button>
  );

  let content;
  if (products.isPending) {
    content = <Spinner />;
  } else if (products.isError) {
    content = <LoadFailed title={t("products.list.loadFailed")} onRetry={() => void products.refetch()} />;
  } else if (products.data.length === 0) {
    content = (
      <EmptyState
        icon={Package}
        title={t("products.list.emptyTitle")}
        description={t("products.list.emptyDescription")}
        action={createButton}
      />
    );
  } else {
    content = <ProductTable tenantId={tenantId} products={products.data} />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t("products.list.title")}</h1>
        {products.data && products.data.length > 0 && createButton}
      </div>
      {content}
      <CreateProductDialog
        tenantId={tenantId}
        open={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
        }}
        onCreated={(product) => {
          setIsCreateOpen(false);
          void navigate(`/products/${product.id}`);
        }}
      />
    </div>
  );
}

function ProductTable({ tenantId, products }: { tenantId: string; products: ProductRead[] }) {
  const { t } = useTranslation();
  // Space names for the "Bereich" column; until they are loaded the column stays empty.
  const spaces = useSpaces(tenantId);
  const spaceNames = new Map(spaces.data?.map((space) => [space.id, space.name]));

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("products.list.name")}</TableHead>
            <TableHead>{t("products.list.space")}</TableHead>
            <TableHead>{t("products.list.languages")}</TableHead>
            <TableHead className="text-right">{t("products.list.documents")}</TableHead>
            <TableHead>{t("products.list.latestRelease")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {products.map((product) => (
            <TableRow key={product.id}>
              <TableCell className="font-medium">
                <Link to={`/products/${product.id}`} className="hover:underline">
                  {product.name}
                </Link>
              </TableCell>
              <TableCell>{product.space_id ? (spaceNames.get(product.space_id) ?? "") : "—"}</TableCell>
              <TableCell>
                {product.required_languages.map((language) => getLanguageLabel(language, t)).join(", ")}
              </TableCell>
              <TableCell className="text-right tabular-nums">{product.document_count}</TableCell>
              <TableCell>
                {product.latest_release_no === null
                  ? t("products.list.noRelease")
                  : t("products.list.releaseNo", { no: product.latest_release_no })}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
