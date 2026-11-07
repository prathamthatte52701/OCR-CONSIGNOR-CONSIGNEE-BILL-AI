import { create } from "zustand";
import { persist } from "zustand/middleware";

// The one-time "you were approved" notice survives a reload (sessionStorage, not localStorage,
// so it never outlives the tab) until OK is pressed. Every access is guarded.
const NOTICE_KEY = "main-ocr-approval-notice";

function readNotice() {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(NOTICE_KEY));
    if (parsed?.justApproved === true) {
      return { justApproved: true, approvedAt: parsed.approvedAt ?? null };
    }
  } catch {
    /* unreadable or unavailable - no notice */
  }
  return { justApproved: false, approvedAt: null };
}

function writeNotice(justApproved, approvedAt) {
  try {
    if (justApproved) sessionStorage.setItem(NOTICE_KEY, JSON.stringify({ justApproved: true, approvedAt }));
    else sessionStorage.removeItem(NOTICE_KEY);
  } catch {
    /* storage unavailable - the notice then lives in memory only */
  }
}

export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,
      username: null,
      email: null,
      role: null,
      // Not part of the persisted auth state (see partialize); mirrored in sessionStorage.
      ...readNotice(),
      // True while an admin-set temporary password is in force (set by the API client on a
      // PASSWORD_CHANGE_REQUIRED 403). In memory only: the server re-sends it on the first call.
      mustChangePassword: false,
      setMustChangePassword: (value) => set({ mustChangePassword: Boolean(value) }),
      setAuth: ({ token, username, email, role, justApproved, approvedAt }) => {
        writeNotice(Boolean(justApproved), approvedAt ?? null);
        set({
          token,
          username,
          email,
          role,
          justApproved: Boolean(justApproved),
          approvedAt: approvedAt ?? null,
        });
      },
      clearJustApproved: () => {
        writeNotice(false, null);
        set({ justApproved: false, approvedAt: null });
      },
      updateProfile: ({ username, email, role }) => set({ username, email, role }),
      logout: () => {
        writeNotice(false, null);
        set({
          token: null,
          username: null,
          email: null,
          role: null,
          justApproved: false,
          approvedAt: null,
          mustChangePassword: false,
        });
      },
    }),
    {
      name: "main-ocr-auth",
      partialize: ({ token, username, email, role }) => ({ token, username, email, role }),
    }
  )
);
