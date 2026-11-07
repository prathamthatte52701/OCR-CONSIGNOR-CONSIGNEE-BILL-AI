import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

export default function RequireAuth() {
  const token = useAuthStore((s) => s.token);
  const mustChangePassword = useAuthStore((s) => s.mustChangePassword);
  const location = useLocation();

  if (!token) {
    const next = encodeURIComponent(location.pathname);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  // Forced password change: every route goes to the one allowed page until the flag clears.
  const onForcedPage = location.pathname === "/set-new-password";
  if (mustChangePassword && !onForcedPage) return <Navigate to="/set-new-password" replace />;
  if (!mustChangePassword && onForcedPage) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}
