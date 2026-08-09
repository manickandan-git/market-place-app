# Guardrails — known gaps and recommendations

Findings from a review of `app/agent/loop.py`, `app/routes/chat.py`,
`app/tools/`, and `app/clients.py` as of the chat endpoint's first working
version. This is the punch list, not a changelog — items are marked done
below as they're fixed, but read the code, not this file, for current
behavior. Two things were already solid from the start and never needed
work: correlation IDs propagate from `ToolContext.request_id` into every
downstream tool call's `X-Request-ID` header (`app/clients.py`), and the
Anthropic API key never reaches the browser — `apps/web`'s `ChatWidget`
calls a server action, not the Anthropic API directly.

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

## 4. No bound on request size

`chat.py` reads `messages = body.get("messages", [])` and passes it into
`run_agent_loop` as-is — no cap on the number of messages or on
per-message length before it's sent to Claude. A single request can send
an arbitrarily large history.

**Recommendation:** cap message count (e.g. keep only the last N turns) and
per-message character length, rejecting or truncating oversized requests
before the Anthropic call.

## 5. Raw exception text leaks into model context

`run_single_tool`'s fallback handler in `loop.py`
(`except Exception as system_err: ... content: f"RuntimeError: Internal
agent failure. {str(system_err)}"`) puts the raw exception string into the
conversation history that Claude reasons over — and Claude may echo
fragments of it back to the user. This can leak internal detail (stack
trace fragments, internal hostnames/paths) depending on what the exception
contains.

**Recommendation:** log the real exception server-side (with
`context.request_id` for correlation) and return a generic, sanitized
message as the tool result instead of `str(system_err)`.

## 6. No wall-clock timeout on the whole request

`max_loops=5` bounds the number of tool-call iterations, but nothing bounds
total request time — a slow Anthropic response or a hanging downstream
tool call can tie up a FastAPI worker indefinitely.

**Recommendation:** wrap the call to `run_agent_loop` in
`asyncio.wait_for(...)` with a ceiling in the same spirit as
`DOWNSTREAM_TIMEOUT_SECONDS` used elsewhere in this service's config.

## Priority order

~~1 and 2 together (one system-prompt change covers both, cheapest fix for
the actual safety boundary)~~ → ~~3 (cost control, matters most once this
is exposed beyond localhost)~~ → 4, 5, 6 remaining.
