import { createContext, useContext, useState, useCallback } from "react";

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

  const setAuth = useCallback((data) => {
    setAuthState(data);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }, []);

  const logout = useCallback(() => {
    setAuthState({});
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return (
    <AdminAuthContext.Provider value={{ ...auth, setAuth, logout }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth() {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdminAuth must be used within AdminAuthProvider");
  return ctx;
}
