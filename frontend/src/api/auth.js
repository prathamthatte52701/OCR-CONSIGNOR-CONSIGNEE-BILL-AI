import { client } from "./client";

export const authApi = {
  signup: (data) => client.post("/auth/signup", data).then((r) => r.data),
  login: (data) => client.post("/auth/login", data).then((r) => r.data),
  me: () => client.get("/auth/me").then((r) => r.data),
  updateMe: (data) => client.patch("/auth/me", data).then((r) => r.data),
  changePassword: (data) => client.post("/auth/change-password", data).then((r) => r.data),
  requestPasswordReset: (data) => client.post("/auth/password-reset-request", data).then((r) => r.data),
  activity: (params) => client.get("/auth/me/activity", { params }).then((r) => r.data),
};
