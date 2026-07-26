from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from app.models import ProviderType
from app.providers.base import (
    EmailMessage,
    EmailProvider,
    PermanentProviderError,
    ProviderResult,
)

logger = logging.getLogger(__name__)


class ConsoleEmailProvider(EmailProvider):
    """
    Development email provider.

    Instead of sending email through an external mail server, this provider
    writes the complete rendered message to application or Celery worker logs.

    Use this provider for:

    - local development
    - automated tests
    - template verification
    - integration testing
    """

    provider_type = ProviderType.CONSOLE

    def __init__(
        self,
        *,
        include_html_body: bool = True,
        include_text_body: bool = True,
        include_metadata: bool = True,
    ) -> None:
        self.include_html_body = include_html_body
        self.include_text_body = include_text_body
        self.include_metadata = include_metadata

    def send(self, message: EmailMessage) -> ProviderResult:
        """
        Log the email and return a simulated successful delivery result.
        """

        started_at = time.perf_counter()

        try:
            self.validate_message(message)
        except ValueError as exc:
            raise PermanentProviderError(
                str(exc),
                response_code="INVALID_MESSAGE",
            ) from exc

        provider_message_id = f"console-{uuid.uuid4()}"

        log_payload: dict[str, Any] = {
            "provider": self.provider_type.value,
            "provider_message_id": provider_message_id,
            "recipient": self._format_address(
                message.recipient_email,
                message.recipient_name,
            ),
            "sender": self._format_address(
                message.sender_email,
                message.sender_name,
            ),
            "reply_to": message.reply_to_email,
            "subject": message.subject,
            "headers": message.headers,
        }

        if self.include_text_body:
            log_payload["body_text"] = message.body_text

        if self.include_html_body:
            log_payload["body_html"] = message.body_html

        if self.include_metadata:
            log_payload["metadata"] = message.metadata

        logger.info(
            "Console email delivered:\n%s",
            json.dumps(
                log_payload,
                indent=2,
                default=str,
                ensure_ascii=False,
            ),
        )

        latency_ms = int(
            (time.perf_counter() - started_at) * 1000
        )

        return ProviderResult(
            success=True,
            provider=self.provider_type,
            provider_message_id=provider_message_id,
            response_code="CONSOLE_ACCEPTED",
            response_message=(
                "Email was written to the application logs"
            ),
            latency_ms=latency_ms,
            metadata={
                "delivery_mode": "console",
            },
        )

    def health_check(self) -> bool:
        """
        The console provider is always available when logging is configured.
        """

        return True

    @staticmethod
    def _format_address(
        email: str,
        name: str | None,
    ) -> str:
        """
        Format a display name and email address for readable logs.
        """

        if name:
            return f"{name} <{email}>"

        return email