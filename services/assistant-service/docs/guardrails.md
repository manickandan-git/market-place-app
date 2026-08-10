# Guardrails — known gaps and recommendations

Findings from a review of `app/agent/loop.py`, `app/routes/chat.py`,
`app/tools/`, and `app/clients.py` as of the chat endpoint's first working
version. This is the punch list, not a changelog — items are marked done
below as they're fixed, but read the code, not this file, for current
behavior. Several things were already solid from the start and never
needed work:
- Correlation IDs propagate from `ToolContext.request_id` into every
  downstream tool call's `X-Request-ID` header (`app/clients.py`).
- The Anthropic API key never reaches the browser — `apps/web`'s
  `ChatWidget` calls a server action, not the Anthropic API directly.
- No PII is ever logged or persisted — the only `print()` in the service is
  a one-time seed script, and assistant-service's own DB holds pgvector
  policy chunks only, never order/cart/user data.
- Writes are always scoped to the real caller. `add_to_cart` (the only
  write tool) acts on `context.access_token`, which comes from *this
  request's* actual `Authorization` header — not from anything in the
  client-supplied message body. Even a forged conversation history (see
  #8) can't redirect a write to someone else's account.

## Category map

|  | Input & Prompt Controls | Data Access & Privacy | Output & Content Moderation | Action & Tool Boundaries |
|---|---|---|---|---|
| Fixed | #1, #2, #3, #4, #8 | #7 | #5 | #6, #9 |
| Open | | | | |

All nine original findings are fixed as of this revision. New findings
surfacing since (from the code-review pass after #4-#9 landed) are tracked
below the numbered list, not renumbered into it.

## 1. No system prompt — **fixed**

`app/agent/loop.py`'s two `anthropic_client.messages.create(...)` calls
(the main loop iteration and the forced final turn after `max_loops`) pass
only `tools` and the raw message history — no `system` parameter exists
anywhere in the file. There is currently nothing that:
- scopes the assistant to marketplace shopping tasks,
- tells it to decline unrelated requests,
- forbids fabricating product/order data that didn't come from a tool
  result.

**Recommendation:** add a `system` prompt to both `messages.create()` calls
that states the assistant's scope (buyer-facing marketplace shopping
assistant only), instructs it to answer only from tool results (never
invent price/stock/order data), and to decline off-topic requests. This is
the actual behavior boundary for the feature and doesn't exist yet — treat
as highest priority.

## 2. Prompt-injection surface via tool results — **fixed**

Tool outputs are seller-controlled data (product names/descriptions from
`search_products`, `get_product`, etc.) but get fed straight back into the
conversation as trusted content: `loop.py`'s tool-result turn
(`messages.append({"role": "user", "content": tool_results_content})`)
carries whatever `json.dumps(result_dict, default=str)` produced, with no
distinction between "data" and "instructions." A seller could embed text in
a product description designed to redirect the assistant's behavior when
that product surfaces in a search result.

**Recommendation:** fold into the same system-prompt change as #1 — state
explicitly that `tool_result` content is untrusted data returned by an API,
never instructions, and the assistant must not follow directives found
inside it.

## 3. No rate limiting on `/chat` — **fixed**

`app/routes/chat.py`'s `chat_endpoint` accepts an optional, unverified
Bearer token (`access_token` is extracted but never validated against
JWKS — auth enforcement happens downstream, per-tool, in the service that
tool calls). This is intentional: per the README, `/api/v1/assistant/*` is
allowlisted PUBLIC at the gateway because guests must be able to search the
catalog and ask policy questions without signing in. But that same
openness meant anyone, signed in or not, could call `/chat` repeatedly with
no throttle — there was no cap on Anthropic spend per caller.

**Fix:** `app/middleware/rate_limit.py`'s `ChatRateLimitMiddleware`, scoped
to `POST {api_prefix}/assistant/chat` only. In-memory sliding window keyed
by the raw bearer token when present, else client IP — this service never
verifies JWTs itself (every tool either relays the buyer's own token or is
an unauthenticated public read), so an unverified token string is still
enough to distinguish one caller from another for throttling. Defaults to
20 requests / 60s (`CHAT_RATE_LIMIT_REQUESTS` /
`CHAT_RATE_LIMIT_WINDOW_SECONDS` in `app/config.py`), returns `429` with a
`Retry-After` header once exceeded.

In-memory only — correct for the single-worker/single-replica deployment
this service currently runs as. **If assistant-service is ever scaled to
multiple workers or replicas, this needs a shared store (Redis) instead**,
since each process would otherwise enforce its own independent limit,
multiplying the effective cap by the replica count.

## 4. No bound on request size — **fixed**

`chat.py` read `messages = body.get("messages", [])` and passed it into
`run_agent_loop` as-is — no cap on the number of messages or on
per-message length before it was sent to Claude. A single request could
send an arbitrarily large history.

**Fix:** `chat.py`'s `ChatRequest`/`ChatMessageIn` Pydantic models —
`messages: list[ChatMessageIn] = Field(min_length=1, max_length=40)` and
`content: str = Field(max_length=4000)` per message. Oversized or malformed
requests now get FastAPI's standard `422` instead of reaching the Anthropic
call. See the new finding below about the frontend not pruning its own
history to match this cap.

## 5. Raw exception text leaks into model context — **fixed**

`run_single_tool`'s fallback handler in `loop.py`
(`except Exception as system_err: ... content: f"RuntimeError: Internal
agent failure. {str(system_err)}"`) put the raw exception string into the
conversation history that Claude reasons over — and Claude could echo
fragments of it back to the user.

**Fix:** the handler now calls `logger.exception(...)` (with
`context.request_id` for correlation) and returns a generic, sanitized
tool-result message instead of `str(system_err)`. This is the first use of
`logging` anywhere in this service.

## 6. No wall-clock timeout on the whole request — **fixed**

`max_loops=5` bounds the number of tool-call iterations, but nothing bounded
total request time — a slow Anthropic response or a hanging downstream
tool call could tie up a FastAPI worker indefinitely.

**Fix:** `chat.py` wraps the `run_agent_loop` call in
`asyncio.wait_for(..., timeout=settings.chat_request_timeout_seconds)`
(default 45s), returning `504` on timeout. See the new finding below about
this cancelling a non-idempotent write mid-flight.

## 7. Order PII forwarded to Anthropic unfiltered — **fixed**

`app/clients.py`'s `OrderClient.get_order()` (line 153) and
`get_my_orders()` (line 125) return `response.json()` as-is from
order-service. Order-service's `OrderResponse` schema
(`services/order-service/app/schemas.py:49-70`) includes full
`shipping_address` and `billing_address` dicts (name, street, phone,
etc.). `get_order_status.py:24` and `get_my_orders.py:22-24` forward that
whole object as the tool result, so the full address block goes to
Anthropic's API on every order-status question — even ones that only need
status/items/dates.

This is the buyer's own data, read with their own JWT, and nothing logs or
persists it (see the list at the top of this doc) — so it's not an
unauthorized-access issue, but it is more third-party exposure than most
questions need.

**Fix:** `app/tools/_order_utils.py`'s `summarize_order()`, used by both
`get_order_status.py` and `get_my_orders.py`. Keeps only
`id`/`order_number`/`status`/`payment_status`/`currency_code`/the four
total fields/`shipping_address`/`items`/`created_at`/`updated_at`; drops
`billing_address`, `payment_reference`, `reservation_group_id`, and
`cancellation_reason`. Not a code fix, but still open: confirming
Anthropic's account-level data-retention/training settings are configured
appropriately, given customer PII (shipping address) still flows through
this path.

## 8. No schema validation on the incoming `messages` array — **fixed**

`chat.py`'s `chat_endpoint` did `messages = body.get("messages", [])` with
no shape validation, then passed it straight into `run_agent_loop` and from
there into Anthropic's `messages` parameter as-is. Anyone calling `/chat`
directly (bypassing `ChatWidget`) could submit arbitrary `role`/`content`
structures, including fabricated `assistant` turns or forged `tool_result`
blocks claiming to be prior tool output.

**Fix:** the `ChatRequest`/`ChatMessageIn` Pydantic models from #4 also
close this — `role` is constrained to `Literal["user", "assistant"]` and
`content` to `str`, so the client can no longer submit content-block
structures (`tool_use`/`tool_result`) at all. Note this was never usable to
redirect a *write*: `add_to_cart` always uses the real request's own
`access_token`, never anything from the message body — the risk was
steering the assistant's stated behavior/tone, not hijacking an action.

## 9. No per-request cap on write-tool invocations — **fixed**

`run_single_tool` calls execute concurrently via `asyncio.gather` for every
`tool_use` block Claude emits in a single turn. Nothing stopped Claude from
requesting `add_to_cart` multiple times within one turn — each call was
individually bounded (`quantity` capped 1-1000 in `AddToCartArgs`), but
nothing bounded the *count* of calls.

**Fix:** `ToolSpec.is_write` (`app/tools/types.py`), set `True` only on
`ADD_TO_CART`. `loop.py` now keeps only the first `is_write` tool call per
turn and returns a synthetic `is_error` tool_result for any additional ones
— every `tool_use` still gets a matching `tool_result` (Anthropic API
requirement), so extras aren't silently dropped. See the new finding below
about the rejection message being cart-specific text in an otherwise
generic mechanism.

## New findings (post #1-9, from code review)

Surfaced reviewing the #4-#9 diff. Not yet fixed.

**A. Reply extraction was broken by the #8 schema change — since fixed.**
`chat.py`'s reply-extraction generator used `block.get("type") == "text"`,
but `final_assistant_message["content"]` is a list of Anthropic SDK objects
(`TextBlock`, etc.), not dicts — no `.get()` method. This broke every
successful chat reply (`stop_reason != "tool_use"`, i.e. the common case)
with a `500`, confirmed live before the fix. Now reads `block.type`
(attribute access, matching `block.text` on the line above). No
`test_chat.py` exists — worth adding one so a regression like this fails
CI instead of only being caught by a live curl check.

**B. Non-idempotent write can double-apply if the #6 timeout fires
mid-flight.** `asyncio.wait_for` in `chat.py` cancels `run_agent_loop` on
timeout, including a downstream `add_to_cart` POST already in flight. The
buyer gets a `504`, but cart-service may have already applied it; a retry
has no idempotency key to prevent adding the item twice. Not fixed —
tradeoff between complexity (needs an idempotency key threaded through
cart-service's `add_item`) and how likely a `add_to_cart` call is to
actually approach the 45s ceiling.

**C. Frontend doesn't prune history to match the #4 server-side cap.**
`ChatRequest.messages` caps at 40, but `ChatWidget.tsx`'s `messages` state
grows unbounded and `chat.ts` resends the full history every turn. Past 40
messages, every subsequent call permanently `422`s, and `chat.ts`'s
`!response.ok` check collapses that into a generic "temporarily
unavailable" with no recovery path short of losing the conversation. Fix
belongs in `ChatWidget.tsx` (cap/window the messages sent) or `chat.ts`.

**D. Write-tool-cap rejection message is cart-specific.** `loop.py`'s
synthetic rejection for a capped write call is hardcoded to `"Only one
cart update is allowed per turn."`, but `ToolSpec.is_write` is meant to
gate any future write tool. Low severity today (only one write tool
exists) — worth generalizing the message (e.g. include the tool name) when
a second write tool is added.

**E. The #3 rate limit's "per-caller" claim doesn't hold for anonymous
traffic behind the gateway — it's effectively one shared bucket for every
guest.** `ChatRateLimitMiddleware._client_key()` falls back to
`request.client.host` when there's no bearer token. But api-gateway proxies
every request to assistant-service without forwarding the real client IP
(no `X-Forwarded-For` or equivalent — checked `services/api-gateway/app/services/routing.py`,
nothing sets it). So every anonymous request arriving through the gateway
— which is *all* signed-out `ChatWidget` traffic, the majority case for a
public storefront — carries the same `request.client.host`: the gateway
container's own docker-network IP. One heavy anonymous user (or a burst of
test/dev traffic through the gateway, which is how this was found) can
exhaust the shared 20-req/60s bucket and `429` every *other* guest at the
same time, not just themselves.

Reproduced live: a burst of test calls through the gateway (`:9000`)
during this session's manual testing caused a real browser
`ChatWidget` click to `429` moments later, surfaced to the user as the
generic "The assistant is temporarily unavailable." (`chat.ts`'s
`!response.ok` branch doesn't distinguish `429` from any other failure).
Confirmed by waiting for the 60s window to roll over — requests succeeded
again immediately after, with no code change.

**Not fixed yet — candidate approaches, to weigh before picking one:**
1. Have api-gateway set `X-Forwarded-For` (or similar) on proxied requests,
   and have `_client_key()` prefer that header when present. Most correct,
   but touches api-gateway too, not just this service.
2. Key anonymous traffic by something gateway-visible instead of IP — e.g.
   a per-browser-session identifier the frontend generates and sends as a
   header/cookie. No gateway change needed, but adds client-side state.
3. Accept the shared-bucket behavior for anonymous traffic as an
   intentional simplification (it still caps total anonymous spend
   server-wide, just not per-guest) and raise the limit/window instead of
   trying to distinguish individual guests. Cheapest, but weakest.

Needs a test (`test_rate_limit.py` doesn't exist yet) covering: two
different bearer tokens each get their own bucket (already true today);
two anonymous requests through a simulated proxy without a distinguishing
header share one bucket (the bug, to guard against regressing further, or
to prove fixed once one of the approaches above lands).

## Priority order

All of #1-9 are fixed. Of the new findings: A is fixed (was the most
severe — broke the whole feature); C and E are the next real user-facing
gaps (C: silent permanent breakage past 40 messages; E: anonymous users
can rate-limit each other) — both worth doing before this is exposed
beyond localhost; B and D are lower urgency design tradeoffs.
