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

// Must match assistant-service's ChatRequest.messages max_length
// (services/assistant-service/app/routes/chat.py). ChatWidget's own
// `messages` state is never trimmed — this only bounds what's sent over
// the wire, so the visible conversation never loses history, only what
// the model re-reads on later turns.
const MAX_HISTORY_MESSAGES = 40;

function windowHistory(messages: ChatMessage[]): ChatMessage[] {
  // Turns strictly alternate user/assistant starting with "user" (a
  // Messages API requirement — see ChatWidget's comment on why the
  // greeting bubble is never included). Trim from the front two at a
  // time (one full user+assistant pair) so a window never starts on an
  // "assistant" turn, which a plain tail slice could produce depending
  // on parity.
  let windowed = messages;
  while (windowed.length > MAX_HISTORY_MESSAGES) {
    windowed = windowed.slice(2);
  }
  return windowed;
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
      body: JSON.stringify({ messages: windowHistory(messages) }),
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
