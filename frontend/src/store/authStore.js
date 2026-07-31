import { create } from "zustand";
import { persist } from "zustand/middleware";

export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,
      username: null,
      email: null,
      role: null,
      setAuth: ({ token, username, email, role }) => set({ token, username, email, role }),
      logout: () => set({ token: null, username: null, email: null, role: null }),
    }),
    { name: "main-ocr-auth" }
  )
);
