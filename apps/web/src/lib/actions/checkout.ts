"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import * as cartApi from "@/lib/api/cart";
import * as ordersApi from "@/lib/api/orders";
import type { CheckoutActionState } from "./checkout-state";

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

const addressSchema = z.object({
  full_name: z.string().min(1, "Full name is required"),
  line1: z.string().min(1, "Address line 1 is required"),
  line2: z.string().optional(),
  city: z.string().min(1, "City is required"),
  state_or_region: z.string().min(1, "State/region is required"),
  postal_code: z.string().min(1, "Postal code is required"),
  country_code: z
    .string()
    .length(2, "Use a 2-letter country code (e.g. US)")
    .toUpperCase(),
  phone: z.string().optional(),
});

const checkoutSchema = z.object({
  cart_id: z.uuid(),
  cart_version: z.coerce.number().int().positive(),
  ...addressSchema.shape,
});

export async function createOrderAction(
  _prevState: CheckoutActionState,
  formData: FormData,
): Promise<CheckoutActionState> {
  const parsed = checkoutSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }

  const { cart_id, cart_version, ...address } = parsed.data;

  // Re-check readiness right before placing the order: prices/availability
  // may have changed since the cart page was rendered.
  const readiness = await cartApi.checkReadiness();
  if (readiness && !readiness.ready) {
    return {
      ok: false,
      message:
        "Some items in your cart are no longer available or changed price. Please review your cart.",
    };
  }

  const result = await ordersApi.createOrder(cart_id, cart_version, {
    full_name: address.full_name,
    line1: address.line1,
    line2: address.line2 || undefined,
    city: address.city,
    state_or_region: address.state_or_region,
    postal_code: address.postal_code,
    country_code: address.country_code,
    phone: address.phone || undefined,
  });

  if (!result.ok || !result.order) {
    return { ok: false, message: result.message };
  }

  redirect(`/checkout/${result.order.id}/pay`);
}
