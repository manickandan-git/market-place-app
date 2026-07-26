from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    select_autoescape,
)

from app.config import Settings, get_settings


class TemplateServiceError(Exception):
    """
    Base exception for notification template failures.
    """


class UnknownTemplateError(TemplateServiceError):
    """
    Raised when a requested template is not registered or does not exist.
    """


class TemplateRenderingError(TemplateServiceError):
    """
    Raised when a registered template cannot be rendered.
    """


@dataclass(slots=True)
class RenderedTemplate:
    """
    Fully rendered notification template.

    Both HTML and plain-text bodies are supported. A template may use only
    one body format, although transactional emails should normally provide
    both.
    """

    template_name: str
    subject: str
    body_html: str | None
    body_text: str | None

    @property
    def html(self) -> str | None:
        """Backward-compatible alias for HTML body content."""

        return self.body_html

    @property
    def text(self) -> str | None:
        """Backward-compatible alias for text body content."""

        return self.body_text


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    """
    Registry entry describing one supported email template.
    """

    name: str
    html_filename: str | None
    text_filename: str | None
    default_subject: str


class TemplateService:
    """
    Loads and renders registered Jinja2 email templates.

    Templates are explicitly registered to prevent callers from loading
    arbitrary files from the template directory.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        template_directory: Path | str | None = None,
    ) -> None:
        self.settings = settings or get_settings()

        self.template_directory = Path(
            template_directory
            or Path(__file__).resolve().parent / "templates"
        )

        self.environment = Environment(
            loader=FileSystemLoader(
                str(self.template_directory),
            ),
            autoescape=select_autoescape(
                enabled_extensions=("html", "htm", "xml"),
                default_for_string=True,
                default=False,
            ),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        self.environment.globals.update(
            marketplace_name=self.settings.default_from_name,
            marketplace_web_url=self.settings.marketplace_web_url,
            support_email=str(self.settings.support_email),
        )

        self._templates: dict[str, TemplateDefinition] = {
            "verification": TemplateDefinition(
                name="verification",
                html_filename="verification.html",
                text_filename="verification.txt",
                default_subject=(
                    self.settings.verification_email_subject
                ),
            ),
            "password_reset": TemplateDefinition(
                name="password_reset",
                html_filename="password_reset.html",
                text_filename="password_reset.txt",
                default_subject=(
                    self.settings.password_reset_email_subject
                ),
            ),
            "password_changed": TemplateDefinition(
                name="password_changed",
                html_filename="password_changed.html",
                text_filename="password_changed.txt",
                default_subject=(
                    self.settings.password_changed_email_subject
                ),
            ),
        }

    @property
    def registered_templates(self) -> tuple[str, ...]:
        """
        Return all template names accepted by the service.
        """

        return tuple(sorted(self._templates))

    @property
    def templates(self) -> dict[str, TemplateDefinition]:
        """Backward-compatible access to the template registry."""

        return self._templates

    def is_registered(self, template_name: str) -> bool:
        """
        Check whether a template is registered.
        """

        normalized_name = self._normalize_template_name(
            template_name
        )

        return normalized_name in self._templates

    def render(
        self,
        template_name: str,
        template_data: dict[str, Any],
        *,
        subject: str | None = None,
    ) -> RenderedTemplate:
        """
        Render a registered email template.

        StrictUndefined causes rendering to fail when a required template
        variable is missing rather than silently producing incomplete email.
        """

        normalized_name = self._normalize_template_name(
            template_name
        )

        definition = self._templates.get(normalized_name)

        if definition is None:
            raise UnknownTemplateError(
                f"Unknown notification template: {template_name}"
            )

        context = self._build_context(template_data)

        try:
            body_html = self._render_file(
                definition.html_filename,
                context,
            )

            body_text = self._render_file(
                definition.text_filename,
                context,
            )

        except TemplateNotFound as exc:
            raise UnknownTemplateError(
                f"Template file was not found: {exc.name}"
            ) from exc

        except Exception as exc:
            raise TemplateRenderingError(
                (
                    f"Unable to render template "
                    f"'{normalized_name}': {exc}"
                )
            ) from exc

        if not body_html and not body_text:
            raise TemplateRenderingError(
                (
                    f"Template '{normalized_name}' produced "
                    "no email content"
                )
            )

        rendered_subject = (
            subject.strip()
            if subject and subject.strip()
            else definition.default_subject
        )

        return RenderedTemplate(
            template_name=normalized_name,
            subject=rendered_subject,
            body_html=body_html,
            body_text=body_text,
        )

    def render_verification_email(
        self,
        *,
        first_name: str,
        verification_token: str,
        expires_in_minutes: int,
        recipient_email: str | None = None,
        verification_url: str | None = None,
        subject: str | None = None,
        additional_data: dict[str, Any] | None = None,
    ) -> RenderedTemplate:
        """
        Render the account-verification email.
        """

        resolved_url = (
            verification_url
            or self.build_verification_url(
                verification_token
            )
        )

        template_data: dict[str, Any] = {
            "first_name": first_name,
            "recipient_email": recipient_email or "",
            "verification_token": verification_token,
            "verification_url": resolved_url,
            "expires_in_minutes": expires_in_minutes,
        }

        if additional_data:
            template_data.update(additional_data)

        return self.render(
            "verification",
            template_data,
            subject=subject,
        )

    def render_password_reset_email(
        self,
        *,
        first_name: str,
        reset_token: str,
        expires_in_minutes: int,
        recipient_email: str | None = None,
        reset_url: str | None = None,
        subject: str | None = None,
        additional_data: dict[str, Any] | None = None,
    ) -> RenderedTemplate:
        """
        Render the password-reset email.
        """

        resolved_url = (
            reset_url
            or self.build_password_reset_url(reset_token)
        )

        template_data: dict[str, Any] = {
            "first_name": first_name,
            "recipient_email": recipient_email or "",
            "reset_token": reset_token,
            "reset_url": resolved_url,
            "expires_in_minutes": expires_in_minutes,
        }

        if additional_data:
            template_data.update(additional_data)

        return self.render(
            "password_reset",
            template_data,
            subject=subject,
        )

    def render_password_changed_email(
        self,
        *,
        first_name: str,
        changed_at: Any,
        recipient_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        support_url: str | None = None,
        subject: str | None = None,
        additional_data: dict[str, Any] | None = None,
    ) -> RenderedTemplate:
        """
        Render the password-changed security alert.
        """

        resolved_support_url = (
            support_url
            or (
                f"{self.settings.marketplace_web_url.rstrip('/')}"
                "/support"
            )
        )

        template_data: dict[str, Any] = {
            "first_name": first_name,
            "recipient_email": recipient_email or "",
            "changed_at": changed_at,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "support_url": resolved_support_url,
        }

        if additional_data:
            template_data.update(additional_data)

        return self.render(
            "password_changed",
            template_data,
            subject=subject,
        )

    def build_verification_url(
        self,
        verification_token: str,
    ) -> str:
        """
        Build the Marketplace account-verification URL.
        """

        return self._append_query_parameters(
            self.settings.verification_url_base,
            {
                "token": verification_token,
            },
        )

    def build_password_reset_url(
        self,
        reset_token: str,
    ) -> str:
        """
        Build the Marketplace password-reset URL.
        """

        return self._append_query_parameters(
            self.settings.password_reset_url_base,
            {
                "token": reset_token,
            },
        )

    def register_template(
        self,
        definition: TemplateDefinition | None = None,
        *,
        name: str | None = None,
        subject: str | None = None,
        html_template: str | None = None,
        text_template: str | None = None,
        replace_existing: bool = False,
    ) -> None:
        """
        Register an additional template at application startup.

        This can later support order-confirmation, shipment, payment, and
        seller-onboarding templates.
        """

        if definition is None:
            if name is None or subject is None:
                raise TemplateServiceError(
                    "name and subject are required"
                )

            definition = TemplateDefinition(
                name=name,
                html_filename=html_template,
                text_filename=text_template,
                default_subject=subject,
            )

        normalized_name = self._normalize_template_name(
            definition.name
        )

        if (
            normalized_name in self._templates
            and not replace_existing
        ):
            raise TemplateServiceError(
                (
                    f"Template '{normalized_name}' "
                    "is already registered"
                )
            )

        if (
            not definition.html_filename
            and not definition.text_filename
        ):
            raise TemplateServiceError(
                "A template must define HTML or text content"
            )

        self._templates[normalized_name] = (
            TemplateDefinition(
                name=normalized_name,
                html_filename=definition.html_filename,
                text_filename=definition.text_filename,
                default_subject=definition.default_subject,
            )
        )

    def validate_registered_templates(
        self,
    ) -> bool | list[str]:
        """
        Verify that all registered template files exist.

        Returns a list of missing template filenames.
        """

        missing_files: list[str] = []

        for definition in self._templates.values():
            filenames = (
                definition.html_filename,
                definition.text_filename,
            )

            for filename in filenames:
                if not filename:
                    continue

                template_path = (
                    self.template_directory / filename
                )

                if not template_path.is_file():
                    missing_files.append(filename)

        unique_missing = sorted(set(missing_files))

        return True if not unique_missing else unique_missing

    def _render_file(
        self,
        filename: str | None,
        context: dict[str, Any],
    ) -> str | None:
        if not filename:
            return None

        template = self.environment.get_template(filename)

        rendered = template.render(**context).strip()

        return rendered or None

    def _build_context(
        self,
        template_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create a rendering context without mutating the caller's dictionary.
        """

        context = dict(template_data)

        context.setdefault(
            "marketplace_name",
            self.settings.default_from_name,
        )

        context.setdefault(
            "marketplace_web_url",
            self.settings.marketplace_web_url,
        )

        context.setdefault(
            "support_email",
            str(self.settings.support_email),
        )

        context.setdefault(
            "company_name",
            self.settings.default_from_name,
        )

        context.setdefault(
            "current_year",
            datetime.now(timezone.utc).year,
        )

        context.setdefault("recipient_email", "")
        context.setdefault("ip_address", None)
        context.setdefault("user_agent", None)

        return context

    @staticmethod
    def _normalize_template_name(
        template_name: str,
    ) -> str:
        normalized_name = template_name.strip().lower()

        if not normalized_name:
            raise UnknownTemplateError(
                "Template name cannot be blank"
            )

        return normalized_name

    @staticmethod
    def _append_query_parameters(
        base_url: str,
        parameters: dict[str, str],
    ) -> str:
        separator = "&" if "?" in base_url else "?"

        return (
            f"{base_url}"
            f"{separator}"
            f"{urlencode(parameters)}"
        )