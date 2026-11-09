import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users, FileStack, ScrollText, LogOut, ShieldAlert, FileWarning, KeyRound, Wrench } from "lucide-react";
import { adminApi } from "../api/admin";
import { useAdminAuth } from "../context/AdminAuthContext";
import { cn } from "../lib/utils";
import { useLayoutState } from "../hooks/useLayoutState";
import { chatClient } from "../api/chat";
import { allowFocusBeat, createState } from "../utils/autoRefreshCore";
import { createTokens, userIdFromToken } from "../utils/chatAdminCore";
import { notifyAdminTick, COUNTS_CHANGED_EVENT } from "../utils/events";
import AdminChat from "./chat/AdminChat";
import ChatButton from "./chat/ChatButton";

const HEARTBEAT_MS = 15000;

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/users", label: "Users", icon: Users },
  { to: "/password-requests", label: "Password requests", icon: KeyRound, badge: "openRequests" },
  { to: "/documents", label: "Documents", icon: FileStack },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/orphaned-files", label: "Orphaned Files", icon: FileWarning },
  { to: "/maintenance", label: "Maintenance", icon: Wrench },
];

export default function AdminLayout() {
  const { username, token, logout } = useAdminAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [counts, setCounts] = useState({ openRequests: 0 });
  const [chatUnread, setChatUnread] = useState({ count: 0, byUser: null });
  const { chatOpen, chatDocked, toggleChat, closeChat } = useLayoutState();
  const chatButton = useRef(null);
  const chatPanel = useRef(null);
  const refocusChat = useRef(false);
  const adminId = userIdFromToken(token);
  const chatOverlay = chatOpen && !chatDocked;
  const [unreadTokens] = useState(createTokens); // a slow older answer must not put an old count back

  // Total unread for the Chat badge, on the shell heartbeat (15 s, only while the tab is visible).
  // Errors (401/403/network) are ignored: the client already handles a dead session.
  const loadUnread = useCallback(() => {
    const t = unreadTokens.next();
    chatClient
      .unread()
      .then((d) => {
        if (unreadTokens.isCurrent(t)) setChatUnread({ count: d.count || 0, byUser: d.byUser || [] });
      })
      .catch(() => {});
  }, [unreadTokens]);

  useEffect(() => {
    if (!adminId) return undefined;
    const visible = () => document.visibilityState === "visible";
    const beat = () => {
      loadUnread();
      notifyAdminTick();
    };
    const gate = createState();
    const wake = () => {
      if (visible() && allowFocusBeat(gate, Date.now())) beat();
    };
    loadUnread();
    const timer = setInterval(() => {
      if (visible()) beat();
    }, HEARTBEAT_MS);
    window.addEventListener(COUNTS_CHANGED_EVENT, loadUnread);
    window.addEventListener("focus", wake);
    document.addEventListener("visibilitychange", wake);
    return () => {
      clearInterval(timer);
      window.removeEventListener(COUNTS_CHANGED_EVENT, loadUnread);
      window.removeEventListener("focus", wake);
      document.removeEventListener("visibilitychange", wake);
    };
  }, [adminId, loadUnread]);

  // Overlay chat (below 1280 px): Escape closes and gives focus back to the Chat button, and the
  // page behind does not scroll.
  const closeChatAndRefocus = useCallback(() => {
    refocusChat.current = true;
    closeChat();
  }, [closeChat]);
  useEffect(() => {
    if (!chatOpen && refocusChat.current) {
      refocusChat.current = false;
      chatButton.current?.focus();
    }
  }, [chatOpen]);
  useEffect(() => {
    if (!chatOverlay) return undefined;
    // a dialog opened from the panel (clear chat) handles its own Escape
    const onKey = (e) => {
      if (e.key === "Escape" && !document.querySelector("dialog[open]")) closeChatAndRefocus();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [chatOverlay, closeChatAndRefocus]);

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
      <header className="sticky top-0 z-30 h-14 border-b border-border bg-surface">
        <div className="mx-auto flex h-full max-w-6xl items-center justify-between px-4">
          <div className="flex min-w-0 items-center gap-2">
            <ShieldAlert size={18} className="shrink-0 text-accent" />
            <span className="hidden truncate font-semibold tracking-tight">THE MAIN OCR &middot; Admin</span>
          </div>

          <nav className="flex min-w-0 items-center gap-1 overflow-x-auto">
            {NAV_ITEMS.map(({ to, label, icon: Icon, badge }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex shrink-0 items-center gap-1.5 px-3 py-1.5 rounded text-sm lg:px-2",
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

          <div className="flex shrink-0 items-center gap-3">
            {adminId && (
              <ChatButton
                buttonRef={chatButton}
                unread={chatUnread.count}
                open={chatOpen}
                onClick={toggleChat}
              />
            )}
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

      <div className={chatOpen && chatDocked ? "pr-[var(--chat-w)]" : ""}>
        <main className="mx-auto max-w-6xl px-4 py-6">
          <Outlet />
        </main>
      </div>

      {adminId && (
        <AdminChat
          adminId={adminId}
          open={chatOpen}
          overlay={chatOverlay}
          onClose={closeChatAndRefocus}
          panelRef={chatPanel}
          byUser={chatUnread.byUser}
        />
      )}
    </div>
  );
}
