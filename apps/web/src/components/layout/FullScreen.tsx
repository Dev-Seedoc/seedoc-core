import type { ReactNode } from "react";

// Centres a loading, error or "no access" state on an otherwise empty screen (used by the layout guards).
export function FullScreen({ children }: { children: ReactNode }) {
  return <div className="flex min-h-svh items-center justify-center p-6">{children}</div>;
}
