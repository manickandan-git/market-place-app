import "server-only";

import createClient, { type Middleware } from "openapi-fetch";

import { config } from "@/lib/config";
import { getAccessToken, getCartToken } from "@/lib/session";

import type { paths } from "./schema";

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = await getAccessToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    const cartToken = await getCartToken();
    if (cartToken) {
      request.headers.set("X-Cart-Token", cartToken);
    }
    return request;
  },
};

/**
 * A network-level failure (gateway unreachable, DNS failure, connection
 * refused/reset) makes the underlying `fetch()` call *reject* rather than
 * resolve — openapi-fetch has no code path for that and lets it propagate
 * as a thrown exception, unlike a well-formed non-2xx HTTP response, which
 * it turns into the `{ error }` half of its `{ data, error }` result.
 *
 * Every function in lib/api/*.ts only handles that `{ error }` case (e.g.
 * `if (error) return null`) — none of them wrap calls in try/catch, so an
 * uncaught throw here propagates straight out of whatever Server Component
 * called it. Confirmed live: stopping the gateway crashed the products
 * page, and separately crashed the *root layout* itself (via
 * SiteHeader's getCart() call), which skips every page-level error.tsx
 * boundary entirely (error.tsx does not wrap the layout.js above it in
 * the same segment) and falls through to the bare, unstyled
 * global-error.tsx with no header/nav/footer on every single page.
 *
 * Fixing this once here — by turning a thrown network error into an
 * ordinary error Response — means every existing `if (error)` check
 * across the codebase already handles a gateway outage correctly, with
 * no per-call-site changes needed.
 */
const networkSafeFetch: typeof fetch = async (input, init) => {
  try {
    return await fetch(input, init);
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : "Network error";
    return new Response(
      JSON.stringify({
        error: { code: "upstream_unreachable", message },
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }
};

// Single client for every gateway call. Nothing here talks to any service
// port directly — only :9000, same as every other gateway consumer.
export const apiClient = createClient<paths>({
  baseUrl: config.gatewayUrl,
  fetch: networkSafeFetch,
});
apiClient.use(authMiddleware);

/**
 * Wraps a single gateway call with a one-shot refresh-and-retry on 401.
 * A 15-minute access token routinely expires mid-session; this mirrors the
 * gateway's own "exactly one retry, never blind" stance (see
 * services/api-gateway/app/services/proxy_service.py's docstring),
 * deliberately scoped to token refresh only — it does not retry on
 * timeouts or 5xx, since several gateway-proxied endpoints
 * (`POST /orders`, `POST /payments`) are non-idempotent.
 *
 * `refreshAccessToken` is passed in rather than imported directly to avoid
 * a circular import between this module and lib/api/auth.ts, which itself
 * needs `apiClient` to call `POST /api/v1/auth/refresh`.
 */
export async function withAuthRetry<T extends { response: Response }>(
  call: () => Promise<T>,
  refreshAccessToken: () => Promise<boolean>,
): Promise<T> {
  const result = await call();
  if (result.response.status !== 401) {
    return result;
  }
  const refreshed = await refreshAccessToken();
  if (!refreshed) {
    return result;
  }
  return call();
}
