import { Loader2 } from "lucide-react";

// Centered loading indicator for a list or pane that is still loading.
export function Spinner() {
  return (
    <div className="flex justify-center py-8">
      <Loader2 className="text-muted-foreground size-5 animate-spin" aria-hidden="true" />
    </div>
  );
}
