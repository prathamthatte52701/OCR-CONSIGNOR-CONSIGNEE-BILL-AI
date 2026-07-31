import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import { AdminAuthProvider } from "./context/AdminAuthContext";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <AdminAuthProvider>
      <BrowserRouter>
        <App />
        <Toaster theme="dark" position="top-right" richColors />
      </BrowserRouter>
    </AdminAuthProvider>
  </StrictMode>
);
