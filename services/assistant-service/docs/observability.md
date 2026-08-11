# Observability

Scoped to assistant-service only (the chat/agent loop), not a platform-wide
observability effort. **The plan below has been implemented** — this doc now
records what shipped and why, not a plan to pick up. Two things are still
true of the rest of the platform: there is no shared logging/metrics/tracing
convention repo-wide (no Prometheus, OpenTelemetry, Sentry — checked), and
this Loki/Promtail/Grafana stack is wired up for assistant-service only.

## What shipped

- **Structured JSON log lines**, one call per event via
  `app/event_logger.py`'s `log_event(logger, event, **fields)` — plain
  stdlib `logging`, no new dependency, emitted through each call site's own
  logger so the module name stays accurate. Three event types:
  - `chat_request` (`app/routes/chat.py`) — one line per completed or timed-out
    `/chat` call: `request_id`, `authenticated`, `outcome`
    (`completed`/`timeout`), `loop_iterations`, `forced_final_turn`,
    `tool_calls`, `stop_reason`, `latency_ms`, `input_tokens`,
    `output_tokens`. Closes the original "no visibility into Anthropic
    spend" blind spot directly — `response.usage` is read at both
    `messages.create()` call sites in `app/agent/loop.py` and threaded back
    through `AgentStats`.
  - `downstream_call` (`app/clients.py`'s `_log_downstream()`, called from
    every product/inventory/order/cart client method, success or failure) —
    `service`, `operation`, `status_code` (`None` on a connection-level
    `httpx.RequestError`), `duration_ms`, `request_id`. Covers both
    tool-level latency/error-rate and `ServiceError` visibility — a failed
    downstream call is logged here even though it only reaches Claude as a
    `tool_result` string.
  - `chat_rate_limited` (`app/middleware/rate_limit.py`) — logged on every
    `429`, with `key_type` (`token` or `ip` — never the raw key itself, which
    could be a bearer token) and `retry_after`, so guardrails finding E
    (anonymous-caller bucket sharing) is now something you can confirm from
    logs instead of reasoning about in the abstract.
- **Loki + Promtail + Grafana** (`docker-compose.yml`, dev-only, profile
  section "23. Observability stack"): Promtail tails every container's
  stdout/stderr via Docker service discovery, ships to Loki, Grafana
  queries it. Config lives in `infrastructure/monitoirng/` (`loki-config.yaml`,
  `promtail-config.yaml`, `grafana-datasources.yaml`,
  `grafana-dashboards.yaml`, `dashboards/`).
- **Dashboard**: `infrastructure/monitoirng/dashboards/assistant-service-observability.json`
  ("Assistant Service - Observability"), auto-provisioned. Panels: chat
  requests/min, chat request latency (avg ms), chat requests by
  `stop_reason`, Anthropic token usage/min, downstream call latency by
  service (avg ms), downstream calls by status code, chat rate-limit
  hits (429s)/min, and a raw event-log panel over all three event types.

## What to deliberately not log

Given the guardrails #7 PII work (`app/tools/_order_utils.py`'s
`summarize_order()`), the same discipline applies to logs: log metadata
(tool names, counts, latencies, outcomes, token counts), never raw message
content or full tool-result payloads. None of the three event types above
carry conversation text or a raw order payload — this was verified while
implementing, not just intended.

## Known gaps

- **No alerting.** Grafana visualizes the metrics above but nothing pages
  or notifies on them (e.g. a spike in 429s or `stop_reason: max_tokens`
  going unusually high). Dashboards only help if someone is looking.
- **No cost/spend rollup.** Token counts are logged and graphed per-minute,
  but there's no daily/monthly aggregate spend view — would need either a
  Grafana panel with a longer window and a $/token conversion, or a
  separate scheduled job.
- **Dev-only stack.** The Loki/Promtail/Grafana containers are part of the
  default `docker-compose.yml`, not gated behind a `--profile`, but nothing
  about the setup (retention, auth, resource limits) has been evaluated for
  a non-local environment.
