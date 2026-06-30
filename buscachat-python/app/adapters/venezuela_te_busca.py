import logging
from datetime import datetime
from typing import Any

import httpx
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_BASE_URL = "https://venezuelatebusca.com"
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}
log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def decode_flattened_response(data: Any) -> Any:
    if not isinstance(data, list) or not data:
        return data

    resolved: dict[int, Any] = {}

    def walk(index: int) -> Any:
        if index < 0:
            return None
        if index in resolved:
            return resolved[index]

        item = data[index]
        if item is None or not isinstance(item, dict | list):
            return item

        if isinstance(item, list):
            items: list[Any] = []
            resolved[index] = items
            items.extend(walk(value_index) for value_index in item)
            return items

        obj: dict[str, Any] = {}
        resolved[index] = obj
        for pointer_key, value_index in item.items():
            if not pointer_key.startswith("_"):
                continue
            actual_key = walk(int(pointer_key[1:]))
            if actual_key is not None:
                obj[str(actual_key)] = walk(value_index)
        return obj

    return walk(0)


class VenezuelaTeBuscaPerson(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    first_name: str | None = Field(default=None, alias="firstName")
    last_name: str | None = Field(default=None, alias="lastName")
    id_number: str | None = Field(default=None, alias="idNumber")
    age: int | None = None
    gender: str | None = None
    last_seen: str | None = Field(default=None, alias="lastSeen")
    description: str | None = None
    status: str | None = None
    photo_url: str | None = Field(default=None, alias="photoUrl")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    last_activity_at: datetime | None = Field(default=None, alias="lastActivityAt")
    found_note: str | None = Field(default=None, alias="foundNote")
    finder: str | dict[str, Any] | None = None
    hospital_name: str | None = Field(default=None, alias="hospitalName")
    hospital_status: str | None = Field(default=None, alias="hospitalStatus")
    sources: list[dict[str, Any]] = Field(default_factory=list)
    tips: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def full_name(self) -> str:
        parts = [part.strip() for part in [self.first_name, self.last_name] if part and part.strip()]
        if not parts:
            return "Nombre no disponible"
        if len(parts) == 2 and parts[1].casefold() in parts[0].casefold():
            return parts[0]
        return " ".join(parts)

    @property
    def cedula_masked(self) -> str | None:
        return self.id_number

    @property
    def last_known_location(self) -> str | None:
        return self.last_seen

    @property
    def source_date(self) -> datetime | None:
        return self.last_activity_at or self.updated_at or self.created_at


class VenezuelaTeBuscaSearchResult(BaseModel):
    query: str
    persons: list[VenezuelaTeBuscaPerson] = Field(default_factory=list)
    total_count: int = 0
    degraded: bool = False
    has_more: bool = False
    next_cursor: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)


class VenezuelaTeBuscaClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def search(self, query: str, *, limit: int = 10) -> VenezuelaTeBuscaSearchResult:
        cleaned = " ".join(query.split())
        if not cleaned or limit <= 0:
            return VenezuelaTeBuscaSearchResult(query=cleaned)

        with tracer.start_as_current_span("venezuela_te_busca.search") as span:
            span.set_attribute("search.query", cleaned)
            span.set_attribute("search.limit", limit)
            span.set_attribute("http.url", f"{self.base_url}/_root.data")
            with httpx.Client(
                timeout=self.timeout,
                headers=DEFAULT_HEADERS,
                transport=self.transport,
            ) as client:
                response = client.get(f"{self.base_url}/_root.data", params={"query": cleaned})
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.response_content_type", response.headers.get("content-type", ""))
                if request_id := response.headers.get("x-request-id"):
                    span.set_attribute("http.response.header.x_request_id", request_id)
                response.raise_for_status()
                decoded = decode_flattened_response(response.json())

            data = _route_data(decoded)
            pagination = data.get("pagination") or {}
            raw_persons = data.get("persons") or []
            result_query = str((data.get("filters") or {}).get("query") or cleaned)
            persons = _parse_persons(raw_persons[:limit], query=result_query, span=span)
            total_count = int(data.get("totalCount") or len(persons))
            degraded = bool(data.get("degraded"))
            span.set_attribute("search.result.total_count", total_count)
            span.set_attribute("search.result.returned_count", len(persons))
            span.set_attribute("search.result.raw_count", len(raw_persons))
            span.set_attribute("search.result.degraded", degraded)
            log.info(
                "Venezuela Te Busca search completed",
                extra={
                    "query": result_query,
                    "total_count": total_count,
                    "returned_count": len(persons),
                    "raw_count": len(raw_persons),
                    "degraded": degraded,
                },
            )
            return VenezuelaTeBuscaSearchResult(
                query=result_query,
                persons=persons,
                total_count=total_count,
                degraded=degraded,
                has_more=bool(pagination.get("hasMore")),
                next_cursor=pagination.get("nextCursor"),
                stats=data.get("stats") or {},
            )


def search_venezuela_te_busca(
    query: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 20.0,
    limit: int = 10,
) -> VenezuelaTeBuscaSearchResult:
    return VenezuelaTeBuscaClient(base_url=base_url, timeout=timeout).search(query, limit=limit)


def _route_data(decoded: Any) -> dict[str, Any]:
    if not isinstance(decoded, dict):
        raise ValueError("Venezuela Te Busca response must decode to a JSON object")

    route = decoded.get("routes/_index")
    if not isinstance(route, dict) or not isinstance(route.get("data"), dict):
        raise ValueError("Venezuela Te Busca response is missing routes/_index data")
    return route["data"]


def _parse_persons(
    raw_persons: list[Any],
    *,
    query: str,
    span: trace.Span,
) -> list[VenezuelaTeBuscaPerson]:
    persons: list[VenezuelaTeBuscaPerson] = []
    for index, person in enumerate(raw_persons):
        if not isinstance(person, dict):
            log.warning(
                "Skipping Venezuela Te Busca person because payload is not an object",
                extra={"query": query, "person_index": index, "payload_type": type(person).__name__},
            )
            span.add_event(
                "venezuela_te_busca.person_skipped",
                {"person.index": index, "person.payload_type": type(person).__name__},
            )
            continue
        try:
            persons.append(VenezuelaTeBuscaPerson.model_validate(person))
        except ValidationError as exc:
            person_id = str(person.get("id") or "")
            log.exception(
                "Skipping Venezuela Te Busca person because payload validation failed",
                extra={
                    "query": query,
                    "person_index": index,
                    "person_id": person_id,
                    "validation_errors": exc.errors(),
                },
            )
            span.record_exception(exc)
            span.add_event(
                "venezuela_te_busca.person_validation_failed",
                {"person.index": index, "person.id": person_id},
            )
    return persons
