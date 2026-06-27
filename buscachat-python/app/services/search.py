from sqlalchemy import or_
from sqlmodel import Session, select

from app.models import MissingPerson


def find_missing_person_by_name(session: Session, name: str) -> MissingPerson | None:
    cleaned = " ".join(name.split())
    if not cleaned:
        return None

    exact = _first(
        session,
        select(MissingPerson).where(MissingPerson.full_name.ilike(cleaned)),
    )
    if exact:
        return exact

    tokens = [token for token in cleaned.split(" ") if token]
    if tokens:
        all_tokens = select(MissingPerson)
        for token in tokens:
            all_tokens = all_tokens.where(MissingPerson.full_name.ilike(f"%{token}%"))
        match = _first(session, all_tokens)
        if match:
            return match

        any_token = select(MissingPerson).where(
            or_(*(MissingPerson.full_name.ilike(f"%{token}%") for token in tokens))
        )
        return _first(session, any_token)

    return None


def _first(session: Session, statement):
    statement = statement.order_by(
        MissingPerson.source_date.desc().nullslast(),
        MissingPerson.id.desc(),
    ).limit(1)
    return session.exec(statement).first()
