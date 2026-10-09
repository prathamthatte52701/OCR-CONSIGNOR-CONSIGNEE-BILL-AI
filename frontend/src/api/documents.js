import { client } from "./client";

export const documentsApi = {
  upload: (part1File, part2File) => {
    const form = new FormData();
    form.append("part1", part1File);
    form.append("part2", part2File);
    return client.post("/documents/upload", form).then((r) => r.data);
  },
  list: (params) => client.get("/documents", { params }).then((r) => r.data),
  stats: () => client.get("/documents/stats").then((r) => r.data),
  get: (id) => client.get(`/documents/${id}`).then((r) => r.data),
  correct: (id, field, value) =>
    client.patch(`/documents/${id}/correct`, { field, value }).then((r) => r.data),
  reprocess: (id) => client.post(`/documents/${id}/reprocess`).then((r) => r.data),
  deleteDocument: (id) => client.delete(`/documents/${id}`).then((r) => r.data),
  purgeFiles: (id) => client.post(`/documents/${id}/purge-files`).then((r) => r.data),
  // The file route needs the bearer token, which a plain <a href> never sends - fetch it as a
  // blob through the shared client (it adds the Authorization header) and save that.
  downloadFile: (id, part) =>
    client.get(`/documents/${id}/download/${part}`, { responseType: "blob" }).then((r) => ({
      blob: r.data,
      filename: (r.headers["content-disposition"] || "").match(/filename="([^"]+)"/)?.[1] || part,
    })),
  downloadAll: (params) =>
    client
      .post("/documents/download-all", null, { params, responseType: "blob" })
      .then((r) => ({
        blob: r.data,
        included: Number(r.headers["x-included-count"] ?? 0),
        skipped: Number(r.headers["x-skipped-count"] ?? 0),
      })),
};
