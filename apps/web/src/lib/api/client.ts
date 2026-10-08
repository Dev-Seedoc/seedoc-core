import createClient from "openapi-fetch";

import type { paths } from "./schema";

// Generated paths already start with /api/v1, so the client talks to the page's own origin.
// Locally the Vite proxy forwards /api to :8000; in production Caddy does the same.
// `credentials: "include"` sends the HttpOnly `seedoc_session` cookie; the app never reads it.
export const client = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: "include",
  // Look up fetch per call (not once at import) so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
});
