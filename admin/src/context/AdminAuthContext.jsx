import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { adminAuthApi } from "../api/admin";

const AdminAuthContext = createContext(null);
const STORAGE_KEY = "main-ocr-admin-auth";

function loadStored() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

export function AdminAuthProvider({ children }) {
  const [auth, setAuthState] = useState(loadStored);
  const [isInitializing, setIsInitializing] = useState(!!loadStored().token);

  const setAuth = useCallback((data) => {
    setAuthState(data);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }, []);

  const logout = useCallback(() => {
    setAuthState({});
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  // Re-verify the persisted session against the server once on mount, so a
  // revoked/expired token doesn't leave the admin looking logged-in.
  useEffect(() => {
    const stored = loadStored();
    if (!stored.token) return;
    adminAuthApi
      .me()
      .then((data) => setAuth({ ...stored, ...data }))
      .catch(() => logout())
      .finally(() => setIsInitializing(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AdminAuthContext.Provider value={{ ...auth, isInitializing, setAuth, logout }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth() {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdminAuth must be used within AdminAuthProvider");
  return ctx;
}
