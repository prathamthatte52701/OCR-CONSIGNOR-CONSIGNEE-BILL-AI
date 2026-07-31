import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users, FileStack, ScrollText, LogOut, ShieldAlert } from "lucide-react";
import { useAdminAuth } from "../context/AdminAuthContext";
import { cn } from "../lib/utils";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/users", label: "Users", icon: Users },
  { to: "/documents", label: "Documents", icon: FileStack },
  { to: "/logs", label: "Logs", icon: ScrollText },
];

export default function AdminLayout() {
  const { username, logout } = useAdminAuth();
  const navigate = useNavigate();

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
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
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
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <span className="hidden sm:inline text-sm text-text-muted">{username}</span>
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
