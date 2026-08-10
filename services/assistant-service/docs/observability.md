# Observability — starting plan

Scoped to assistant-service only (the chat/agent loop), not a platform-wide
observability effort. Nothing below is implemented yet — this is a plan to
pick up, not a changelog. Two things are true of the whole platform right
now and worth remembering while planning: there is no logging, metrics, or
tracing infrastructure anywhere in this repo (no Prometheus,
OpenTelemetry, Sentry, log aggregation — checked), and only
`auth-service`/`notification-service` use plain `logging` at all.
assistant-service's own first (and only) use of `logging` is the exception
handler added for guardrails finding #5
(`app/agent/loop.py::run_single_tool`).

## The biggest blind spot: Anthropic token usage is invisible

Every `anthropic_client.messages.create(...)` call (`app/agent/loop.py`,
two call sites) returns a `response.usage` field (input/output token
counts) that the code never reads. After adding rate limiting specifically
to control Anthropic spend (guardrails #3), there's still no actual
visibility into what that spend *is* — no way to answer "how many tokens
did this conversation cost" or "what's our daily Anthropic spend" today.
This is the natural starting point.

## What to instrument, in rough priority order

1. **Token usage per Anthropic call.** Log `response.usage.input_tokens` /
   `output_tokens` from both `messages.create()` call sites in `loop.py`,
   tagged with `request_id`. Cheapest, highest-value — closes the blind
   spot above directly.
2. **Per-request outcome.** One log line per completed `/chat` request:
   `request_id`, authenticated y/n, number of loop iterations used, which
   tools were called and whether each succeeded, `stop_reason`, total
   latency, total token counts. Nothing currently logs a normal
   *successful* request at all — only the unexpected-exception path (#5)
   logs anything today.
3. **Tool-level detail.** Success/error rate per tool name, latency per
   downstream HTTP call (`app/clients.py`), and how often `max_loops` gets
   exhausted (the forced-final-turn path in `loop.py`) — that's a direct
   signal the agent is struggling to resolve a request within budget.
4. **Rate-limit visibility.** How often `ChatRateLimitMiddleware` actually
   returns `429`, and to which key (token vs IP). This would let us
   confirm whether guardrails finding E (the shared-bucket bug for
   anonymous traffic behind the gateway) is a live problem in practice or
   still theoretical — right now there's no way to tell.
5. **`ServiceError` visibility.** Downstream failures (`app/clients.py`
   raising `ServiceError`) are currently only surfaced as a `tool_result`
   string back to Claude — never logged. Worth logging these too; they're
   invisible today even though they're a distinct, already-handled failure
   path from the unexpected-exception one #5 covers.

## What to deliberately not log

Given the guardrails #7 PII work (`app/tools/_order_utils.py`'s
`summarize_order()`), the same discipline applies to logs: log metadata
(tool names, counts, latencies, outcomes, token counts), never raw message
content or full tool-result payloads. A log line that includes the actual
conversation text or an order's `shipping_address` defeats the point of
having trimmed it out of the Anthropic-facing payload in the first place.

## Recommended starting point

Structured `logging` output (stdlib, same minimal pattern #5 already
introduced — no new dependency), one log line per completed `/chat`
request carrying the fields from item 2 above, plus item 1's token counts
folded in.

**Tradeoff to go in eyes-open:** this gets per-request debugging (grep logs
by `request_id`) cheaply, but not trends, dashboards, or alerting. Real
cost/latency trend visibility eventually needs somewhere to ship logs to
and query them — the platform has no log aggregation or metrics
infrastructure anywhere today, so that's a bigger, platform-level decision
that shouldn't be folded into this service alone. Start with stdlib
logging here; revisit shipping logs somewhere once (or if) the platform
adopts a convention for it.

## Open question for next session

Log format: plain stdlib text logs (matches #5, zero new dependencies) vs.
structured JSON logs (easier to grep/parse `request_id` and fields out of,
slightly more setup — a formatter, not a new dependency either). Worth
deciding before writing the first log line, since changing format later
means touching every call site again.
