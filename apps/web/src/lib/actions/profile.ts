"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import * as profileApi from "@/lib/api/profile";
import type { AuthActionState } from "./auth-state";

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

const profileSchema = z.object({
  display_name: z.string().min(1, "Display name is required"),
  first_name: z.string().optional(),
  last_name: z.string().optional(),
  phone_number: z.string().optional(),
});

export async function createProfileAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const parsed = profileSchema.safeParse({
    display_name: formData.get("display_name"),
  });
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }
  const result = await profileApi.createProfile(parsed.data.display_name);
  revalidatePath("/account");
  return { ok: result.ok, message: result.message };
}

export async function updateProfileAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const parsed = profileSchema.safeParse({
    display_name: formData.get("display_name"),
    first_name: formData.get("first_name") || undefined,
    last_name: formData.get("last_name") || undefined,
    phone_number: formData.get("phone_number") || undefined,
  });
  const version = Number(formData.get("version"));
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }
  if (!Number.isFinite(version)) {
    return { ok: false, message: "Invalid request." };
  }
  const result = await profileApi.updateProfile(parsed.data, version);
  revalidatePath("/account");
  return { ok: result.ok, message: result.message };
}
