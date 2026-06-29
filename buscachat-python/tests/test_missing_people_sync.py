import pytest

import app.services.missing_people_sync as missing_people_sync
from app.adapters.base import MissingPersonPayload


class FakeMissingPeopleAdapter:
    source = "test-source"

    def __init__(self, pages: list[list[MissingPersonPayload]]) -> None:
        self.pages = pages
        self.fetches: list[tuple[int, int]] = []

    def fetch_page(self, *, offset: int, limit: int) -> list[MissingPersonPayload]:
        self.fetches.append((offset, limit))
        page_index = offset // limit
        if page_index >= len(self.pages):
            return []
        return self.pages[page_index]


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_request_interval_seconds_defaults_to_50_requests_per_minute() -> None:
    assert missing_people_sync._request_interval_seconds(
        missing_people_sync.MISSING_PEOPLE_SYNC_REQUESTS_PER_MINUTE
    ) == pytest.approx(1.2)


def test_request_interval_seconds_can_be_disabled() -> None:
    assert missing_people_sync._request_interval_seconds(None) == 0


def test_request_interval_seconds_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="requests_per_minute"):
        missing_people_sync._request_interval_seconds(0)


def test_iter_missing_people_pages_uses_offsets_and_max_pages() -> None:
    payload = MissingPersonPayload(
        source="test-source",
        external_id="person-1",
        full_name="Alex Example Rivera",
        raw_payload={"id": "person-1", "display_name": "Alex Example Rivera"},
    )
    adapter = FakeMissingPeopleAdapter([[payload], [payload], [payload]])

    pages = list(
        missing_people_sync._iter_missing_people_pages(
            adapter=adapter,
            page_limit=1,
            max_pages=2,
            requests_per_minute=None,
            sleep=lambda _delay: None,
            monotonic=lambda: 0.0,
        )
    )

    assert pages == [[payload], [payload]]
    assert adapter.fetches == [(0, 1), (1, 1)]


def test_sync_missing_people_throttles_between_page_fetches(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = MissingPersonPayload(
        source="test-source",
        external_id="person-1",
        full_name="Alex Example Rivera",
        raw_payload={"id": "person-1", "display_name": "Alex Example Rivera"},
    )
    adapter = FakeMissingPeopleAdapter([[payload], [payload], []])
    session = FakeSession()
    now = 100.0
    sleep_delays: list[float] = []

    def monotonic() -> float:
        return now

    def sleep(delay: float) -> None:
        nonlocal now
        sleep_delays.append(delay)
        now += delay

    monkeypatch.setattr(missing_people_sync, "_upsert_record", lambda *_args: 1)
    monkeypatch.setattr(missing_people_sync, "_upsert_sync_state", lambda *_args, **_kwargs: None)

    result = missing_people_sync.sync_missing_people(
        session=session,  # type: ignore[arg-type]
        adapter=adapter,
        page_limit=1,
        requests_per_minute=60,
        sleep=sleep,
        monotonic=monotonic,
    )

    assert result.records_seen == 2
    assert result.records_upserted == 2
    assert sleep_delays == [1.0, 1.0]
    assert session.rollbacks == 0


def test_sync_missing_people_does_not_throttle_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = MissingPersonPayload(
        source="test-source",
        external_id="person-1",
        full_name="Alex Example Rivera",
        raw_payload={"id": "person-1", "display_name": "Alex Example Rivera"},
    )
    adapter = FakeMissingPeopleAdapter([[payload], []])
    sleep_delays: list[float] = []

    monkeypatch.setattr(missing_people_sync, "_upsert_record", lambda *_args: 1)
    monkeypatch.setattr(missing_people_sync, "_upsert_sync_state", lambda *_args, **_kwargs: None)

    missing_people_sync.sync_missing_people(
        session=FakeSession(),  # type: ignore[arg-type]
        adapter=adapter,
        page_limit=1,
        requests_per_minute=None,
        sleep=sleep_delays.append,
    )

    assert sleep_delays == []
