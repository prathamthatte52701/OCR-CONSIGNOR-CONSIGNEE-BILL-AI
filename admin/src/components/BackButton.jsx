import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { cn } from "../lib/utils";
import { safePath } from "./routeHistory";

// Goes back inside the app only: browser history when this tab has in-app history (so a list
// keeps its filters and page, they live in the URL), otherwise `fallback` (replace, so Back never
// bounces to the page it just left). `to` forces a same-app target. Unsafe targets are ignored.
export default function BackButton({ fallback = "/dashboard", to, className = "" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const busy = useRef(false);

  useEffect(() => {
    busy.current = false;
  }, [location.key]);

  const handleClick = () => {
    if (to) return navigate(safePath(to, fallback));
    // Rapid clicks would queue several navigate(-1) and walk out of the app.
    if (busy.current) return;
    busy.current = true;
    setTimeout(() => {
      busy.current = false;
    }, 600);
    const hasHistory = location.key !== "default" || (window.history.state?.idx ?? 0) > 0;
    if (!hasHistory) return navigate(safePath(fallback), { replace: true });
    return navigate(-1);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label="Go back"
      className={cn(
        "inline-flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-sm font-medium text-text-muted hover:border-accent/50 hover:text-text",
        className
      )}
    >
      <ArrowLeft size={14} aria-hidden="true" />
      Back
    </button>
  );
}
