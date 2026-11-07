import { useRef } from "react";
import { NavLink } from "react-router-dom";
import { LayoutDashboard, Upload, FileStack, History, CircleHelp, UserRound, X } from "lucide-react";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { cn } from "../lib/utils";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/upload", label: "Upload", icon: Upload },
  { to: "/documents", label: "My Documents", icon: FileStack },
  { to: "/activity", label: "My Activity", icon: History },
  { to: "/help", label: "Help", icon: CircleHelp },
  { to: "/profile", label: "Profile", icon: UserRound },
];

function SidebarNav({ onNavigate }) {
  return (
    <nav aria-label="Main" className="flex-1 space-y-1 overflow-y-auto p-3">
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded px-3 py-2 text-sm",
              isActive
                ? "bg-accent/15 text-accent"
                : "text-text-muted hover:bg-surface-raised hover:text-text"
            )
          }
        >
          <Icon size={16} aria-hidden="true" />
          <span className="truncate">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

// Mounted only while open, so the focus trap runs exactly for its lifetime and focus returns to
// the menu button when it unmounts.
function Drawer({ onClose }) {
  const ref = useRef(null);
  useFocusTrap(ref);
  return (
    <div className="fixed inset-0 z-[60]">
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-black/60"
      />
      <div
        ref={ref}
        id="app-sidebar"
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        className="relative flex h-full w-60 max-w-[85vw] flex-col border-r border-border bg-surface shadow-2xl"
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <span className="font-semibold tracking-tight">THE MAIN OCR</span>
          <button type="button" onClick={onClose} aria-label="Close menu" className="p-1 text-text-muted hover:text-text">
            <X size={18} />
          </button>
        </div>
        <SidebarNav onNavigate={onClose} />
      </div>
    </div>
  );
}

// variant "rail": fixed left sidebar (desktop). variant "drawer": slide-in modal (mobile).
export default function AppSidebar({ variant, onClose }) {
  if (variant === "drawer") return <Drawer onClose={onClose} />;
  return (
    <div
      id="app-sidebar"
      className="fixed bottom-0 left-0 top-14 z-40 flex w-60 flex-col border-r border-border bg-surface"
    >
      <SidebarNav />
    </div>
  );
}
