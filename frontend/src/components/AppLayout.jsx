import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { LogOut, PanelLeftClose, PanelLeftOpen, Menu } from "lucide-react";
import { useAuthStore } from "../store/authStore";
import { useChat } from "../hooks/useChat";
import { userIdFromToken } from "../utils/chatCore";
import { useLogout } from "../hooks/useAuth";
import { useLayoutState } from "../hooks/useLayoutState";
import AppSidebar from "./AppSidebar";
import ApprovedWelcomeDialog from "./ApprovedWelcomeDialog";
import ChatButton from "./chat/ChatButton";
import ChatPanel from "./chat/ChatPanel";

export default function AppLayout() {
  const username = useAuthStore((s) => s.username);
  const logout = useLogout();
  const { pathname } = useLocation();
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const mustChangePassword = useAuthStore((s) => s.mustChangePassword);
  const {
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
  } = useLayoutState();
  const menuRef = useRef(null);
  const chatPanelRef = useRef(null);

  // Chat is for signed-in non-admin users, and not while a forced password change is pending.
  const userId = userIdFromToken(token);
  const canChat = Boolean(userId) && role !== "admin" && !mustChangePassword;
  const chat = useChat({ userId, canChat, open: chatOpen });
  const chatShown = canChat && chatOpen;
  const chatOverlayShown = chatShown && !chatDocked;
  const chatDockedShown = chatShown && chatDocked;
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

  // Overlay chat: same treatment as the drawer. Escape closes (the focus trap in the panel hands
  // focus back to the Chat button) and the page behind does not scroll.
  useEffect(() => {
    if (!chatOverlayShown) return undefined;
    const onKeyDown = (e) => {
      if (e.key === "Escape") closeChat();
    };
    document.addEventListener("keydown", onKeyDown);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prev;
    };
  }, [chatOverlayShown, closeChat]);

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
            {canChat && <ChatButton unread={chat.unread} open={chatOpen} onClick={toggleChat} />}
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

      <div className={`${railShown ? "lg:pl-60" : ""} ${chatDockedShown ? "pr-[var(--chat-w)]" : ""}`}>
        <main className="mx-auto max-w-6xl px-4 py-6">
          <Outlet />
        </main>
      </div>
      <ApprovedWelcomeDialog />
      {chatShown && (
        <ChatPanel
          overlay={chatOverlayShown}
          panelRef={chatPanelRef}
          onClose={closeChat}
          color={chat.color}
          onColorChange={chat.setColor}
          colorFailed={chat.colorFailed}
          messages={chat.messages}
          offset={chat.offset}
          now={chat.now}
          expiredEdits={chat.expiredEdits}
          edit={chat.edit}
          onStartEdit={chat.startEdit}
          onCancelEdit={chat.cancelEdit}
          onSaveEdit={chat.saveEdit}
          hasOlder={chat.hasOlder}
          loadingOlder={chat.loadingOlder}
          onLoadOlder={chat.loadOlder}
          onAtBottomChange={chat.setAtBottom}
          loading={chat.loading}
          draft={chat.draft}
          onDraftChange={chat.setDraft}
          onSend={chat.send}
          sending={chat.sending}
          sendError={chat.sendError}
          admins={chat.admins}
          adminsState={chat.adminsState}
          selectedAdminId={chat.selectedAdminId}
          onSelectAdmin={chat.selectAdmin}
          onInsertSummary={chat.insertSummary}
          summaryError={chat.summaryError}
          files={chat.files}
          file={chat.file}
          onFileChange={chat.chooseFile}
          fileError={chat.fileError}
          progress={chat.progress}
        />
      )}
    </div>
  );
}
