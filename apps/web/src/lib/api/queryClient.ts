import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError, getErrorCode, showErrorToast } from "./errors";
import { queryKeys } from "./queryKeys";

declare module "@tanstack/react-query" {
  interface Register {
    // `errorToast: false` turns off the global error toast, e.g. when a screen shows the error inline.
    queryMeta: { errorToast?: boolean };
    mutationMeta: { errorToast?: boolean };
  }
}

// 4xx answers will not change on retry; only network/server errors are retried once.
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) {
    return false;
  }
  return failureCount < 1;
}

export function createQueryClient(): QueryClient {
  function handleError(error: unknown, meta: { errorToast?: boolean } | undefined) {
    // The staff session lost its TOTP confirmation: reload `get_me` (mfa_verified → false) and StaffLayout
    // shows the TOTP screen instead of an error.
    if (getErrorCode(error) === "mfa_required") {
      void queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() });
      return;
    }
    if (meta?.errorToast !== false) {
      showErrorToast(error);
    }
  }

  const queryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        handleError(error, query.meta);
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        handleError(error, mutation.meta);
      },
    }),
    defaultOptions: {
      queries: { staleTime: 30_000, retry: shouldRetry, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return queryClient;
}
