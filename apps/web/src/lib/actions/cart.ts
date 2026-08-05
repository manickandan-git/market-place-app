"use server";

import { revalidatePath } from "next/cache";

import * as cartApi from "@/lib/api/cart";
import { getCartToken, isAuthenticated, setCartToken } from "@/lib/session";
import type { CartActionState } from "./cart-state";

/**
 * Ensures a cart identity exists, returning its *current* version — every
 * cart mutation, including add-item, requires If-Match-Version (confirmed
 * against the real endpoint; the generated schema marks it optional but
 * cart-service's required_version dependency 428s without it). For a
 * brand new guest, cart-service 401s ("Sign in or provide X-Cart-Token")
 * unless a guest cart already exists, so a first-ever "add to cart" click
 * has to create one first — its creation response already carries the
 * fresh cart's version (always 1), so no extra round trip is needed for
 * that case.
 */
async function resolveCartVersion(): Promise<number | null> {
  if (!(await isAuthenticated()) && !(await getCartToken())) {
    const created = await cartApi.createGuestCart();
    if (!created) {
      return null;
    }
    await setCartToken(created.cartToken);
    return created.cart.version;
  }
  const cart = await cartApi.getCart();
  return cart?.version ?? null;
}

export async function addToCartAction(
  productId: string,
  variantId: string,
  quantity: number,
): Promise<CartActionState> {
  const version = await resolveCartVersion();
  if (version === null) {
    return { ok: false, message: "Could not load your cart." };
  }
  const result = await cartApi.addItem(productId, variantId, quantity, version);
  revalidatePath("/cart");
  return { ok: result.ok, message: result.message };
}

/** FormData-shaped wrapper around addToCartAction, for useActionState-bound forms. */
export async function addToCartFormAction(
  _prevState: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const productId = String(formData.get("product_id"));
  const variantId = String(formData.get("variant_id"));
  const quantity = Number(formData.get("quantity")) || 1;
  if (!productId || !variantId) {
    return { ok: false, message: "Select an option first." };
  }
  return addToCartAction(productId, variantId, quantity);
}

export async function updateQuantityAction(
  _prevState: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const itemId = String(formData.get("item_id"));
  const version = Number(formData.get("version"));
  const quantity = Number(formData.get("quantity"));
  if (!itemId || !Number.isFinite(version) || !Number.isFinite(quantity)) {
    return { ok: false, message: "Invalid request." };
  }
  const result = await cartApi.updateItemQuantity(itemId, quantity, version);
  revalidatePath("/cart");
  return { ok: result.ok, message: result.message };
}

export async function removeItemAction(
  _prevState: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const itemId = String(formData.get("item_id"));
  const version = Number(formData.get("version"));
  const result = await cartApi.removeItem(itemId, version);
  revalidatePath("/cart");
  return { ok: result.ok, message: result.message };
}

export async function clearCartAction(
  _prevState: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const version = Number(formData.get("version"));
  const result = await cartApi.clearCart(version);
  revalidatePath("/cart");
  return { ok: result.ok, message: result.message };
}

export async function saveForLaterAction(
  _prevState: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const itemId = String(formData.get("item_id"));
  const version = Number(formData.get("version"));
  const result = await cartApi.saveForLater(itemId, version);
  revalidatePath("/cart");
  return { ok: result.ok, message: result.message };
}

export async function moveToCartAction(
  _prevState: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const itemId = String(formData.get("item_id"));
  const version = Number(formData.get("version"));
  const result = await cartApi.moveSavedToCart(itemId, version);
  revalidatePath("/cart");
  return { ok: result.ok, message: result.message };
}

export async function deleteSavedItemAction(
  _prevState: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const itemId = String(formData.get("item_id"));
  const version = Number(formData.get("version"));
  const result = await cartApi.deleteSavedItem(itemId, version);
  revalidatePath("/cart");
  return { ok: result.ok, message: result.message };
}
