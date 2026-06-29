import json
from pathlib import Path
from typing import Any

import httpx

from app.adapters.venezuela_te_busca import VenezuelaTeBuscaClient, VenezuelaTeBuscaPerson, decode_flattened_response

FIXTURE = Path(__file__).parent / "mock" / "response-venezuela-te-busca.json"


def _flatten_remix_payload(value: Any) -> list[Any]:
    items: list[Any] = []

    def encode(item: Any) -> int:
        index = len(items)
        items.append(None)
        if isinstance(item, dict):
            items[index] = {f"_{encode(key)}": encode(value) for key, value in item.items()}
        elif isinstance(item, list):
            items[index] = [encode(value) for value in item]
        else:
            items[index] = item
        return index

    encode(value)
    return items


def test_decode_flattened_response_from_fixture() -> None:
    decoded = decode_flattened_response(json.loads(FIXTURE.read_text()))

    assert decoded["root"]["data"]["country"] == "VE"
    assert decoded["root"]["data"]["chatwoot"]["baseUrl"] == "https://support.example.test"

    route_data = decoded["routes/_index"]["data"]
    assert route_data["filters"]["query"] == "sample query"
    assert route_data["totalCount"] == 3
    assert len(route_data["persons"]) == 3
    assert route_data["persons"][0]["firstName"] == "Alex Example"


def test_client_search_decodes_root_data_and_uses_browser_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/_root.data"
        assert request.url.params["query"] == "sample query"
        assert "Mozilla/5.0" in request.headers["user-agent"]
        return httpx.Response(
            200,
            json=json.loads(FIXTURE.read_text()),
            headers={"content-type": "text/x-script"},
        )

    client = VenezuelaTeBuscaClient(
        "https://venezuelatebusca.com",
        transport=httpx.MockTransport(handler),
    )

    result = client.search("  sample query  ", limit=2)

    assert result.query == "sample query"
    assert result.total_count == 3
    assert len(result.persons) == 2
    assert result.persons[0].full_name == "Alex Example Rivera"
    assert result.persons[0].status == "found"


def test_client_search_keeps_fallecido_status_details_from_flattened_payload() -> None:
    payload = _flatten_remix_payload(
        {
            "root": {"data": {"country": "VE"}},
            "routes/_index": {
                "data": {
                    "filters": {"query": "Taylor Example"},
                    "pagination": {"nextCursor": None, "hasMore": False},
                    "persons": [
                        {
                            "id": "person-inline-001",
                            "firstName": "Taylor Example",
                            "lastName": "Status",
                            "idNumber": "TEST-9001",
                            "age": 75,
                            "status": "found",
                            "lastSeen": "Example District",
                            "description": "Synthetic medical-status test record.",
                            "photoUrl": "/media/photos/test-person-inline-001.webp",
                            "foundNote": "Deceased test note",
                            "hospitalName": "Example General Hospital",
                            "hospitalStatus": "deceased",
                        }
                    ],
                    "totalCount": 1,
                    "degraded": False,
                    "stats": {"found": 1},
                }
            },
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/_root.data"
        assert request.url.params["query"] == "Taylor Example"
        return httpx.Response(200, json=payload, headers={"content-type": "text/x-script"})

    client = VenezuelaTeBuscaClient(
        "https://venezuelatebusca.com",
        transport=httpx.MockTransport(handler),
    )

    result = client.search("Taylor Example", limit=10)

    assert result.query == "Taylor Example"
    assert result.total_count == 1
    assert len(result.persons) == 1
    person = result.persons[0]
    assert person.id == "person-inline-001"
    assert person.full_name == "Taylor Example Status"
    assert person.cedula_masked == "TEST-9001"
    assert person.found_note == "Deceased test note"
    assert person.hospital_status == "deceased"
    assert person.hospital_name == "Example General Hospital"


def test_person_accepts_finder_object_from_source_payload() -> None:
    person = VenezuelaTeBuscaPerson.model_validate(
        {
            "id": "person-inline-002",
            "firstName": "Jordan Example",
            "lastName": "Reporter",
            "status": "found",
            "finder": {
                "name": "Case Worker Example",
                "phone": "+15550101002",
            },
        }
    )

    assert person.full_name == "Jordan Example Reporter"
    assert person.finder == {
        "name": "Case Worker Example",
        "phone": "+15550101002",
    }
