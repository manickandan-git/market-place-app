export interface DecodedJwtPayload {
  exp?: number;
  sub?: string;
  [claim: string]: unknown;
}

/**
 * Decodes a JWT payload WITHOUT verifying its signature. This is only ever
 * used to peek at `exp` for proactive-refresh timing (see proxy.ts) — it
 * must never be trusted as proof of authenticity. Real verification
 * (signature, issuer, audience) happens at the gateway's edge check and
 * again in every downstream service, unchanged; this file exists purely
 * as a UX optimization to avoid sending an obviously-expired token.
 */
export function decodeJwtPayload(token: string): DecodedJwtPayload | null {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }
  try {
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload.padEnd(
      payload.length + ((4 - (payload.length % 4)) % 4),
      "=",
    );
    const json = atob(padded);
    return JSON.parse(json) as DecodedJwtPayload;
  } catch {
    return null;
  }
}

export function isExpiringWithin(token: string, seconds: number): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) {
    return true;
  }
  const nowSeconds = Date.now() / 1000;
  return payload.exp - nowSeconds <= seconds;
}
