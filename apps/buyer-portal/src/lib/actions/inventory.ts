"use server";

import { getAvailability } from "@/lib/api/inventory";
import type { Availability } from "@/lib/api/inventory";

export async function checkAvailability(
  sku: string,
  quantity: number,
): Promise<Availability | null> {
  return getAvailability(sku, quantity);
}
