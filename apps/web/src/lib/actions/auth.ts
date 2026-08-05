"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import * as authApi from "@/lib/api/auth";
import type { UserRole } from "@/lib/api/auth";
import * as cartApi from "@/lib/api/cart";
import { clearCartToken, getCartToken } from "@/lib/session";
import type { AuthActionState, RegisterActionState } from "./auth-state";

function toFieldErrors(error: z.ZodError): Record<string, string> {
  const fieldErrors: Record<string, string> = {};
  for (const issue of error.issues) {
    const field = String(issue.path[0] ?? "form");
    if (!(field in fieldErrors)) {
      fieldErrors[field] = issue.message;
    }
  }
  return fieldErrors;
}

function safeRedirectTarget(next: FormDataEntryValue | null): string {
  const value = typeof next === "string" ? next : "";
  return value.startsWith("/") && !value.startsWith("//") ? value : "/account";
}

const loginSchema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

export async function loginAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const parsed = loginSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }

  const result = await authApi.login(parsed.data);
  if (!result.ok) {
    return result;
  }

  // Best-effort: a guest cart from browsing before sign-in gets folded
  // into the buyer's account cart. A merge failure shouldn't block login
  // — the buyer just keeps whatever their account cart already had.
  const guestCartToken = await getCartToken();
  if (guestCartToken) {
    await cartApi.mergeGuestCart(guestCartToken);
    await clearCartToken();
  }

  redirect(safeRedirectTarget(formData.get("next")));
}

const registerSchema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(10, "Password must be at least 10 characters"),
  first_name: z.string().min(1, "First name is required"),
  last_name: z.string().min(1, "Last name is required"),
  role: z.enum(["BUYER", "SELLER"]),
});

export async function registerAction(
  _prevState: RegisterActionState,
  formData: FormData,
): Promise<RegisterActionState> {
  const parsed = registerSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    first_name: formData.get("first_name"),
    last_name: formData.get("last_name"),
    role: formData.get("role") || "BUYER",
  });
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }

  const result = await authApi.register({
    ...parsed.data,
    role: parsed.data.role as UserRole,
  });
  if (!result.ok) {
    return result;
  }

  return {
    ok: true,
    message: result.message,
    verificationToken: result.data?.verificationToken,
  };
}

const emailOnlySchema = z.object({ email: z.email("Enter a valid email address") });

export async function resendVerificationAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const parsed = emailOnlySchema.safeParse({ email: formData.get("email") });
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }
  return authApi.resendVerification(parsed.data.email);
}

const verifyEmailSchema = z.object({ token: z.string().min(1, "Token is required") });

export async function verifyEmailAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const parsed = verifyEmailSchema.safeParse({ token: formData.get("token") });
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }
  return authApi.verifyEmail(parsed.data.token);
}

export async function forgotPasswordAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const parsed = emailOnlySchema.safeParse({ email: formData.get("email") });
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }
  return authApi.forgotPassword(parsed.data.email);
}

const resetPasswordSchema = z.object({
  token: z.string().min(1, "Token is required"),
  new_password: z.string().min(10, "Password must be at least 10 characters"),
});

export async function resetPasswordAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const parsed = resetPasswordSchema.safeParse({
    token: formData.get("token"),
    new_password: formData.get("new_password"),
  });
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }
  return authApi.resetPassword(parsed.data.token, parsed.data.new_password);
}

export async function logoutAction(): Promise<void> {
  await authApi.logout();
  redirect("/");
}
