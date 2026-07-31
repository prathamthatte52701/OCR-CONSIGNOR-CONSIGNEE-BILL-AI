import { Navigate, Outlet } from "react-router-dom";
import { useAdminAuth } from "../context/AdminAuthContext";

export default function RequireAdminAuth() {
  const { token } = useAdminAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}
