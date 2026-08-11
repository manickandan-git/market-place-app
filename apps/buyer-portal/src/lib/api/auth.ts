import "server-only";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import {
  clearCartToken,
  clearSessionCookies,
  getRefreshToken,
  setSessionCookies,
} from "@/lib/session";

import { extractErrorMessage, extractFieldErrors } from "./errors";

export type RegisterInput = components["schemas"]["auth_RegisterRequest"];
export type LoginInput = components["schemas"]["auth_LoginRequest"];
export type UserRole = components["schemas"]["auth_UserRole"];

export interface ActionResult<T = undefined> {
  ok: boolean;
  message?: string;
  fieldErrors?: Record<string, string>;
  data?: T;
}

export async function register(
  input: RegisterInput,
): Promise<ActionResult<{ verificationToken?: string | null }>> {
  const { data, error } = await apiClient.POST("/api/v1/auth/register", {
    body: input,
  });
  if (error) {
    return {
      ok: false,
      message: extractErrorMessage(error),
      fieldErrors: extractFieldErrors(error),
    };
  }
  return {
    ok: true,
    message: data.message,
    data: { verificationToken: data.verification_token },
  };
}

export async function verifyEmail(token: string): Promise<ActionResult> {
  const { error } = await apiClient.POST("/api/v1/auth/verify-email", {
    body: { token },
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true };
}

export async function resendVerification(email: string): Promise<ActionResult> {
  const { data, error } = await apiClient.POST(
    "/api/v1/auth/resend-verification",
    { body: { email } },
  );
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, message: data.message };
}

export async function forgotPassword(email: string): Promise<ActionResult> {
  const { data, error } = await apiClient.POST(
    "/api/v1/auth/forgot-password",
    { body: { email } },
  );
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, message: data.message };
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<ActionResult> {
  const { error } = await apiClient.POST("/api/v1/auth/reset-password", {
    body: { token, new_password: newPassword },
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, message: "Your password has been reset." };
}

/** Logs in and sets session cookies. Only callable from a Server Action / Route Handler. */
export async function login(input: LoginInput): Promise<ActionResult> {
  const { data, error } = await apiClient.POST("/api/v1/auth/login", {
    body: input,
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  await setSessionCookies({
    access_token: data.access_token,
    refresh_token: data.refresh_token,
  });
  return { ok: true };
}

/**
 * Attempts to rotate the access token using the current refresh token
 * cookie, setting fresh cookies on success. Returns false (without
 * throwing) on any failure — an expired/invalid/missing refresh token is
 * an expected outcome, not an error, and callers should fall back to
 * treating the user as logged out. Only callable from a Server Action /
 * Route Handler / proxy.ts, since it mutates cookies.
 */
export async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    return false;
  }
  const { data, error } = await apiClient.POST("/api/v1/auth/refresh", {
    body: { refresh_token: refreshToken },
  });
  if (error) {
    return false;
  }
  await setSessionCookies({
    access_token: data.access_token,
    refresh_token: data.refresh_token,
  });
  return true;
}

/** Revokes the current refresh token server-side and clears local session cookies. */
export async function logout(): Promise<void> {
  const refreshToken = await getRefreshToken();
  if (refreshToken) {
    await apiClient.POST("/api/v1/auth/logout", {
      body: { refresh_token: refreshToken },
    });
  }
  await clearSessionCookies();
  await clearCartToken();
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<ActionResult> {
  const { error } = await apiClient.POST("/api/v1/auth/change-password", {
    body: { current_password: currentPassword, new_password: newPassword },
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true };
}
