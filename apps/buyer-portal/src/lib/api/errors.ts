/**
 * Two different error shapes can come back through the gateway, and both
 * need to render sensibly in the UI:
 *
 * - The gateway's own rejections (404 not_found, 401 invalid_token, 503
 *   circuit_open, ...) use `{ error: { code, message, request_id } }` —
 *   see services/api-gateway/app/exceptions.py.
 * - Everything proxied through to a service uses plain FastAPI shapes:
 *   `{ detail: "some message" }` for a raised HTTPException, or
 *   `{ detail: [{ loc, msg, type }, ...] }` for a 422 validation error.
 */
export function extractErrorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const record = error as Record<string, unknown>;

    if (
      "error" in record &&
      record.error &&
      typeof record.error === "object" &&
      "message" in (record.error as Record<string, unknown>)
    ) {
      const message = (record.error as Record<string, unknown>).message;
      if (typeof message === "string") {
        return message;
      }
    }

    if ("detail" in record) {
      const detail = record.detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail)) {
        const messages = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as Record<string, unknown>).msg)
              : null,
          )
          .filter((message): message is string => Boolean(message));
        if (messages.length > 0) {
          return messages.join("; ");
        }
      }
    }
  }
  return "Something went wrong. Please try again.";
}

/** Per-field messages from a 422 validation error, keyed by field name (last `loc` segment). */
export function extractFieldErrors(error: unknown): Record<string, string> {
  const fieldErrors: Record<string, string> = {};
  if (
    error &&
    typeof error === "object" &&
    "detail" in error &&
    Array.isArray((error as Record<string, unknown>).detail)
  ) {
    for (const item of (error as { detail: unknown[] }).detail) {
      if (
        item &&
        typeof item === "object" &&
        "loc" in item &&
        "msg" in item &&
        Array.isArray((item as Record<string, unknown>).loc)
      ) {
        const loc = (item as { loc: unknown[] }).loc;
        const field = String(loc[loc.length - 1]);
        fieldErrors[field] = String((item as Record<string, unknown>).msg);
      }
    }
  }
  return fieldErrors;
}
