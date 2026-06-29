from app.adapters.sos_venezuela import SOSVenezuelaAdapter


def test_sos_venezuela_adapter_normalizes_source_payload() -> None:
    adapter = SOSVenezuelaAdapter("https://example.test")

    record = adapter._normalize(
        {
            "id": "a407d211-ceff-47e4-b498-10cf5a5f61c7",
            "status": "seeking_info",
            "cedula_masked": "TEST-****001",
            "display_name": " Alex Example Rivera ",
            "municipio": "Sample City",
            "parroquia": "Demo Parish",
            "hospital_name": "Example General Hospital",
            "photo_path": "https://example.test/photo.webp",
            "source_date": "2026-06-27T19:15:06.924Z",
        }
    )

    assert record.source == "sosvenezuela2026"
    assert record.external_id == "a407d211-ceff-47e4-b498-10cf5a5f61c7"
    assert record.full_name == "Alex Example Rivera"
    assert record.status == "missing"
    assert record.raw_status == "seeking_info"
    assert record.last_known_location == "Example General Hospital · Sample City · Demo Parish"
