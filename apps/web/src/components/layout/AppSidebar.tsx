import {
  Building2,
  FileText,
  HardHat,
  LayoutDashboard,
  type LucideIcon,
  Package,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import type de from "@/i18n/de.json";
import { useMe } from "@/lib/api/hooks/auth";
import { cn } from "@/lib/utils";

type NavKey = Exclude<keyof (typeof de)["shell"]["nav"], "label">;

interface NavItem {
  to: string;
  key: NavKey;
  icon: LucideIcon;
}

// Paths from NAMING §7.
const MAIN_ITEMS: NavItem[] = [
  { to: "/", key: "dashboard", icon: LayoutDashboard },
  { to: "/documents", key: "documents", icon: FileText },
  { to: "/products", key: "products", icon: Package },
  { to: "/customers", key: "customers", icon: Building2 },
  { to: "/settings", key: "settings", icon: Settings },
];

const STAFF_ITEM: NavItem = { to: "/staff", key: "staff", icon: ShieldCheck };
const OPERATOR_ITEM: NavItem = { to: "/operator", key: "operator", icon: HardHat };

function SidebarLink({ item }: { item: NavItem }) {
  const { t } = useTranslation();
  const Icon = item.icon;

  return (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
        )
      }
    >
      <Icon className="size-4" aria-hidden="true" />
      {t(`shell.nav.${item.key}`)}
    </NavLink>
  );
}

export function AppSidebar() {
  const { t } = useTranslation();
  const { data: me } = useMe();

  const extraItems = [
    ...(me?.is_staff ? [STAFF_ITEM] : []),
    ...(me && me.operator_orgs.length > 0 ? [OPERATOR_ITEM] : []),
  ];

  return (
    <aside className="bg-muted/40 flex w-60 shrink-0 flex-col border-r">
      <div className="flex h-14 items-center border-b px-5 text-lg font-semibold tracking-tight">
        {t("common.appName")}
      </div>
      <nav aria-label={t("shell.nav.label")} className="flex flex-1 flex-col gap-1 p-3">
        {MAIN_ITEMS.map((item) => (
          <SidebarLink key={item.to} item={item} />
        ))}
        {extraItems.length > 0 && (
          <div className="mt-3 flex flex-col gap-1 border-t pt-3">
            {extraItems.map((item) => (
              <SidebarLink key={item.to} item={item} />
            ))}
          </div>
        )}
      </nav>
    </aside>
  );
}
