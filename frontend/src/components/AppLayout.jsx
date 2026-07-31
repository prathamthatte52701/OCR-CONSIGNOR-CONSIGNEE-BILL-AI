import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Upload, FileStack, CircleHelp, LogOut, Menu, X } from "lucide-react";
import { useState } from "react";
import { useAuthStore } from "../store/authStore";
import { useLogout } from "../hooks/useAuth";
import { cn } from "../lib/utils";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/upload", label: "Upload", icon: Upload },
  { to: "/documents", label: "Documents", icon: FileStack },
  { to: "/help", label: "Help", icon: CircleHelp },
];

export default function AppLayout() {
  const username = useAuthStore((s) => s.username);
  const logout = useLogout();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-accent" />
            <span className="font-semibold tracking-tight">THE MAIN OCR</span>
          </div>

          <nav className="hidden md:flex items-center gap-1">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded text-sm",
                    isActive
                      ? "bg-accent/15 text-accent"
                      : "text-text-muted hover:text-text hover:bg-surface-raised"
                  )
                }
              >
                <Icon size={15} />
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="hidden md:flex items-center gap-3">
            <NavLink to="/profile" className="text-sm text-text-muted hover:text-text">
              {username}
            </NavLink>
            <button
              onClick={logout}
              className="flex items-center gap-1.5 text-sm text-text-muted hover:text-danger"
            >
              <LogOut size={15} /> Log out
            </button>
          </div>

          <button className="md:hidden" onClick={() => setMenuOpen((v) => !v)} aria-label="Menu">
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        {menuOpen && (
          <nav className="md:hidden border-t border-border px-4 py-2 flex flex-col gap-1">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 px-2 py-2 rounded text-sm",
                    isActive ? "bg-accent/15 text-accent" : "text-text-muted"
                  )
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
            <NavLink to="/profile" onClick={() => setMenuOpen(false)} className="px-2 py-2 text-sm text-text-muted">
              Profile ({username})
            </NavLink>
            <button onClick={logout} className="flex items-center gap-2 px-2 py-2 text-sm text-danger text-left">
              <LogOut size={16} /> Log out
            </button>
          </nav>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
