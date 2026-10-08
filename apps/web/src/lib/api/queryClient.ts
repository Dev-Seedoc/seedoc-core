import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError, showErrorToast } from "./errors";

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
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.meta?.errorToast !== false) {
          showErrorToast(error);
        }
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.errorToast !== false) {
          showErrorToast(error);
        }
      },
    }),
    defaultOptions: {
      queries: { staleTime: 30_000, retry: shouldRetry, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}
