import { client } from "./client";

export const adminApi = {
  users: (params) => client.get("/admin/users", { params }).then((r) => r.data),
  user: (id) => client.get(`/admin/users/${id}`).then((r) => r.data),
  updateUser: (id, data) => client.patch(`/admin/users/${id}`, data).then((r) => r.data),
  deleteUser: (id) => client.delete(`/admin/users/${id}`).then((r) => r.data),
  approveUser: (id) => client.post(`/admin/users/${id}/approve`).then((r) => r.data),
  rejectUser: (id, reason = null) =>
    client.post(`/admin/users/${id}/reject`, { reason }).then((r) => r.data),
  nukeUser: (id, data) => client.post(`/admin/users/${id}/nuke`, data).then((r) => r.data),
  nukeGlobal: (data) => client.post("/admin/nuke-global", data).then((r) => r.data),

  documents: (params) => client.get("/admin/documents", { params }).then((r) => r.data),
  document: (id) => client.get(`/admin/documents/${id}`).then((r) => r.data),
  // Files need the bearer token, so fetch as a blob (a plain <a href> would be sent without it).
  // Every call is audit-logged server-side (admin_downloaded_part1 / _part2).
  downloadDocumentFile: (id, part) =>
    client.get(`/admin/documents/${id}/download/${part}`, { responseType: "blob" }).then((r) => ({
      blob: r.data,
      filename: (r.headers["content-disposition"] || "").match(/filename="([^"]+)"/)?.[1] || part,
    })),
  correctDocument: (id, field, value) =>
    client.patch(`/admin/documents/${id}`, { field, value }).then((r) => r.data),
  deleteDocument: (id) => client.delete(`/admin/documents/${id}`).then((r) => r.data),
  purgeDocumentFiles: (id) => client.post(`/admin/documents/${id}/purge-files`).then((r) => r.data),

  logs: (params) => client.get("/admin/logs", { params }).then((r) => r.data),
  telemetry: () => client.get("/admin/telemetry").then((r) => r.data),

  passwordRequests: (params) => client.get("/admin/password-requests", { params }).then((r) => r.data),
  setTempPassword: (id, password) =>
    client.post(`/admin/password-requests/${id}/temp-password`, { password }).then((r) => r.data),
  dismissPasswordRequest: (id) =>
    client.post(`/admin/password-requests/${id}/dismiss`).then((r) => r.data),

  orphanedFiles: (params) => client.get("/admin/orphaned-files", { params }).then((r) => r.data),
  retryOrphanedFile: (id) => client.post(`/admin/orphaned-files/${id}/retry`).then((r) => r.data),
  dismissOrphanedFile: (id) => client.delete(`/admin/orphaned-files/${id}`).then((r) => r.data),
};

export const adminAuthApi = {
  login: (data) => client.post("/auth/login", data).then((r) => r.data),
  me: () => client.get("/auth/me").then((r) => r.data),
  updateMe: (data) => client.patch("/auth/me", data).then((r) => r.data),
  changePassword: (data) => client.post("/auth/change-password", data).then((r) => r.data),
};
