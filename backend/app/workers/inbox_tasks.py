"""Inbox-checking Celery tasks — polling email inboxes, ingesting replies, and auto-responding."""

import logging
import uuid

from app.workers.celery_app import celery_app
from app.workers.base_task import BaseTask

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.inbox_tasks.check_inboxes",
    queue="inbox",
)
def check_inboxes(self, **kwargs):
    """Check all connected email inboxes for new replies.

    Scheduled via Celery Beat every 2 minutes.
    Connects to Gmail via IMAP, fetches unseen messages, matches to outreach,
    and creates Reply records.
    """
    import asyncio
    from app.database import async_session
    from app.config import settings

    if not settings.GMAIL_INBOX_EMAIL or not settings.GMAIL_INBOX_APP_PASSWORD:
        logger.info("Inbox polling disabled — no Gmail credentials configured")
        return {"status": "disabled", "note": "no_gmail_credentials"}

    async def _check():
        from app.services.email.inbox_service import InboxService

        async with async_session() as db:
            svc = InboxService(db)
            try:
                await svc.connect()
                replies = await svc.fetch_and_process_new_messages()
                logger.info("Inbox check: found %d new replies", len(replies))

                # Trigger classification for each new reply
                for reply in replies:
                    try:
                        process_inbound_reply.delay(str(reply.id))
                    except Exception as exc:
                        logger.warning("Failed to dispatch classification for reply %s: %s", reply.id, exc)

                return {
                    "status": "completed",
                    "new_replies": len(replies),
                    "reply_ids": [str(r.id) for r in replies],
                }
            except Exception as exc:
                logger.error("Inbox check failed: %s", exc)
                return {"status": "error", "error": str(exc)}
            finally:
                await svc.disconnect()

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_check())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.inbox_tasks.check_inbox_for_account",
    queue="inbox",
)
def check_inbox_for_account(self, email: str, **kwargs):
    """Check inbox for a specific email account.

    Called by check_inboxes for each configured inbox account.
    """
    import asyncio
    from app.database import async_session
    from app.config import settings

    async def _check():
        from app.services.email.inbox_service import InboxService

        async with async_session() as db:
            svc = InboxService(db)
            try:
                await svc.connect()
                replies = await svc.fetch_and_process_new_messages()
                logger.info("Inbox check for %s: found %d new replies", email, len(replies))

                for reply in replies:
                    try:
                        process_inbound_reply.delay(str(reply.id))
                    except Exception as exc:
                        logger.warning("Failed to dispatch for reply %s: %s", reply.id, exc)

                return {
                    "status": "completed",
                    "email": email,
                    "new_replies": len(replies),
                }
            except Exception as exc:
                logger.error("Inbox check failed for %s: %s", email, exc)
                return {"status": "error", "email": email, "error": str(exc)}
            finally:
                await svc.disconnect()

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_check())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.inbox_tasks.process_inbound_reply",
    queue="inbox",
)
def process_inbound_reply(self, reply_id: str, **kwargs):
    """Process a newly ingested reply — classify and optionally auto-respond.

    Dispatched after a new Reply record is created by the inbox checker.
    """
    import asyncio
    from app.database import async_session
    from app.services.email.auto_responder import AutoResponder

    async def _process():
        async with async_session() as db:
            responder = AutoResponder(db)
            result = await responder.process_reply(uuid.UUID(reply_id))
            return result

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_process())
    finally:
        loop.close()