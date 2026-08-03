import { Navigate, Outlet } from "react-router-dom";
import { useAdminAuth } from "../context/AdminAuthContext";
import LoadingState from "./LoadingState";

export default function RequireAdminAuth() {
  const { token, isInitializing } = useAdminAuth();
  if (isInitializing) return <LoadingState message="Checking session..." />;
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}
