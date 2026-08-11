import "server-only";

import { apiClient } from "@/lib/api/client";
import { extractErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Profile = components["schemas"]["user_BuyerProfileResponse"];

export interface ProfileResult {
  ok: boolean;
  profile?: Profile;
  message?: string;
}

/** user-service's own buyer/seller profile — distinct from auth-service's
 * identity record at GET /api/v1/users/me. A freshly registered account
 * has no profile row here until one is created. */
export async function getProfile(): Promise<Profile | null> {
  const { data, error } = await apiClient.GET("/api/v1/me");
  if (error) {
    return null;
  }
  return data;
}

export async function createProfile(displayName: string): Promise<ProfileResult> {
  const { data, error } = await apiClient.POST("/api/v1/me", {
    body: { display_name: displayName },
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, profile: data };
}

export async function updateProfile(
  updates: components["schemas"]["user_BuyerProfileUpdate"],
  version: number,
): Promise<ProfileResult> {
  const { data, error } = await apiClient.PATCH("/api/v1/me", {
    params: { header: { "If-Match": String(version) } },
    body: updates,
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, profile: data };
}
