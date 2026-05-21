"""Inbox-checking Celery tasks — polling email inboxes, ingesting replies, and triggering classification."""

import logging

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
    Phase 2 will add: IMAP/POP polling, reply ingestion, dedup.

    For each new reply found:
      1. Create a Reply record
      2. Trigger classify_reply task
    """
    logger.info("Task check_inboxes started — polling for new replies (placeholder)")
    # TODO: Implement IMAP polling for connected email accounts
    # TODO: For each new reply:
    #   - Dedup by Message-ID header
    #   - Create Reply record
    #   - Dispatch classify_reply task
    logger.info("Task check_inboxes completed (placeholder)")
    return {"status": "completed", "note": "placeholder"}


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.inbox_tasks.process_new_reply",
    queue="inbox",
)
def process_new_reply(self, reply_id: str, **kwargs):
    """Process a newly ingested reply — classify and create follow-ups.

    Dispatched after a new Reply record is created.
    """
    from app.workers.outreach_tasks import classify_reply

    # Chain: classify the reply, which will also create follow-up tasks
    classify_reply.delay(reply_id)
    return {"reply_id": reply_id, "action": "classify_dispatched"}
