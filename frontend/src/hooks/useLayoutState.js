import { useCallback, useEffect, useState } from "react";

const HIDDEN_KEY = "main-ocr-sidebar-hidden";
const DESKTOP_QUERY = "(min-width: 1024px)";

function read() {
  try {
    return localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function write(hidden) {
  try {
    localStorage.setItem(HIDDEN_KEY, hidden ? "1" : "0");
  } catch {
    /* storage blocked: the flag just is not remembered */
  }
}

const isDesktopNow = () =>
  typeof window.matchMedia === "function" && window.matchMedia(DESKTOP_QUERY).matches;

// Sidebar state: `sidebarHidden` (desktop collapse, remembered) and `drawerOpen` (mobile, not).
export function useLayoutState() {
  const [sidebarHidden, setHidden] = useState(read);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isDesktop, setIsDesktop] = useState(isDesktopNow);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const mql = window.matchMedia(DESKTOP_QUERY);
    const onChange = (e) => {
      setIsDesktop(e.matches);
      if (e.matches) setDrawerOpen(false);
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const toggleSidebar = useCallback(() => {
    setHidden((h) => {
      write(!h);
      return !h;
    });
  }, []);
  const openDrawer = useCallback(() => setDrawerOpen(true), []);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  return { sidebarHidden, toggleSidebar, drawerOpen, openDrawer, closeDrawer, isDesktop };
}
