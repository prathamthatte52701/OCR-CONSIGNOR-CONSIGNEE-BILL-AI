import { useEffect, useState } from "react";
import { authApi } from "../api/auth";
import { useAuthStore } from "../store/authStore";

// Re-verifies the persisted session against the server on app mount.
// A stored token can be stale (revoked, password changed, expired) — this
// confirms it's still valid before routes render, and refreshes the cached
// profile fields (username/email/role) while keeping the existing token.
export function useInitAuth() {
  const token = useAuthStore((s) => s.token);
  const updateProfile = useAuthStore((s) => s.updateProfile);
  const logout = useAuthStore((s) => s.logout);
  const [isInitializing, setIsInitializing] = useState(!!token);

  useEffect(() => {
    if (!token) return;
    authApi
      .me()
      .then((data) => updateProfile(data))
      .catch(() => logout())
      .finally(() => setIsInitializing(false));
    // Run once on mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return isInitializing;
}
