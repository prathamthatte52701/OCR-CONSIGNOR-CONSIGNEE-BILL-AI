import { Routes, Route, Navigate } from "react-router-dom";
import AdminLayout from "./components/AdminLayout";
import RequireAdminAuth from "./components/RequireAdminAuth";
import ServerDownBanner from "./components/ServerDownBanner";
import AdminLoginPage from "./pages/AdminLoginPage";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import AdminUserDetailPage from "./pages/AdminUserDetailPage";
import AdminDocumentsPage from "./pages/AdminDocumentsPage";
import AdminDocumentDetailPage from "./pages/AdminDocumentDetailPage";
import AdminLogsPage from "./pages/AdminLogsPage";

export default function App() {
  return (
    <>
      <ServerDownBanner />
      <Routes>
        <Route path="/login" element={<AdminLoginPage />} />

        <Route element={<RequireAdminAuth />}>
          <Route element={<AdminLayout />}>
            <Route path="/dashboard" element={<AdminDashboardPage />} />
            <Route path="/users" element={<AdminUsersPage />} />
            <Route path="/users/:id" element={<AdminUserDetailPage />} />
            <Route path="/documents" element={<AdminDocumentsPage />} />
            <Route path="/documents/:id" element={<AdminDocumentDetailPage />} />
            <Route path="/logs" element={<AdminLogsPage />} />
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  );
}
