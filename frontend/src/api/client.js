import axios from "axios";
import { useAuthStore } from "../store/authStore";

let serverDown = false;
const listeners = new Set();

export function onServerDownChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function setServerDown(value) {
  if (serverDown === value) return;
  serverDown = value;
  listeners.forEach((fn) => fn(value));
}

export function isServerDown() {
  return serverDown;
}

function isUnreachable(error) {
  if (!error.response) return true; // true network failure
  // Vite's dev proxy itself returns 502/503/504 when the backend is down.
  return [502, 503, 504].includes(error.response.status);
}

// Exact texts the backend sends with a 403 when an account is not (or no longer) approved.
export const PENDING_MESSAGE = "Waiting for admin approval.";
export const REJECTED_MESSAGE = "Your request was not approved. Contact the admin.";

export const client = axios.create({
  baseURL: "/api",
});

client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => {
    setServerDown(false);
    return response;
  },
  (error) => {
    if (isUnreachable(error)) {
      setServerDown(true);
    } else {
      setServerDown(false);
    }

    const status = error.response?.status;
    if (status === 401 && !error.config?.url?.includes("/auth/")) {
      useAuthStore.getState().logout();
      const next = encodeURIComponent(window.location.pathname);
      window.location.href = `/login?next=${next}`;
    }

    // Account was un-approved while logged in: end the session and say why on the login page.
    // (A 403 from the login call itself is shown inline by the login page - don't redirect.)
    const detail = error.response?.data?.detail;
    if (
      status === 403 &&
      (detail === PENDING_MESSAGE || detail === REJECTED_MESSAGE) &&
      !error.config?.url?.includes("/auth/login")
    ) {
      useAuthStore.getState().logout();
      window.location.href = `/login?notice=${detail === PENDING_MESSAGE ? "pending" : "rejected"}`;
    }

    error.userMessage = extractUserMessage(error);
    return Promise.reject(error);
  }
);

function extractUserMessage(error) {
  if (!error.response) return "Cannot reach the server. Check your connection.";
  const detail = error.response.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg).join(", ");
  }
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  if (error.response.data?.error) return error.response.data.error;
  return "Something went wrong. Please try again.";
}

// With responseType "blob" even an error response body arrives as a Blob, so the usual
// extractUserMessage() cannot read its JSON. Read the Blob text and pull the server's message out.
export async function readErrorMessage(error, fallback) {
  const data = error?.response?.data;
  if (data instanceof Blob) {
    try {
      const detail = JSON.parse(await data.text())?.detail;
      if (typeof detail === "string") return detail;
    } catch {
      /* not JSON - fall through */
    }
  }
  return error?.userMessage || fallback;
}
