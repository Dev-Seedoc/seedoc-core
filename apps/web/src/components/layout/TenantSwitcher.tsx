import { ChevronsUpDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCurrentTenant } from "@/hooks/useCurrentTenant";

export function TenantSwitcher() {
  const { t } = useTranslation();
  const { currentTenant, memberships, switchTenant } = useCurrentTenant();

  if (!currentTenant) {
    return null;
  }

  // One tenant: nothing to switch, just show its name.
  if (memberships.length === 1) {
    return <span className="text-sm font-medium">{currentTenant.tenant_name}</span>;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={t("shell.tenantSwitcher.label")}>
          {currentTenant.tenant_name}
          <ChevronsUpDown className="text-muted-foreground" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel>{t("shell.tenantSwitcher.label")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup value={currentTenant.tenant_id} onValueChange={switchTenant}>
          {memberships.map((membership) => (
            <DropdownMenuRadioItem key={membership.tenant_id} value={membership.tenant_id}>
              {membership.tenant_name}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
