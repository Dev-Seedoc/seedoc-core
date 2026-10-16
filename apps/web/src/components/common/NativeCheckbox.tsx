import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

interface NativeCheckboxProps extends Omit<ComponentProps<"input">, "type"> {
  // "Some but not all": shown as a dash. Browsers only allow setting it from script, hence the ref callback.
  indeterminate?: boolean;
}

// The browser's own checkbox, sized and coloured like the other controls. Used instead of a Radix checkbox, which
// would be a new dependency.
export function NativeCheckbox({ indeterminate = false, className, ...props }: NativeCheckboxProps) {
  return (
    <input
      type="checkbox"
      ref={(element) => {
        if (element) {
          element.indeterminate = indeterminate;
        }
      }}
      className={cn(
        "accent-primary size-4 shrink-0 cursor-pointer rounded-sm align-middle disabled:cursor-not-allowed",
        "focus-visible:ring-ring/50 outline-none focus-visible:ring-[3px]",
        className,
      )}
      {...props}
    />
  );
}
