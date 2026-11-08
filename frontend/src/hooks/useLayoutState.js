import { useCallback, useEffect, useRef, useState } from "react";
import { CHAT_OPEN_KEY, readFlag, writeFlag } from "../utils/layoutStorage";

const HIDDEN_KEY = "main-ocr-sidebar-hidden";
const DESKTOP_QUERY = "(min-width: 1024px)";
const DOCK_QUERY = "(min-width: 1280px)"; // chat docks beside the content from here, overlays below

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

const matches = (query) =>
  typeof window.matchMedia === "function" && window.matchMedia(query).matches;

// Sidebar state: `sidebarHidden` (desktop collapse, remembered) and `drawerOpen` (mobile, not).
// Chat state: `chatOpen` (remembered only while docked; an overlay always starts closed) and
// `chatDocked`. One overlay at a time: an overlaid chat and the sidebar drawer close each other.
export function useLayoutState() {
  const [sidebarHidden, setHidden] = useState(read);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isDesktop, setIsDesktop] = useState(() => matches(DESKTOP_QUERY));
  const [chatDocked, setChatDocked] = useState(() => matches(DOCK_QUERY));
  const [chatOpen, setChatOpenState] = useState(
    () => matches(DOCK_QUERY) && readFlag(CHAT_OPEN_KEY)
  );
  const chatRef = useRef(chatOpen);

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

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const mql = window.matchMedia(DOCK_QUERY);
    const onChange = (e) => {
      const open = e.matches && readFlag(CHAT_OPEN_KEY);
      chatRef.current = open;
      setChatDocked(e.matches);
      setChatOpenState(open);
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

  const setChatOpen = useCallback(
    (next) => {
      chatRef.current = next;
      if (chatDocked) writeFlag(CHAT_OPEN_KEY, next);
      else if (next) setDrawerOpen(false);
      setChatOpenState(next);
    },
    [chatDocked]
  );
  const toggleChat = useCallback(() => setChatOpen(!chatRef.current), [setChatOpen]);
  const closeChat = useCallback(() => setChatOpen(false), [setChatOpen]);

  const openDrawer = useCallback(() => {
    if (!chatDocked) {
      chatRef.current = false;
      setChatOpenState(false);
    }
    setDrawerOpen(true);
  }, [chatDocked]);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  return {
    sidebarHidden,
    toggleSidebar,
    drawerOpen,
    openDrawer,
    closeDrawer,
    isDesktop,
    chatOpen,
    chatDocked,
    toggleChat,
    closeChat,
  };
}
