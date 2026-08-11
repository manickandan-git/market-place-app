"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import * as addressesApi from "@/lib/api/addresses";
import type { CartActionState as AddressActionState } from "./cart-state";

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
  recipient_name: z.string().min(1, "Recipient name is required"),
  address_line1: z.string().min(1, "Address line 1 is required"),
  address_line2: z.string().optional(),
  city: z.string().min(1, "City is required"),
  // Optional in user-service's own schema, but order-service's checkout
  // requires it (confirmed by hitting the real endpoint — see
  // lib/actions/checkout.ts) and this address book exists to feed
  // checkout, so require it here too rather than letting an incomplete
  // address get saved and only fail later at checkout time.
  state_or_region: z.string().min(1, "State/region is required"),
  postal_code: z.string().min(1, "Postal code is required"),
  country_code: z.string().length(2, "Use a 2-letter country code").toUpperCase(),
  phone_number: z.string().optional(),
  is_default: z.coerce.boolean().default(false),
});

export interface AddressFormState extends AddressActionState {
  fieldErrors?: Record<string, string>;
}

export async function createAddressAction(
  _prevState: AddressFormState,
  formData: FormData,
): Promise<AddressFormState> {
  const parsed = addressSchema.safeParse({
    recipient_name: formData.get("recipient_name"),
    address_line1: formData.get("address_line1"),
    address_line2: formData.get("address_line2") || undefined,
    city: formData.get("city"),
    state_or_region: formData.get("state_or_region") || undefined,
    postal_code: formData.get("postal_code"),
    country_code: formData.get("country_code"),
    phone_number: formData.get("phone_number") || undefined,
    is_default: formData.get("is_default") === "on",
  });
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }

  const result = await addressesApi.createAddress({
    address_type: "shipping",
    ...parsed.data,
  });
  revalidatePath("/account/addresses");
  return { ok: result.ok, message: result.message };
}

export async function updateAddressAction(
  _prevState: AddressFormState,
  formData: FormData,
): Promise<AddressFormState> {
  const addressId = String(formData.get("address_id"));
  const version = Number(formData.get("version"));
  const parsed = addressSchema.safeParse({
    recipient_name: formData.get("recipient_name"),
    address_line1: formData.get("address_line1"),
    address_line2: formData.get("address_line2") || undefined,
    city: formData.get("city"),
    state_or_region: formData.get("state_or_region") || undefined,
    postal_code: formData.get("postal_code"),
    country_code: formData.get("country_code"),
    phone_number: formData.get("phone_number") || undefined,
    is_default: formData.get("is_default") === "on",
  });
  if (!addressId || !Number.isFinite(version)) {
    return { ok: false, message: "Invalid request." };
  }
  if (!parsed.success) {
    return { ok: false, fieldErrors: toFieldErrors(parsed.error) };
  }

  const result = await addressesApi.updateAddress(
    addressId,
    { address_type: "shipping", ...parsed.data },
    version,
  );
  revalidatePath("/account/addresses");
  revalidatePath("/checkout");
  return { ok: result.ok, message: result.message };
}

export async function deleteAddressAction(
  _prevState: AddressActionState,
  formData: FormData,
): Promise<AddressActionState> {
  const addressId = String(formData.get("address_id"));
  const version = Number(formData.get("version"));
  const result = await addressesApi.deleteAddress(addressId, version);
  revalidatePath("/account/addresses");
  return { ok: result.ok, message: result.message };
}
