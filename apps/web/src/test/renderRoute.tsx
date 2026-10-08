import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, type InitialEntry, RouterProvider } from "react-router";
import { vi } from "vitest";

import { queryKeys } from "@/lib/api/queryKeys";
import type { MeRead } from "@/lib/api/types";
import { routes } from "@/router";

export const TEST_ME: MeRead = {
  user: { id: "00000000-0000-4000-8000-000000000001", email: "owner@example.com", full_name: "Olga Owner" },
  memberships: [
    { tenant_id: "00000000-0000-4000-8000-00000000000a", tenant_name: "Alpha Maschinenbau", role: "owner" },
  ],
  operator_orgs: [],
  is_staff: false,
  mfa_verified: false,
};

// Renders the real routes at `entry`. Pass `me` to start logged in (no request for /auth/me is made).
export function renderRoute(entry: InitialEntry, me?: MeRead) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  if (me) {
    queryClient.setQueryData(queryKeys.auth.me(), me);
  }
  const router = createMemoryRouter(routes, { initialEntries: [entry] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

export interface FakeResponse {
  status: number;
  body?: unknown;
}

export function apiError(status: number, code: string, details: Record<string, unknown> = {}): FakeResponse {
  return { status, body: { error: { code, message: code, details } } };
}

// An answer, or a function choosing one from the request (e.g. by its query string).
export type FakeAnswer = FakeResponse | ((request: Request) => FakeResponse);

// Stubs fetch with one answer per "METHOD /api/v1/path" (query string ignored). Unknown requests answer 404.
export function stubApi(answers: Record<string, FakeAnswer>) {
  const fetchMock = vi.fn((request: Request) => {
    const key = `${request.method} ${new URL(request.url).pathname}`;
    const answerOrFn = answers[key] ?? apiError(404, "not_found");
    const answer = typeof answerOrFn === "function" ? answerOrFn(request) : answerOrFn;
    const body = answer.body === undefined ? null : JSON.stringify(answer.body);
    return Promise.resolve(
      new Response(body, { status: answer.status, headers: { "Content-Type": "application/json" } }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
