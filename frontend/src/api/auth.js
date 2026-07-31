import { client } from "./client";

export const authApi = {
  signup: (data) => client.post("/auth/signup", data).then((r) => r.data),
  login: (data) => client.post("/auth/login", data).then((r) => r.data),
  me: () => client.get("/auth/me").then((r) => r.data),
  updateMe: (data) => client.patch("/auth/me", data).then((r) => r.data),
  changePassword: (data) => client.post("/auth/change-password", data).then((r) => r.data),
  forgotPasswordVerify: (data) => client.post("/auth/forgot-password/verify", data).then((r) => r.data),
  forgotPasswordReset: (data) => client.post("/auth/forgot-password/reset", data).then((r) => r.data),
};
