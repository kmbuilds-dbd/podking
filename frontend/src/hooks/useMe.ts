import { useQuery } from "@tanstack/react-query"
import { api, UnauthenticatedError } from "@/api"

export type Me = { email: string; display_name: string | null }

export function useMe() {
  return useQuery<Me>({
    queryKey: ["me"],
    queryFn: () => api<Me>("/api/me"),
    retry: (failureCount, error) => {
      if (error instanceof UnauthenticatedError) return false
      return failureCount < 2
    },
  })
}
