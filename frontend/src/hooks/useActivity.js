import { useQuery } from "@tanstack/react-query";
import { authApi } from "../api/auth";

export function useActivity(params) {
  return useQuery({
    queryKey: ["activity", params],
    queryFn: () => authApi.activity(params),
  });
}
