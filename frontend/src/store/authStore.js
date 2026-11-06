import { create } from "zustand";
import { persist } from "zustand/middleware";

export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,
      username: null,
      email: null,
      role: null,
      // In memory only (see partialize): the one-time "you were approved" notice.
      justApproved: false,
      approvedAt: null,
      setAuth: ({ token, username, email, role, justApproved, approvedAt }) =>
        set({
          token,
          username,
          email,
          role,
          justApproved: Boolean(justApproved),
          approvedAt: approvedAt ?? null,
        }),
      clearJustApproved: () => set({ justApproved: false, approvedAt: null }),
      updateProfile: ({ username, email, role }) => set({ username, email, role }),
      logout: () =>
        set({ token: null, username: null, email: null, role: null, justApproved: false, approvedAt: null }),
    }),
    {
      name: "main-ocr-auth",
      partialize: ({ token, username, email, role }) => ({ token, username, email, role }),
    }
  )
);
