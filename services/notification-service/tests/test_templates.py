from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from jinja2 import StrictUndefined, UndefinedError

from app.template_service import (
    TemplateRenderingError,
    TemplateService,
    UnknownTemplateError,
)

TEMPLATE_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "templates"
)


@pytest.fixture
def template_service() -> TemplateService:
    """
    Create the real TemplateService using the Notification Service
    template directory.
    """

    return TemplateService(
        template_directory=TEMPLATE_DIRECTORY,
    )


@pytest.fixture
def verification_template_data() -> dict[str, object]:
    return {
        "first_name": "Customer",
        "recipient_email": "customer@example.com",
        "verification_token": "verification-token-123",
        "verification_url": (
            "http://localhost:3000/verify-email"
            "?token=verification-token-123"
        ),
        "expires_in_minutes": 30,
        "company_name": "Marketplace",
        "support_email": "support@marketplace.local",
        "current_year": 2026,
    }


@pytest.fixture
def password_reset_template_data() -> dict[str, object]:
    return {
        "first_name": "Customer",
        "recipient_email": "customer@example.com",
        "reset_token": "reset-token-123",
        "reset_url": (
            "http://localhost:3000/reset-password"
            "?token=reset-token-123"
        ),
        "expires_in_minutes": 20,
        "company_name": "Marketplace",
        "support_email": "support@marketplace.local",
        "current_year": 2026,
    }


@pytest.fixture
def password_changed_template_data() -> dict[str, object]:
    return {
        "first_name": "Customer",
        "recipient_email": "customer@example.com",
        "changed_at": datetime(
            2026,
            7,
            26,
            14,
            30,
            tzinfo=UTC,
        ).isoformat(),
        "ip_address": "127.0.0.1",
        "user_agent": "pytest-test-client",
        "support_url": "http://localhost:3000/support",
        "support_email": "support@marketplace.local",
        "company_name": "Marketplace",
        "current_year": 2026,
    }


def test_template_directory_exists() -> None:
    assert TEMPLATE_DIRECTORY.exists()
    assert TEMPLATE_DIRECTORY.is_dir()


@pytest.mark.parametrize(
    "filename",
    [
        "verification.html",
        "verification.txt",
        "password_reset.html",
        "password_reset.txt",
        "password_changed.html",
        "password_changed.txt",
    ],
)
def test_required_template_file_exists(
    filename: str,
) -> None:
    template_path = TEMPLATE_DIRECTORY / filename

    assert template_path.exists()
    assert template_path.is_file()
    assert template_path.stat().st_size > 0


def test_template_service_uses_strict_undefined(
    template_service: TemplateService,
) -> None:
    """
    Missing required template variables must fail instead of silently
    rendering empty strings.
    """

    undefined_class = template_service.environment.undefined

    assert undefined_class is StrictUndefined


def test_registered_templates_are_available(
    template_service: TemplateService,
) -> None:
    expected_templates = {
        "verification",
        "password_reset",
        "password_changed",
    }

    registered_templates = set(
        template_service.templates.keys()
    )

    assert expected_templates.issubset(
        registered_templates
    )


def test_validate_registered_templates(
    template_service: TemplateService,
) -> None:
    result = template_service.validate_registered_templates()

    if result is not None:
        assert result is True


def test_render_verification_template(
    template_service: TemplateService,
    verification_template_data: dict[str, object],
) -> None:
    rendered = template_service.render(
        "verification",
        verification_template_data,
    )

    assert rendered.template_name == "verification"
    assert rendered.subject
    assert rendered.html
    assert rendered.text

    assert "Customer" in rendered.html
    assert "Customer" in rendered.text

    assert "verification-token-123" in rendered.html
    assert "verification-token-123" in rendered.text

    assert (
        verification_template_data["verification_url"]
        in rendered.html
    )
    assert (
        verification_template_data["verification_url"]
        in rendered.text
    )

    assert "support@marketplace.local" in rendered.html
    assert "support@marketplace.local" in rendered.text

    assert "{{" not in rendered.html
    assert "}}" not in rendered.html
    assert "{{" not in rendered.text
    assert "}}" not in rendered.text


def test_render_verification_email_helper(
    template_service: TemplateService,
) -> None:
    rendered = template_service.render_verification_email(
        first_name="Customer",
        recipient_email="customer@example.com",
        verification_token="verification-token-123",
        verification_url=(
            "http://localhost:3000/verify-email"
            "?token=verification-token-123"
        ),
        expires_in_minutes=30,
    )

    assert rendered.template_name == "verification"
    assert "Customer" in rendered.html
    assert "verification-token-123" in rendered.html
    assert "verification-token-123" in rendered.text
    assert "verify" in rendered.subject.lower()


def test_render_password_reset_template(
    template_service: TemplateService,
    password_reset_template_data: dict[str, object],
) -> None:
    rendered = template_service.render(
        "password_reset",
        password_reset_template_data,
    )

    assert rendered.template_name == "password_reset"
    assert rendered.subject
    assert rendered.html
    assert rendered.text

    assert "Customer" in rendered.html
    assert "Customer" in rendered.text

    assert "reset-token-123" in rendered.html
    assert "reset-token-123" in rendered.text

    assert (
        password_reset_template_data["reset_url"]
        in rendered.html
    )
    assert (
        password_reset_template_data["reset_url"]
        in rendered.text
    )

    assert "password" in rendered.subject.lower()

    assert "{{" not in rendered.html
    assert "}}" not in rendered.html
    assert "{{" not in rendered.text
    assert "}}" not in rendered.text


def test_render_password_reset_email_helper(
    template_service: TemplateService,
) -> None:
    rendered = template_service.render_password_reset_email(
        first_name="Customer",
        recipient_email="customer@example.com",
        reset_token="reset-token-123",
        reset_url=(
            "http://localhost:3000/reset-password"
            "?token=reset-token-123"
        ),
        expires_in_minutes=20,
    )

    assert rendered.template_name == "password_reset"
    assert "Customer" in rendered.html
    assert "reset-token-123" in rendered.html
    assert "reset-token-123" in rendered.text
    assert "password" in rendered.subject.lower()


def test_render_password_changed_template(
    template_service: TemplateService,
    password_changed_template_data: dict[str, object],
) -> None:
    rendered = template_service.render(
        "password_changed",
        password_changed_template_data,
    )

    assert rendered.template_name == "password_changed"
    assert rendered.subject
    assert rendered.html
    assert rendered.text

    assert "Customer" in rendered.html
    assert "Customer" in rendered.text

    assert "127.0.0.1" in rendered.html
    assert "127.0.0.1" in rendered.text

    assert "pytest-test-client" in rendered.html
    assert "pytest-test-client" in rendered.text

    assert (
        password_changed_template_data["changed_at"]
        in rendered.html
    )
    assert (
        password_changed_template_data["changed_at"]
        in rendered.text
    )

    assert "support@marketplace.local" in rendered.html
    assert "support@marketplace.local" in rendered.text

    assert "password" in rendered.subject.lower()

    assert "{{" not in rendered.html
    assert "}}" not in rendered.html
    assert "{{" not in rendered.text
    assert "}}" not in rendered.text


def test_render_password_changed_email_helper(
    template_service: TemplateService,
) -> None:
    changed_at = datetime(
        2026,
        7,
        26,
        14,
        30,
        tzinfo=UTC,
    )

    rendered = template_service.render_password_changed_email(
        first_name="Customer",
        recipient_email="customer@example.com",
        changed_at=changed_at,
        ip_address="127.0.0.1",
        user_agent="pytest-test-client",
    )

    assert rendered.template_name == "password_changed"
    assert "Customer" in rendered.html
    assert "127.0.0.1" in rendered.html
    assert "pytest-test-client" in rendered.html
    assert "password" in rendered.subject.lower()


def test_password_changed_template_allows_optional_security_fields(
    template_service: TemplateService,
    password_changed_template_data: dict[str, object],
) -> None:
    template_data = {
        key: value
        for key, value in password_changed_template_data.items()
        if key not in {
            "ip_address",
            "user_agent",
        }
    }

    rendered = template_service.render(
        "password_changed",
        template_data,
    )

    assert rendered.html
    assert rendered.text

    assert "127.0.0.1" not in rendered.html
    assert "127.0.0.1" not in rendered.text

    assert "pytest-test-client" not in rendered.html
    assert "pytest-test-client" not in rendered.text


def test_unknown_template_is_rejected(
    template_service: TemplateService,
) -> None:
    with pytest.raises(UnknownTemplateError):
        template_service.render(
            "unknown_template",
            {
                "first_name": "Customer",
            },
        )


@pytest.mark.parametrize(
    ("template_name", "template_data"),
    [
        (
            "verification",
            {
                "recipient_email": "customer@example.com",
                "verification_token": "token-123",
                "verification_url": "http://localhost/verify",
                "expires_in_minutes": 30,
                "company_name": "Marketplace",
                "support_email": "support@example.com",
                "current_year": 2026,
            },
        ),
        (
            "password_reset",
            {
                "first_name": "Customer",
                "recipient_email": "customer@example.com",
                "reset_url": "http://localhost/reset",
                "expires_in_minutes": 20,
                "company_name": "Marketplace",
                "support_email": "support@example.com",
                "current_year": 2026,
            },
        ),
        (
            "password_changed",
            {
                "first_name": "Customer",
                "recipient_email": "customer@example.com",
                "company_name": "Marketplace",
                "support_email": "support@example.com",
                "support_url": "http://localhost/support",
                "current_year": 2026,
            },
        ),
    ],
)
def test_missing_required_template_variable_is_rejected(
    template_service: TemplateService,
    template_name: str,
    template_data: dict[str, object],
) -> None:
    with pytest.raises(
        (
            TemplateRenderingError,
            UndefinedError,
        )
    ):
        template_service.render(
            template_name,
            template_data,
        )


def test_verification_url_builder(
    template_service: TemplateService,
) -> None:
    url = template_service.build_verification_url(
        "verification-token-123"
    )

    assert "verification-token-123" in url
    assert "verify" in url.lower()


def test_password_reset_url_builder(
    template_service: TemplateService,
) -> None:
    url = template_service.build_password_reset_url(
        "reset-token-123"
    )

    assert "reset-token-123" in url
    assert "reset" in url.lower()


def test_verification_html_contains_clickable_link(
    template_service: TemplateService,
    verification_template_data: dict[str, object],
) -> None:
    rendered = template_service.render(
        "verification",
        verification_template_data,
    )

    verification_url = str(
        verification_template_data["verification_url"]
    )

    assert f'href="{verification_url}"' in rendered.html
    assert "Verify Email Address" in rendered.html


def test_password_reset_html_contains_clickable_link(
    template_service: TemplateService,
    password_reset_template_data: dict[str, object],
) -> None:
    rendered = template_service.render(
        "password_reset",
        password_reset_template_data,
    )

    reset_url = str(
        password_reset_template_data["reset_url"]
    )

    assert f'href="{reset_url}"' in rendered.html
    assert "Reset Password" in rendered.html


def test_password_changed_html_contains_support_link(
    template_service: TemplateService,
    password_changed_template_data: dict[str, object],
) -> None:
    rendered = template_service.render(
        "password_changed",
        password_changed_template_data,
    )

    support_url = str(
        password_changed_template_data["support_url"]
    )

    assert f'href="{support_url}"' in rendered.html
    assert "Contact Support" in rendered.html


@pytest.mark.parametrize(
    ("template_name", "template_data"),
    [
        (
            "verification",
            {
                "first_name": "<script>alert('xss')</script>",
                "recipient_email": "customer@example.com",
                "verification_token": "token-123",
                "verification_url": "http://localhost/verify",
                "expires_in_minutes": 30,
                "company_name": "Marketplace",
                "support_email": "support@example.com",
                "current_year": 2026,
            },
        ),
        (
            "password_reset",
            {
                "first_name": "<script>alert('xss')</script>",
                "recipient_email": "customer@example.com",
                "reset_token": "token-123",
                "reset_url": "http://localhost/reset",
                "expires_in_minutes": 20,
                "company_name": "Marketplace",
                "support_email": "support@example.com",
                "current_year": 2026,
            },
        ),
    ],
)
def test_html_templates_escape_untrusted_values(
    template_service: TemplateService,
    template_name: str,
    template_data: dict[str, object],
) -> None:
    rendered = template_service.render(
        template_name,
        template_data,
    )

    assert "<script>alert('xss')</script>" not in rendered.html
    assert (
        "&lt;script&gt;"
        in rendered.html
    )


def test_plain_text_template_preserves_readable_content(
    template_service: TemplateService,
    verification_template_data: dict[str, object],
) -> None:
    rendered = template_service.render(
        "verification",
        verification_template_data,
    )

    assert "<html" not in rendered.text.lower()
    assert "<body" not in rendered.text.lower()
    assert "<p>" not in rendered.text.lower()

    assert "EMAIL VERIFICATION" in rendered.text
    assert "Security Notice" in rendered.text


def test_custom_template_can_be_registered(
    template_service: TemplateService,
    tmp_path: Path,
) -> None:
    html_template = tmp_path / "custom.html"
    text_template = tmp_path / "custom.txt"

    html_template.write_text(
        "<html><body>Hello {{ first_name }}</body></html>",
        encoding="utf-8",
    )
    text_template.write_text(
        "Hello {{ first_name }}",
        encoding="utf-8",
    )

    template_service.environment.loader.searchpath.append(
        str(tmp_path)
    )

    template_service.register_template(
        name="custom",
        subject="Custom email",
        html_template="custom.html",
        text_template="custom.txt",
    )

    rendered = template_service.render(
        "custom",
        {
            "first_name": "Customer",
        },
    )

    assert rendered.template_name == "custom"
    assert rendered.subject == "Custom email"
    assert "Hello Customer" in rendered.html
    assert "Hello Customer" in rendered.text
