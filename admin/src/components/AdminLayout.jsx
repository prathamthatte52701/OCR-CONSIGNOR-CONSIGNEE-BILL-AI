import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users, FileStack, ScrollText, LogOut, ShieldAlert, FileWarning, KeyRound } from "lucide-react";
import { adminApi } from "../api/admin";
import { useAdminAuth } from "../context/AdminAuthContext";
import { cn } from "../lib/utils";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/users", label: "Users", icon: Users },
  { to: "/password-requests", label: "Password requests", icon: KeyRound, badge: "openRequests" },
  { to: "/documents", label: "Documents", icon: FileStack },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/orphaned-files", label: "Orphaned Files", icon: FileWarning },
];

export default function AdminLayout() {
  const { username, logout } = useAdminAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [counts, setCounts] = useState({ openRequests: 0 });

  // Open password-request count for the nav badge: refreshed on every page change.
  useEffect(() => {
    adminApi
      .passwordRequests({ status: "open" })
      .then((data) => setCounts({ openRequests: data.openCount || 0 }))
      .catch(() => {});
  }, [location.pathname]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <ShieldAlert size={18} className="text-accent" />
            <span className="font-semibold tracking-tight">THE MAIN OCR &middot; Admin</span>
          </div>

          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map(({ to, label, icon: Icon, badge }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded text-sm",
                    isActive ? "bg-accent/15 text-accent" : "text-text-muted hover:text-text hover:bg-surface-raised"
                  )
                }
              >
                <Icon size={15} />
                <span className="hidden sm:inline">{label}</span>
                {badge && counts[badge] > 0 && (
                  <span className="rounded-full bg-warning text-bg text-[10px] font-semibold px-1.5">
                    {counts[badge]}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <NavLink to="/profile" className="hidden sm:inline text-sm text-text-muted hover:text-accent">
              {username}
            </NavLink>
            <button onClick={handleLogout} className="flex items-center gap-1.5 text-sm text-text-muted hover:text-danger">
              <LogOut size={15} />
              <span className="hidden sm:inline">Log out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
