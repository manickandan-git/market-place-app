import "server-only";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Cart = components["schemas"]["cart_CartResponse"];
export type CartItem = components["schemas"]["cart_CartItemResponse"];
export type CheckoutReadiness =
  components["schemas"]["cart_CheckoutReadinessResponse"];

export interface CartResult {
  ok: boolean;
  cart?: Cart;
  message?: string;
  /** True on a 409 If-Match-Version conflict: caller should refetch and
   * show a "your cart changed" message rather than silently retrying —
   * see docs/route-allowlist.md's parent conversation on why the gateway
   * itself never blindly retries non-idempotent calls; the same
   * discipline applies here. */
  versionConflict?: boolean;
}

// authMiddleware (lib/api/client.ts) already attaches X-Cart-Token from
// the mp_cart_token cookie to every request — callers here only need to
// pass If-Match-Version, which is per-call, not a static session value.

function toCartResult(
  data: Cart | undefined,
  error: unknown,
  response: Response,
): CartResult {
  if (error) {
    return {
      ok: false,
      versionConflict: response.status === 409,
      message:
        response.status === 409
          ? "Your cart changed since this page loaded. Please refresh."
          : "Something went wrong updating your cart.",
    };
  }
  return { ok: true, cart: data };
}

export async function getCart(): Promise<Cart | null> {
  const { data, error } = await apiClient.GET("/api/v1/cart");
  if (error) {
    return null;
  }
  return data;
}

export async function createGuestCart(): Promise<{
  cartToken: string;
  cart: Cart;
} | null> {
  const { data, error } = await apiClient.POST("/api/v1/guest-carts");
  if (error) {
    return null;
  }
  return { cartToken: data.cart_token, cart: data.cart };
}

/**
 * `version` is the cart's *current* version, required even though the
 * generated OpenAPI schema marks `If-Match-Version` optional for this
 * route — confirmed by hitting the real endpoint: cart-service's
 * `required_version` dependency (app/dependencies/headers.py) enforces it
 * at runtime and 428s without it, a gap between the raw `Header()` type
 * annotation (which is what openapi-typescript sees) and the dependency
 * function's own validation. Same requirement as every other cart
 * mutation.
 */
export async function addItem(
  productId: string,
  variantId: string,
  quantity: number,
  version: number,
): Promise<CartResult> {
  const { data, error, response } = await apiClient.POST("/api/v1/cart/items", {
    params: { header: { "If-Match-Version": version } },
    body: { product_id: productId, variant_id: variantId, quantity },
  });
  return toCartResult(data, error, response);
}

export async function updateItemQuantity(
  itemId: string,
  quantity: number,
  version: number,
): Promise<CartResult> {
  const { data, error, response } = await apiClient.PATCH(
    "/api/v1/cart/items/{item_id}",
    {
      params: {
        path: { item_id: itemId },
        header: { "If-Match-Version": version },
      },
      body: { quantity },
    },
  );
  return toCartResult(data, error, response);
}

export async function removeItem(
  itemId: string,
  version: number,
): Promise<CartResult> {
  const { data, error, response } = await apiClient.DELETE(
    "/api/v1/cart/items/{item_id}",
    {
      params: {
        path: { item_id: itemId },
        header: { "If-Match-Version": version },
      },
    },
  );
  return toCartResult(data, error, response);
}

export async function clearCart(version: number): Promise<CartResult> {
  const { data, error, response } = await apiClient.DELETE("/api/v1/cart", {
    params: { header: { "If-Match-Version": version } },
  });
  return toCartResult(data, error, response);
}

export async function saveForLater(
  itemId: string,
  version: number,
): Promise<CartResult> {
  const { data, error, response } = await apiClient.POST(
    "/api/v1/cart/items/{item_id}/save-for-later",
    { params: { path: { item_id: itemId }, header: { "If-Match-Version": version } } },
  );
  return toCartResult(data, error, response);
}

export async function moveSavedToCart(
  itemId: string,
  version: number,
): Promise<CartResult> {
  const { data, error, response } = await apiClient.POST(
    "/api/v1/cart/saved-items/{item_id}/move-to-cart",
    { params: { path: { item_id: itemId }, header: { "If-Match-Version": version } } },
  );
  return toCartResult(data, error, response);
}

export async function deleteSavedItem(
  itemId: string,
  version: number,
): Promise<CartResult> {
  const { data, error, response } = await apiClient.DELETE(
    "/api/v1/cart/saved-items/{item_id}",
    { params: { path: { item_id: itemId }, header: { "If-Match-Version": version } } },
  );
  return toCartResult(data, error, response);
}

/** Only callable once authenticated — cart-service requires a user JWT for merge. */
export async function mergeGuestCart(guestCartToken: string): Promise<CartResult> {
  const { data, error, response } = await apiClient.POST("/api/v1/cart/merge", {
    body: { guest_cart_token: guestCartToken },
  });
  return toCartResult(data, error, response);
}

export async function checkReadiness(): Promise<CheckoutReadiness | null> {
  const { data, error } = await apiClient.POST("/api/v1/cart/readiness");
  if (error) {
    return null;
  }
  return data;
}
