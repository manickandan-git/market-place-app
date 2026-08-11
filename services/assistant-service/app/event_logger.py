import json
import logging


def log_event(target_logger: logging.Logger, event: str, **fields) -> None:
    """Logs one structured JSON line: {"event": event, ...fields}.

    Takes the caller's own logger (not a module-level singleton here) so the
    emitted record keeps its real module name (e.g. "app.routes.chat"),
    matching every other logger in this service — see
    docs/observability.md's "what to deliberately not log": fields only,
    never message content or tool results.
    """
    target_logger.info(json.dumps({"event": event, **fields}))
