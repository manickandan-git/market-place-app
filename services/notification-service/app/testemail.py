import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(
        0,
        str(Path(__file__).resolve().parents[1]),
    )

from app.database import AsyncSessionLocal
from app.email_service import EmailService

from app.config import get_settings
settings = get_settings()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        service = EmailService(db)

        notification = await service.create_direct_notification(
            recipient_email="buyer@example.com",
            recipient_name="John Buyer",
            subject="Marketplace notification test",
            body_text="The Notification Service is working.",
            body_html=(
                "<h1>Marketplace</h1>"
                "<p>The Notification Service is working.</p>"
            ),
        )

        await db.commit()

        delivered = await service.send_notification(
            notification.id
        )

        print(delivered.id)
        print(delivered.status)
        print(delivered.provider_message_id)
        print(delivered.retry_count)
        print(delivered.max_retry_count)
        print(delivered.scheduled_at)
        print(delivered.sent_at)
        print(delivered.failed_at)
        print(delivered.error_message)


if __name__ == "__main__":
    asyncio.run(main())