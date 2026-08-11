import "server-only";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type CurrentUser = components["schemas"]["auth_UserResponse"];

/** The auth-service identity record (id/email/role) — distinct from
 * user-service's richer buyer/seller profile at GET /api/v1/me, which
 * account/address-book pages (phase 6) use instead. */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const { data, error } = await apiClient.GET("/api/v1/users/me");
  if (error) {
    return null;
  }
  return data;
}
