import { type KeyboardEvent, type ReactNode, useId, useRef } from "react";
import { useSearchParams } from "react-router";

import { cn } from "@/lib/utils";

export interface UrlTab<T extends string> {
  value: T;
  // Already translated.
  label: string;
}

interface UrlTabsProps<T extends string> {
  // Translated name of the tab list for screen readers.
  label: string;
  tabs: readonly UrlTab<T>[];
  children: (tab: T) => ReactNode;
}

const TAB_PARAM = "tab";

// Tabs kept in `?tab=` (NAMING §7: English identifiers, labels from i18n), so a tab can be linked and survives a
// reload. An unknown or missing value shows the first tab. Arrow keys, Home and End move between tabs (WAI-ARIA).
export function UrlTabs<T extends string>({ label, tabs, children }: UrlTabsProps<T>) {
  const [searchParams, setSearchParams] = useSearchParams();
  const baseId = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const requested = searchParams.get(TAB_PARAM);
  const active = tabs.find((tab) => tab.value === requested) ?? tabs[0];

  function select(value: T) {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set(TAB_PARAM, value);
        return next;
      },
      { replace: true },
    );
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((tab) => tab.value === active?.value);
    const targets: Record<string, number> = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index - 1 + tabs.length) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    };
    const target = targets[event.key];
    const tab = target === undefined ? undefined : tabs[target];
    if (target === undefined || !tab) {
      return;
    }
    event.preventDefault();
    select(tab.value);
    tabRefs.current[target]?.focus();
  }

  if (!active) {
    return null;
  }
  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b" onKeyDown={handleKeyDown}>
        {tabs.map((tab, index) => {
          const isActive = tab.value === active.value;
          return (
            <button
              key={tab.value}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.value}`}
              aria-selected={isActive}
              aria-controls={`${baseId}-panel`}
              tabIndex={isActive ? 0 : -1}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "border-primary text-foreground"
                  : "text-muted-foreground hover:text-foreground border-transparent",
              )}
              onClick={() => {
                select(tab.value);
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${baseId}-panel`} aria-labelledby={`${baseId}-tab-${active.value}`}>
        {children(active.value)}
      </div>
    </div>
  );
}
