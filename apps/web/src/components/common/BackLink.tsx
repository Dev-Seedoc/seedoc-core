import { ArrowLeft } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router";

import { Button } from "@/components/ui/button";

// Back to the list the user came from (with its filters and tab); opened directly, to `to`. `label` is translated.
export function BackLink({ to, label }: { to: string; label: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  const cameFromApp = location.key !== "default";
  return (
    <Button variant="ghost" size="sm" className="self-start" asChild>
      <Link
        to={to}
        onClick={(event) => {
          if (cameFromApp) {
            event.preventDefault();
            void navigate(-1);
          }
        }}
      >
        <ArrowLeft aria-hidden="true" />
        {label}
      </Link>
    </Button>
  );
}
