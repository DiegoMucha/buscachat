from sqlalchemy import or_
from sqlmodel import Session, select

from app.models import MissingPerson


def find_missing_person_by_name(session: Session, name: str) -> MissingPerson | None:
    matches = find_missing_people_by_name(session, name, limit=1)
    return matches[0] if matches else None


def find_missing_people_by_name(
    session: Session,
    name: str,
    *,
    limit: int = 10,
) -> list[MissingPerson]:
    cleaned = " ".join(name.split())
    if not cleaned or limit <= 0:
        return []

    results: list[MissingPerson] = []
    seen_ids: set[int] = set()

    def add_matches(statement) -> None:
        if len(results) >= limit:
            return
        for person in session.exec(_ordered(statement).limit(limit - len(results))).all():
            if person.id in seen_ids:
                continue
            if person.id is not None:
                seen_ids.add(person.id)
            results.append(person)

    add_matches(select(MissingPerson).where(MissingPerson.full_name.ilike(cleaned)))

    tokens = [token for token in cleaned.split(" ") if token]
    if tokens:
        all_tokens = select(MissingPerson)
        for token in tokens:
            all_tokens = all_tokens.where(MissingPerson.full_name.ilike(f"%{token}%"))
        add_matches(all_tokens)

        any_token = select(MissingPerson).where(or_(*(MissingPerson.full_name.ilike(f"%{token}%") for token in tokens)))
        add_matches(any_token)

    return results


def find_missing_person_by_cedula(session: Session, cedula: str) -> MissingPerson | None:
    cleaned = cedula.strip()
    if not cleaned:
        return None

    digits = cleaned.upper().lstrip("VE-").strip()
    return _first(
        session,
        select(MissingPerson).where(MissingPerson.cedula_masked.ilike(f"%{digits}%")),
    )


def _first(session: Session, statement):
    return session.exec(_ordered(statement).limit(1)).first()


def _ordered(statement):
    return statement.order_by(
        MissingPerson.source_date.desc().nullslast(),
        MissingPerson.id.desc(),
    )
