from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.base import MissingPersonPayload


STATUS_MAP = {
    "found_alive": "found",
    "seeking_info": "missing",
    "found": "found",
    "missing": "missing",
    "deceased": "deceased",
    "injured": "injured",
    "unknown": "unknown",
}


class SOSPerson(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    status: str | None = None
    cedula_masked: str | None = None
    display_name: str
    municipio: str | None = None
    parroquia: str | None = None
    hospital_name: str | None = None
    photo_path: str | None = Field(default=None)
    source_date: datetime | None = None


class SOSVenezuelaAdapter:
    source = "sosvenezuela2026"

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def fetch_page(self, *, offset: int, limit: int) -> list[MissingPersonPayload]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(self.base_url, params={"offset": offset, "limit": limit})
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, list):
            raise ValueError("SOS Venezuela response must be a JSON array")

        return [self._normalize(item) for item in payload]

    def _normalize(self, item: dict) -> MissingPersonPayload:
        person = SOSPerson.model_validate(item)
        raw_status = person.status or "unknown"
        location = self._location_for(person)

        return MissingPersonPayload(
            source=self.source,
            external_id=person.id,
            full_name=person.display_name.strip(),
            status=STATUS_MAP.get(raw_status, "unknown"),
            raw_status=raw_status,
            cedula_masked=person.cedula_masked,
            municipio=person.municipio,
            parroquia=person.parroquia,
            hospital_name=person.hospital_name,
            last_known_location=location,
            photo_url=person.photo_path,
            source_date=person.source_date,
            raw_payload=person.model_dump(mode="json"),
        )

    @staticmethod
    def _location_for(person: SOSPerson) -> str | None:
        parts = [
            person.hospital_name,
            person.municipio,
            person.parroquia,
        ]
        cleaned = [part.strip() for part in parts if part and part.strip()]
        return " · ".join(cleaned) if cleaned else None
