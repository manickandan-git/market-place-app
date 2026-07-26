from __future__ import annotations

import smtplib
import socket
import ssl
import time
from email.message import EmailMessage as MimeEmailMessage
from email.utils import formataddr, make_msgid

from app.config import get_settings
from app.models import ProviderType
from app.providers.base import (
    EmailMessage,
    EmailProvider,
    PermanentProviderError,
    ProviderResult,
    RetryableProviderError,
)

settings = get_settings()


class SMTPEmailProvider(EmailProvider):
    """
    SMTP email provider.

    Supports:

    - plain-text email
    - HTML email
    - multipart alternative email
    - SMTP over SSL
    - STARTTLS
    - optional authentication
    - custom headers
    - provider-neutral result handling
    """

    provider_type = ProviderType.SMTP

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool | None = None,
        use_ssl: bool | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.host = host or settings.smtp_host
        self.port = port or settings.smtp_port

        self.username = (
            username
            if username is not None
            else settings.smtp_username
        )

        self.password = (
            password
            if password is not None
            else settings.smtp_password
        )

        self.use_tls = (
            use_tls
            if use_tls is not None
            else settings.smtp_use_tls
        )

        self.use_ssl = (
            use_ssl
            if use_ssl is not None
            else settings.smtp_use_ssl
        )

        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.smtp_timeout_seconds
        )

        self._validate_configuration()

    def send(self, message: EmailMessage) -> ProviderResult:
        """
        Send an email through SMTP.

        Temporary network and server failures raise RetryableProviderError.
        Permanent recipient and message failures raise PermanentProviderError.
        """

        started_at = time.perf_counter()

        try:
            self.validate_message(message)
        except ValueError as exc:
            raise PermanentProviderError(
                str(exc),
                response_code="INVALID_MESSAGE",
            ) from exc

        mime_message = self._build_mime_message(message)

        try:
            with self._create_client() as smtp_client:
                self._initialize_connection(smtp_client)

                refused_recipients = smtp_client.send_message(
                    mime_message,
                    from_addr=message.sender_email,
                    to_addrs=[message.recipient_email],
                )

            if refused_recipients:
                refusal = refused_recipients.get(
                    message.recipient_email
                )

                if refusal is None:
                    refusal = next(
                        iter(refused_recipients.values()),
                        None,
                    )

                code, response = self._parse_refusal(refusal)

                raise self._classify_smtp_error(
                    code=code,
                    message=response,
                )

        except smtplib.SMTPRecipientsRefused as exc:
            code, response = self._extract_recipient_refusal(
                exc,
                message.recipient_email,
            )

            raise self._classify_smtp_error(
                code=code,
                message=response,
            ) from exc

        except smtplib.SMTPSenderRefused as exc:
            raise PermanentProviderError(
                self._decode_response(exc.smtp_error),
                response_code=str(exc.smtp_code),
            ) from exc

        except smtplib.SMTPDataError as exc:
            raise self._classify_smtp_error(
                code=exc.smtp_code,
                message=self._decode_response(exc.smtp_error),
            ) from exc

        except smtplib.SMTPAuthenticationError as exc:
            raise PermanentProviderError(
                (
                    "SMTP authentication failed: "
                    f"{self._decode_response(exc.smtp_error)}"
                ),
                response_code=str(exc.smtp_code),
            ) from exc

        except smtplib.SMTPNotSupportedError as exc:
            raise PermanentProviderError(
                f"SMTP feature is not supported: {exc}",
                response_code="SMTP_NOT_SUPPORTED",
            ) from exc

        except smtplib.SMTPHeloError as exc:
            raise RetryableProviderError(
                f"SMTP server rejected HELO/EHLO: {exc}",
                response_code="SMTP_HELO_ERROR",
            ) from exc

        except smtplib.SMTPServerDisconnected as exc:
            raise RetryableProviderError(
                f"SMTP server disconnected unexpectedly: {exc}",
                response_code="SMTP_DISCONNECTED",
            ) from exc

        except smtplib.SMTPConnectError as exc:
            raise RetryableProviderError(
                (
                    "Unable to connect to SMTP server: "
                    f"{self._decode_response(exc.smtp_error)}"
                ),
                response_code=str(exc.smtp_code),
            ) from exc

        except (
            TimeoutError,
            socket.timeout,
            socket.gaierror,
            ConnectionError,
            OSError,
        ) as exc:
            raise RetryableProviderError(
                f"SMTP network error: {exc}",
                response_code="SMTP_NETWORK_ERROR",
            ) from exc

        except smtplib.SMTPException as exc:
            raise RetryableProviderError(
                f"Unexpected SMTP failure: {exc}",
                response_code="SMTP_ERROR",
            ) from exc

        latency_ms = int(
            (time.perf_counter() - started_at) * 1000
        )

        return ProviderResult(
            success=True,
            provider=self.provider_type,
            provider_message_id=str(
                mime_message["Message-ID"]
            ),
            response_code="250",
            response_message="SMTP server accepted the message",
            latency_ms=latency_ms,
            metadata={
                "smtp_host": self.host,
                "smtp_port": self.port,
                "tls": self.use_tls,
                "ssl": self.use_ssl,
            },
        )

    def health_check(self) -> bool:
        """
        Verify that the SMTP server can be reached.

        This does not send an email.
        """

        try:
            with self._create_client() as smtp_client:
                self._initialize_connection(
                    smtp_client,
                    authenticate=False,
                )

                code, _ = smtp_client.noop()

                return 200 <= code < 400

        except Exception:
            return False

    def _validate_configuration(self) -> None:
        if not self.host.strip():
            raise ValueError("SMTP host is required")

        if not 1 <= self.port <= 65535:
            raise ValueError(
                "SMTP port must be between 1 and 65535"
            )

        if self.use_ssl and self.use_tls:
            raise ValueError(
                "SMTP_USE_SSL and SMTP_USE_TLS "
                "cannot both be enabled"
            )

        if self.username and not self.password:
            raise ValueError(
                "SMTP password is required when username is set"
            )

        if self.password and not self.username:
            raise ValueError(
                "SMTP username is required when password is set"
            )

    def _create_client(
        self,
    ) -> smtplib.SMTP | smtplib.SMTP_SSL:
        if self.use_ssl:
            ssl_context = ssl.create_default_context()

            return smtplib.SMTP_SSL(
                host=self.host,
                port=self.port,
                timeout=self.timeout_seconds,
                context=ssl_context,
            )

        return smtplib.SMTP(
            host=self.host,
            port=self.port,
            timeout=self.timeout_seconds,
        )

    def _initialize_connection(
        self,
        smtp_client: smtplib.SMTP | smtplib.SMTP_SSL,
        *,
        authenticate: bool = True,
    ) -> None:
        smtp_client.ehlo()

        if self.use_tls:
            ssl_context = ssl.create_default_context()

            smtp_client.starttls(
                context=ssl_context,
            )

            smtp_client.ehlo()

        if (
            authenticate
            and self.username
            and self.password
        ):
            smtp_client.login(
                self.username,
                self.password,
            )

    def _build_mime_message(
        self,
        message: EmailMessage,
    ) -> MimeEmailMessage:
        mime_message = MimeEmailMessage()

        mime_message["Message-ID"] = make_msgid(
            domain=self._message_id_domain(
                message.sender_email
            ),
        )

        mime_message["From"] = formataddr(
            (
                message.sender_name or "",
                message.sender_email,
            )
        )

        mime_message["To"] = formataddr(
            (
                message.recipient_name or "",
                message.recipient_email,
            )
        )

        mime_message["Subject"] = message.subject

        if message.reply_to_email:
            mime_message["Reply-To"] = (
                message.reply_to_email
            )

        for header_name, header_value in (
            message.headers.items()
        ):
            if self._is_protected_header(header_name):
                continue

            mime_message[header_name] = header_value

        if message.body_text and message.body_html:
            mime_message.set_content(message.body_text)

            mime_message.add_alternative(
                message.body_html,
                subtype="html",
            )

        elif message.body_html:
            mime_message.set_content(
                self._html_fallback_text(
                    message.body_html
                )
            )

            mime_message.add_alternative(
                message.body_html,
                subtype="html",
            )

        else:
            mime_message.set_content(
                message.body_text or ""
            )

        return mime_message

    @staticmethod
    def _is_protected_header(
        header_name: str,
    ) -> bool:
        protected_headers = {
            "from",
            "to",
            "subject",
            "message-id",
            "reply-to",
            "content-type",
            "mime-version",
        }

        return (
            header_name.strip().lower()
            in protected_headers
        )

    @staticmethod
    def _message_id_domain(
        sender_email: str,
    ) -> str | None:
        if "@" not in sender_email:
            return None

        domain = sender_email.rsplit("@", 1)[1].strip()

        return domain or None

    @staticmethod
    def _html_fallback_text(
        html_body: str,
    ) -> str:
        """
        Provide a basic plain-text fallback.

        A future implementation can replace this with a dedicated HTML-to-text
        library.
        """

        return (
            "This email contains HTML content. "
            "Open it in an HTML-capable email client.\n\n"
            f"{html_body}"
        )

    @staticmethod
    def _parse_refusal(
        refusal: object,
    ) -> tuple[int, str]:
        if (
            isinstance(refusal, tuple)
            and len(refusal) >= 2
        ):
            code = int(refusal[0])
            response = SMTPEmailProvider._decode_response(
                refusal[1]
            )

            return code, response

        return 550, str(refusal)

    @staticmethod
    def _extract_recipient_refusal(
        exc: smtplib.SMTPRecipientsRefused,
        recipient_email: str,
    ) -> tuple[int, str]:
        refusal = exc.recipients.get(
            recipient_email
        )

        if refusal is None and exc.recipients:
            refusal = next(
                iter(exc.recipients.values())
            )

        return SMTPEmailProvider._parse_refusal(
            refusal
        )

    @staticmethod
    def _classify_smtp_error(
        *,
        code: int,
        message: str,
    ) -> RetryableProviderError | PermanentProviderError:
        if 400 <= code < 500:
            return RetryableProviderError(
                message,
                response_code=str(code),
            )

        return PermanentProviderError(
            message,
            response_code=str(code),
        )

    @staticmethod
    def _decode_response(
        response: bytes | str | object,
    ) -> str:
        if isinstance(response, bytes):
            return response.decode(
                "utf-8",
                errors="replace",
            )

        return str(response)