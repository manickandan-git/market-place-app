"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { z } from "zod";

import * as addressesApi from "@/lib/api/addresses";
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

const baseSchema = z.object({
  cart_id: z.uuid(),
  cart_version: z.coerce.number().int().positive(),
});

export async function createOrderAction(
  _prevState: CheckoutActionState,
  formData: FormData,
): Promise<CheckoutActionState> {
  const base = baseSchema.safeParse(Object.fromEntries(formData));
  if (!base.success) {
    return { ok: false, fieldErrors: toFieldErrors(base.error) };
  }

  const rawAddressId = formData.get("address_id");
  const addressId =
    typeof rawAddressId === "string" && rawAddressId && rawAddressId !== "new"
      ? rawAddressId
      : null;

  let shippingAddress: ordersApi.AddressInput;

  if (addressId) {
    // A saved address was picked: re-read it from user-service rather than
    // trusting client-supplied address text for it. The client only tells
    // us *which* address (a reference, not its contents) — ownership is
    // already enforced by user-service scoping /me/addresses to the
    // authenticated caller, same pattern the Next.js docs recommend for
    // any mutation where a client names a row it doesn't fully control.
    const saved = await addressesApi.getAddress(addressId);
    if (!saved) {
      return { ok: false, message: "That address could not be found." };
    }
    // order-service's AddressSnapshot requires a non-empty state_or_region
    // (enforced server-side; not visible from the bare OpenAPI type,
    // confirmed by actually hitting the endpoint) — user-service's own
    // address book leaves it optional, so an older saved address can
    // predate that requirement. Fail clearly rather than silently
    // submitting an empty string, which order-service rejects anyway.
    if (!saved.state_or_region) {
      return {
        ok: false,
        message:
          "This address is missing a state/region, which checkout requires. Please edit it in your address book first.",
      };
    }
    shippingAddress = {
      full_name: saved.recipient_name,
      line1: saved.address_line1,
      line2: saved.address_line2 || undefined,
      city: saved.city,
      state_or_region: saved.state_or_region,
      postal_code: saved.postal_code,
      country_code: saved.country_code,
      phone: saved.phone_number || undefined,
    };
  } else {
    const parsed = addressSchema.safeParse(Object.fromEntries(formData));
    if (!parsed.success) {
      return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
    }
    shippingAddress = {
      full_name: parsed.data.full_name,
      line1: parsed.data.line1,
      line2: parsed.data.line2 || undefined,
      city: parsed.data.city,
      state_or_region: parsed.data.state_or_region,
      postal_code: parsed.data.postal_code,
      country_code: parsed.data.country_code,
      phone: parsed.data.phone || undefined,
    };
  }

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

  const result = await ordersApi.createOrder(
    base.data.cart_id,
    base.data.cart_version,
    shippingAddress,
  );

  if (!result.ok || !result.order) {
    return { ok: false, message: result.message };
  }

  // Order creation retires the cart server-side (order-service marks it
  // CHECKED_OUT). Revalidate the root layout so SiteHeader's cart badge
  // (a separate cache segment from /cart) reflects that on the next
  // render, plus /cart itself in case the buyer navigates back to it.
  revalidatePath("/", "layout");
  revalidatePath("/cart");
  redirect(`/checkout/${result.order.id}/pay`);
}
