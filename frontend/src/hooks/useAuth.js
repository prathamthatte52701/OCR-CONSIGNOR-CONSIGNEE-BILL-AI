import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { authApi } from "../api/auth";
import { useAuthStore } from "../store/authStore";

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  return useMutation({
    mutationFn: authApi.login,
    onSuccess: (data) => {
      setAuth(data);
      toast.success(`Welcome back, ${data.username}.`);
      const params = new URLSearchParams(window.location.search);
      navigate(params.get("next") || "/dashboard");
    },
    // A 403 means pending/rejected approval - the login page shows that inline and persistently,
    // so don't also flash it as a toast. Everything else is a normal transient error.
    onError: (error) => {
      if (error.response?.status !== 403) toast.error(error.userMessage || "Login failed.");
    },
  });
}

export function useSignup() {
  const navigate = useNavigate();
  return useMutation({
    mutationFn: authApi.signup,
    onSuccess: () => {
      toast.success("Account created. Waiting for admin approval.");
      navigate("/login?notice=signup");
    },
    onError: (error) => toast.error(error.userMessage || "Signup failed."),
  });
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  return () => {
    logout();
    navigate("/login");
  };
}
