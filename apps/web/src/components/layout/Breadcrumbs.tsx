import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useMatches } from "react-router";

import { isRouteHandle } from "./routeHandle";

export function Breadcrumbs() {
  const { t } = useTranslation();
  const matches = useMatches();

  const crumbs = matches.flatMap((match) =>
    isRouteHandle(match.handle) && match.handle.crumb
      ? [{ id: match.id, pathname: match.pathname, label: match.handle.crumb(t) }]
      : [],
  );

  return (
    <nav aria-label={t("shell.breadcrumbs.label")}>
      <ol className="text-muted-foreground flex items-center gap-1.5 text-sm">
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <li key={crumb.id} className="flex items-center gap-1.5">
              {index > 0 && <ChevronRight className="size-3.5" aria-hidden="true" />}
              {isLast ? (
                <span aria-current="page" className="text-foreground font-medium">
                  {crumb.label}
                </span>
              ) : (
                <Link to={crumb.pathname} className="hover:text-foreground transition-colors">
                  {crumb.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
