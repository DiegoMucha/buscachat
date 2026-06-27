import logging
import time
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session

from app.adapters import SOSVenezuelaAdapter
from app.config import Settings
from app.database import engine
from app.models import utc_now
from app.services import sync_missing_people

log = logging.getLogger(__name__)


def start_scheduler(settings: Settings) -> BackgroundScheduler | None:
    if not settings.missing_people_sync_enabled:
        log.info("Missing people sync scheduler is disabled")
        return None

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _sync_missing_people_job(settings),
        trigger=IntervalTrigger(hours=settings.missing_people_sync_interval_hours),
        id="sync_missing_people",
        name="Sync missing people from configured sources",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=utc_now() if settings.missing_people_sync_run_on_startup else None,
    )
    scheduler.start()
    log.info(
        "Missing people sync scheduler started: every %s hour(s)",
        settings.missing_people_sync_interval_hours,
    )
    return scheduler


def _sync_missing_people_job(settings: Settings) -> Callable[[], None]:
    def job() -> None:
        adapter = SOSVenezuelaAdapter(settings.sos_venezuela_persons_url)

        def run_once() -> None:
            with Session(engine) as session:
                result = sync_missing_people(
                    session=session,
                    adapter=adapter,
                    page_limit=settings.missing_people_sync_page_limit,
                    max_pages=settings.missing_people_sync_max_pages,
                )
            log.info(
                "Missing people sync complete: source=%s records_seen=%s records_upserted=%s",
                result.source,
                result.records_seen,
                result.records_upserted,
            )

        _run_with_retries(
            run_once,
            attempts=settings.missing_people_sync_retry_attempts,
            base_delay_seconds=settings.missing_people_sync_retry_backoff_seconds,
        )

    return job


def _run_with_retries(
    func: Callable[[], None],
    *,
    attempts: int,
    base_delay_seconds: float,
) -> None:
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            func()
            return
        except Exception:
            if attempt >= attempts:
                log.exception("Missing people sync failed after %s attempt(s)", attempts)
                raise
            delay = base_delay_seconds * (2 ** (attempt - 1))
            log.warning(
                "Missing people sync attempt %s/%s failed; retrying in %.1fs",
                attempt,
                attempts,
                delay,
                exc_info=True,
            )
            time.sleep(delay)
