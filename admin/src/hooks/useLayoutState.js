import { useCallback, useEffect, useRef, useState } from "react";
import { CHAT_OPEN_KEY, readFlag, writeFlag } from "../utils/layoutStorage";

const DOCK_QUERY = "(min-width: 1280px)"; // chat docks beside the content from here, overlays below

const matchesDock = () =>
  typeof window.matchMedia === "function" && window.matchMedia(DOCK_QUERY).matches;

// Chat panel state. The stored open flag only applies when docked; an overlay always starts closed.
export function useLayoutState() {
  const [chatDocked, setChatDocked] = useState(matchesDock);
  const [chatOpen, setChatOpenState] = useState(() => matchesDock() && readFlag(CHAT_OPEN_KEY));
  const chatRef = useRef(chatOpen);

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

  const setChatOpen = useCallback(
    (next) => {
      chatRef.current = next;
      if (chatDocked) writeFlag(CHAT_OPEN_KEY, next);
      setChatOpenState(next);
    },
    [chatDocked]
  );
  const toggleChat = useCallback(() => setChatOpen(!chatRef.current), [setChatOpen]);
  const closeChat = useCallback(() => setChatOpen(false), [setChatOpen]);

  return { chatOpen, chatDocked, toggleChat, closeChat };
}
