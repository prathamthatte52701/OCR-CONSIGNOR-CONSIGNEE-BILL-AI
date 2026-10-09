import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import RequireAuth from "./components/RequireAuth";
import ServerDownBanner from "./components/ServerDownBanner";
import GlobalConfirmDialog from "./components/GlobalConfirmDialog";
import LoadingState from "./components/LoadingState";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import Dashboard from "./pages/Dashboard";
import UploadPage from "./pages/UploadPage";
import DocumentsPage from "./pages/DocumentsPage";
import DocumentDetailPage from "./pages/DocumentDetailPage";
import DocumentsViewAllPage from "./pages/DocumentsViewAllPage";
import ProfilePage from "./pages/ProfilePage";
import ActivityPage from "./pages/ActivityPage";
import HelpPage from "./pages/HelpPage";
import NotFoundPage from "./pages/NotFoundPage";
import { useInitAuth } from "./hooks/useInitAuth";

export default function App() {
  const isInitializing = useInitAuth();

  if (isInitializing) {
    return <LoadingState message="Checking session..." />;
  }

  return (
    <>
      <ServerDownBanner />
      <GlobalConfirmDialog />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />

        <Route element={<RequireAuth />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/documents/view-all" element={<DocumentsViewAllPage />} />
            <Route path="/documents/:id" element={<DocumentDetailPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/activity" element={<ActivityPage />} />
            <Route path="/help" element={<HelpPage />} />
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  );
}
