"use server";

import { revalidatePath } from "next/cache";

import { config } from "@/lib/config";
import { getAccessToken } from "@/lib/session";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatActionResult {
  ok: boolean;
  reply?: string;
  error?: string;
}

/**
 * Calls assistant-service's chat endpoint through the gateway, attaching the
 * buyer's bearer token server-side when signed in — guests get no
 * Authorization header at all, and assistant-service's tools soft-gate on
 * that themselves (e.g. "sign in to check your orders") rather than
 * rejecting the request. Not wired through the generated `apiClient`
 * (lib/api/*.ts + schema.d.ts): assistant-service isn't in the gateway's
 * OpenAPI aggregator yet (services/api-gateway/app/services/
 * openapi_aggregator.py's SERVICE_BASE_URL_SETTINGS doesn't list it), so
 * there's no generated type for this path to build against.
 *
 * The endpoint is stateless — the full message history, including the new
 * user turn, must be resent on every call; there is no server-side session.
 */
export async function sendChatMessageAction(
  messages: ChatMessage[],
): Promise<ChatActionResult> {
  const accessToken = await getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(`${config.gatewayUrl}/api/v1/assistant/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({ messages }),
    });
  } catch {
    return { ok: false, error: "Could not reach the assistant right now." };
  }

  if (!response.ok) {
    return { ok: false, error: "The assistant is temporarily unavailable." };
  }

  const data = (await response.json()) as { response: string };

  // The assistant's add_to_cart tool may have just changed the buyer's
  // cart. Revalidate unconditionally — the response doesn't say which
  // tools ran, and this is cheap. The header badge (SiteHeader) lives in
  // the root layout, a separate cache segment from /cart, so both calls
  // are needed.
  revalidatePath("/cart");
  revalidatePath("/", "layout");

  return { ok: true, reply: data.response };
}
