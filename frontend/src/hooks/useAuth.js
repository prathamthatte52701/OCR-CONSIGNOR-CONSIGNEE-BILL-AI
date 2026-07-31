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
    onError: (error) => toast.error(error.userMessage || "Login failed."),
  });
}

export function useSignup() {
  const navigate = useNavigate();
  return useMutation({
    mutationFn: authApi.signup,
    onSuccess: () => {
      toast.success("Account created. Please log in.");
      navigate("/login");
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
