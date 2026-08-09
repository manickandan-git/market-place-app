# Guardrails — known gaps and recommendations

Findings from a review of `app/agent/loop.py`, `app/routes/chat.py`,
`app/tools/`, and `app/clients.py` as of the chat endpoint's first working
version. Nothing below is implemented yet — this is the punch list, not a
changelog. Two things are already solid and don't need work: correlation IDs
propagate from `ToolContext.request_id` into every downstream tool call's
`X-Request-ID` header (`app/clients.py`), and the Anthropic API key never
reaches the browser — `apps/web`'s `ChatWidget` calls a server action, not
the Anthropic API directly.

## 1. No system prompt

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

## 2. Prompt-injection surface via tool results

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

## 3. No rate limiting on `/chat`

`app/routes/chat.py`'s `chat_endpoint` accepts an optional, unverified
Bearer token (`access_token` is extracted but never validated against
JWKS — auth enforcement happens downstream, per-tool, in the service that
tool calls). This is intentional: per the README, `/api/v1/assistant/*` is
allowlisted PUBLIC at the gateway because guests must be able to search the
catalog and ask policy questions without signing in. But that same
openness means anyone, signed in or not, can call `/chat` repeatedly with
no throttle anywhere in `app/middleware/` — there's no cap on Anthropic
spend per caller.

**Recommendation:** add a rate limit (e.g. Redis-backed, keyed by IP for
anonymous callers and by subject claim for authenticated ones) ahead of the
agent loop. Being public-by-design doesn't mean unthrottled.

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

1 and 2 together (one system-prompt change covers both, cheapest fix for
the actual safety boundary) → 3 (cost control, matters most once this is
exposed beyond localhost) → 4, 5, 6.
