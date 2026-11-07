import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { LogOut, PanelLeftClose, PanelLeftOpen, Menu } from "lucide-react";
import { useAuthStore } from "../store/authStore";
import { useLogout } from "../hooks/useAuth";
import { useLayoutState } from "../hooks/useLayoutState";
import AppSidebar from "./AppSidebar";
import ApprovedWelcomeDialog from "./ApprovedWelcomeDialog";

export default function AppLayout() {
  const username = useAuthStore((s) => s.username);
  const logout = useLogout();
  const { pathname } = useLocation();
  const { sidebarHidden, toggleSidebar, drawerOpen, openDrawer, closeDrawer, isDesktop } =
    useLayoutState();
  const menuRef = useRef(null);
  const drawerShown = !isDesktop && drawerOpen;
  const railShown = isDesktop && !sidebarHidden;

  // A route change closes the drawer.
  useEffect(() => {
    closeDrawer();
  }, [pathname, closeDrawer]);

  // Drawer open: Escape closes and the page behind does not scroll. The focus trap inside the
  // drawer hands focus back to the menu button when the drawer unmounts.
  useEffect(() => {
    if (!drawerShown) return undefined;
    const onKeyDown = (e) => {
      if (e.key === "Escape") closeDrawer();
    };
    document.addEventListener("keydown", onKeyDown);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prev;
    };
  }, [drawerShown, closeDrawer]);

  const ToggleIcon = isDesktop ? (railShown ? PanelLeftClose : PanelLeftOpen) : Menu;
  const label = isDesktop ? (railShown ? "Hide sidebar" : "Show sidebar") : "Open menu";

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="sticky top-0 z-50 h-14 border-b border-border bg-surface">
        <div className="flex h-full items-center justify-between gap-2 px-4">
          <div className="flex min-w-0 items-center gap-3">
            <button
              ref={menuRef}
              type="button"
              onClick={isDesktop ? toggleSidebar : openDrawer}
              aria-label={label}
              title={label}
              aria-expanded={isDesktop ? railShown : drawerShown}
              aria-controls={railShown || drawerShown ? "app-sidebar" : undefined}
              className="rounded p-1.5 text-text-muted hover:bg-surface-raised hover:text-text"
            >
              <ToggleIcon size={18} aria-hidden="true" />
            </button>
            <span className="h-2.5 w-2.5 rounded-full bg-accent" />
            <span className="truncate font-semibold tracking-tight">THE MAIN OCR</span>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <span className="hidden max-w-[10rem] truncate text-sm text-text-muted sm:inline">
              {username}
            </span>
            <button
              onClick={logout}
              className="flex items-center gap-1.5 text-sm text-text-muted hover:text-danger"
            >
              <LogOut size={15} /> Log out
            </button>
          </div>
        </div>
      </header>

      {railShown && <AppSidebar variant="rail" />}
      {drawerShown && <AppSidebar variant="drawer" onClose={closeDrawer} />}

      <div className={railShown ? "lg:pl-60" : ""}>
        <main className="mx-auto max-w-6xl px-4 py-6">
          <Outlet />
        </main>
      </div>
      <ApprovedWelcomeDialog />
    </div>
  );
}
