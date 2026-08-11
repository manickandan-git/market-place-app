import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { isExpiringWithin } from "@/lib/jwt";

// Proxy is the only place that can proactively refresh the access token:
// it can mutate response cookies, unlike a plain Server Component render
// (see lib/session.ts's docstrings). It runs on the Node.js runtime by
// default in Next 16, so a plain fetch() to the gateway is fine here.
const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:9000";
const ACCESS_TOKEN_COOKIE = "mp_access_token";
const REFRESH_TOKEN_COOKIE = "mp_refresh_token";
const REFRESH_MARGIN_SECONDS = 60;

const PROTECTED_PREFIXES = ["/account", "/checkout", "/orders"];

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

async function tryRefresh(
  refreshToken: string,
): Promise<{ access_token: string; refresh_token: string } | null> {
  try {
    const response = await fetch(`${GATEWAY_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as {
      access_token: string;
      refresh_token: string;
    };
  } catch {
    // Gateway unreachable or timed out — treat like a failed refresh
    // rather than blocking navigation entirely; the page itself will
    // surface a real error if it also can't reach the gateway.
    return null;
  }
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!isProtected(pathname)) {
    return NextResponse.next();
  }

  const accessToken = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_TOKEN_COOKIE)?.value;

  const needsRefresh =
    !accessToken || isExpiringWithin(accessToken, REFRESH_MARGIN_SECONDS);

  if (!needsRefresh) {
    return NextResponse.next();
  }

  if (!refreshToken) {
    return redirectToLogin(request);
  }

  const refreshed = await tryRefresh(refreshToken);
  if (!refreshed) {
    const response = redirectToLogin(request);
    response.cookies.delete(ACCESS_TOKEN_COOKIE);
    response.cookies.delete(REFRESH_TOKEN_COOKIE);
    return response;
  }

  const response = NextResponse.next();
  const isProduction = process.env.NODE_ENV === "production";
  response.cookies.set(ACCESS_TOKEN_COOKIE, refreshed.access_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: 900,
  });
  response.cookies.set(REFRESH_TOKEN_COOKIE, refreshed.refresh_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  return response;
}

function redirectToLogin(request: NextRequest) {
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/account/:path*", "/checkout/:path*", "/orders/:path*"],
};
