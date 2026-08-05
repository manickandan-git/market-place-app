import "server-only";

import { cookies } from "next/headers";

// httpOnly — never readable from client-side JS. This is the whole point
// of the BFF pattern: the browser only ever sees an opaque session cookie,
// never the bearer token itself.
const ACCESS_TOKEN_COOKIE = "mp_access_token";
const REFRESH_TOKEN_COOKIE = "mp_refresh_token";
// Not httpOnly — this is a cart identifier (cart-service's `X-Cart-Token`),
// not a credential. It doesn't grant access to anything but one anonymous
// cart, so there's nothing gained by hiding it from client JS and it's
// simpler to let client components read it if ever needed.
const CART_TOKEN_COOKIE = "mp_cart_token";

// Matches the real values observed from auth-service: access tokens carry
// `expires_in: 900`, refresh tokens are valid ~7 days (confirmed from a
// real token's iat/exp during end-to-end testing of the gateway).
const ACCESS_TOKEN_MAX_AGE_SECONDS = 900;
const REFRESH_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7;

const isProduction = process.env.NODE_ENV === "production";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

/** Server Actions / Route Handlers only — cookies can't be set from a Server Component render. */
export async function setSessionCookies(tokens: TokenPair): Promise<void> {
  const store = await cookies();
  store.set(ACCESS_TOKEN_COOKIE, tokens.access_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: ACCESS_TOKEN_MAX_AGE_SECONDS,
  });
  store.set(REFRESH_TOKEN_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: REFRESH_TOKEN_MAX_AGE_SECONDS,
  });
}

export async function clearSessionCookies(): Promise<void> {
  const store = await cookies();
  store.delete(ACCESS_TOKEN_COOKIE);
  store.delete(REFRESH_TOKEN_COOKIE);
}

export async function getAccessToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(ACCESS_TOKEN_COOKIE)?.value;
}

export async function getRefreshToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(REFRESH_TOKEN_COOKIE)?.value;
}

export async function isAuthenticated(): Promise<boolean> {
  return (await getAccessToken()) !== undefined;
}

export async function setCartToken(token: string): Promise<void> {
  const store = await cookies();
  store.set(CART_TOKEN_COOKIE, token, {
    httpOnly: false,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
}

export async function getCartToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(CART_TOKEN_COOKIE)?.value;
}

export async function clearCartToken(): Promise<void> {
  const store = await cookies();
  store.delete(CART_TOKEN_COOKIE);
}
