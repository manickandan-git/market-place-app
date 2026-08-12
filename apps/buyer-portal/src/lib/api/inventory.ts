import "server-only";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Availability = components["schemas"]["inventory_AvailabilityResponse"];

export async function getAvailability(
  sku: string,
  quantity: number = 1,
): Promise<Availability | null> {
  const { data, error } = await apiClient.GET("/api/v1/availability/{sku}", {
    params: {
      path: { sku },
      query: { quantity },
    },
  });
  if (error) {
    return null;
  }
  return data;
}
