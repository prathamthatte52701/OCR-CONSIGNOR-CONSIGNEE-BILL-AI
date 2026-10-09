import axios from "axios";

const STORAGE_KEY = "main-ocr-admin-auth";

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
  if (!error.response) return true;
  return [502, 503, 504].includes(error.response.status);
}

export const client = axios.create({ baseURL: "/api" });

client.interceptors.request.use((config) => {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (stored?.token) config.headers.Authorization = `Bearer ${stored.token}`;
  } catch {
    // no stored auth
  }
  return config;
});

client.interceptors.response.use(
  (response) => {
    setServerDown(false);
    return response;
  },
  (error) => {
    setServerDown(isUnreachable(error));

    const status = error.response?.status;
    if (status === 401 && !error.config?.url?.includes("/auth/")) {
      localStorage.removeItem(STORAGE_KEY);
      window.location.href = "/login";
    }

    error.userMessage = extractUserMessage(error);
    return Promise.reject(error);
  }
);

function extractUserMessage(error) {
  if (!error.response) return "Cannot reach the server. Check your connection.";
  const detail = error.response.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join(", ");
  if (detail?.message) return detail.message;
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
