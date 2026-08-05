"use server";

import { revalidatePath } from "next/cache";

import * as ordersApi from "@/lib/api/orders";
import type { CartActionState as OrderActionState } from "./cart-state";

export async function cancelOrderAction(
  _prevState: OrderActionState,
  formData: FormData,
): Promise<OrderActionState> {
  const orderId = String(formData.get("order_id"));
  const version = Number(formData.get("version"));
  const reason = String(formData.get("reason") || "Changed my mind");

  const result = await ordersApi.cancelOrder(orderId, version, reason);
  revalidatePath(`/orders/${orderId}`);
  return { ok: result.ok, message: result.message };
}
