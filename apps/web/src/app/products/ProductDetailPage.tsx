import { PackageX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { BackLink } from "@/components/common/BackLink";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { UrlTabs } from "@/components/common/UrlTabs";
import { useCurrentTenant } from "@/hooks/useCurrentTenant";
import { getErrorCode } from "@/lib/api/errors";
import { useProduct } from "@/lib/api/hooks/products";
import type { ProductRead } from "@/lib/api/types";

import { ProductDetailsForm } from "./ProductDetailsForm";
import { ProductDocuments } from "./ProductDocuments";
import { ProductLanguages } from "./ProductLanguages";
import { ProductReleases } from "./ProductReleases";

// NAMING §7: `?tab=documents|releases|languages`.
type ProductTab = "documents" | "languages" | "releases";

// `/products/:productId` (NAMING §7).
export function ProductDetailPage() {
  const { currentTenant } = useCurrentTenant();
  const { productId = "" } = useParams();
  // AppLayout renders pages only for users with a tenant.
  return currentTenant ? <ProductDetail tenantId={currentTenant.tenant_id} productId={productId} /> : null;
}

function ProductDetail({ tenantId, productId }: { tenantId: string; productId: string }) {
  const { t } = useTranslation();
  const product = useProduct(tenantId, productId);

  let content;
  if (product.isPending) {
    content = <Spinner />;
  } else if (product.isError) {
    // Unknown, another tenant's or a malformed id: for the user, all mean "this link leads nowhere".
    const code = getErrorCode(product.error);
    content =
      code === "not_found" || code === "validation_failed" ? (
        <EmptyState
          icon={PackageX}
          title={t("products.detail.notFoundTitle")}
          description={t("products.detail.notFoundDescription")}
        />
      ) : (
        <LoadFailed title={t("products.detail.loadFailed")} onRetry={() => void product.refetch()} />
      );
  } else {
    content = <ProductOverview tenantId={tenantId} product={product.data} />;
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <BackLink to="/products" label={t("products.detail.back")} />
      {content}
    </div>
  );
}

function ProductOverview({ tenantId, product }: { tenantId: string; product: ProductRead }) {
  const { t } = useTranslation();
  const tabs = [
    { value: "documents", label: t("products.tabs.documents") },
    { value: "languages", label: t("products.tabs.languages") },
    { value: "releases", label: t("products.tabs.releases") },
  ] as const satisfies readonly { value: ProductTab; label: string }[];

  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{product.name}</h1>
        <p className="text-muted-foreground text-sm">
          {t("products.detail.summary", { count: product.document_count })}
          {" · "}
          {product.latest_release_no === null
            ? t("products.detail.noRelease")
            : t("products.list.releaseNo", { no: product.latest_release_no })}
        </p>
      </header>

      <ProductDetailsForm tenantId={tenantId} product={product} />

      <UrlTabs label={t("products.tabs.label")} tabs={tabs}>
        {(tab) => {
          if (tab === "languages") {
            return <ProductLanguages tenantId={tenantId} product={product} />;
          }
          if (tab === "releases") {
            return <ProductReleases tenantId={tenantId} product={product} />;
          }
          return <ProductDocuments tenantId={tenantId} product={product} />;
        }}
      </UrlTabs>
    </>
  );
}
