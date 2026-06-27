from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel


class MissingPersonPayload(BaseModel):
    source: str
    external_id: str
    full_name: str
    status: str = "unknown"
    raw_status: str | None = None
    cedula_masked: str | None = None
    municipio: str | None = None
    parroquia: str | None = None
    hospital_name: str | None = None
    last_known_location: str | None = None
    photo_url: str | None = None
    source_date: datetime | None = None
    raw_payload: dict[str, Any]


class MissingPeopleAdapter(Protocol):
    source: str

    def fetch_page(self, *, offset: int, limit: int) -> list[MissingPersonPayload]:
        raise NotImplementedError
