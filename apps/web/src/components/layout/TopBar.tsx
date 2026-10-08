import { Breadcrumbs } from "./Breadcrumbs";
import { TenantSwitcher } from "./TenantSwitcher";
import { UserMenu } from "./UserMenu";

export function TopBar() {
  return (
    <header className="bg-background flex h-14 shrink-0 items-center justify-between gap-4 border-b px-6">
      <Breadcrumbs />
      <div className="flex items-center gap-2">
        <TenantSwitcher />
        <UserMenu />
      </div>
    </header>
  );
}
