from datetime import UTC, datetime

import pytest

from app.waitlist.domain.enums import EntryStatus

API = "/api/v1/venues"
SLUG = "la-terraza-azul"
DINER = f"{API}/{SLUG}/diner"
JOIN_BODY = {"name": "Carla", "phone": "987 654 321", "party_size": 2, "consent": True}

ENTRY_KEYS = {
    "token",
    "ticket",
    "name",
    "party_size",
    "phone_display",
    "status",
    "position",
    "eta",
    "hold_ends_at",
    "on_the_way",
    "venue",
    "server_time",
}
CLOSED_AT = datetime(2026, 9, 18, 15, 0, tzinfo=UTC)  # viernes 10:00 Lima


async def join(client, slug=SLUG, **overrides):
    return await client.post(f"{API}/{slug}/diner/join", json={**JOIN_BODY, **overrides})


async def host_headers(db, client, venue, username="terraza"):
    await db.create_user(venue.id, username, "secreto")
    login = await client.post("/api/v1/auth/login", json={"username": username, "password": "secreto"})
    return {"Authorization": f"Bearer {login.json()['token']}"}


async def test_health(client):
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_venue_status_for_an_open_list(db, client):
    await db.create_venue()

    response = await client.get(f"{DINER}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["venue"] == {
        "slug": SLUG,
        "name": "La Terraza Azul",
        "country_code": "PE",
        "phone_prefix": "+51",
    }
    assert body["status"] == {"kind": "open", "closes_at": "01:00", "next_open": None}
    assert body["server_time"] == "2026-09-19T01:00:00Z"


async def test_venue_status_when_closed_says_when_it_opens(db, client):
    await db.create_venue()
    db.clock.set(CLOSED_AT)

    status = (await client.get(f"{DINER}/status")).json()["status"]

    assert status == {
        "kind": "closed",
        "closes_at": None,
        "next_open": {"day_offset": 0, "weekday": 4, "time": "11:00"},
    }


async def test_unknown_venue_uses_the_common_error_format(client):
    response = await client.get(f"{API}/no-existe/diner/status")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "venue_not_found", "message": "No encontramos ese local.", "field": None}
    }


async def test_join_creates_the_entry_and_returns_the_turn(db, client):
    await db.create_venue()

    response = await join(client)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == ENTRY_KEYS | {"already_in_queue"}
    assert body["already_in_queue"] is False
    assert (body["ticket"], body["name"], body["party_size"], body["status"]) == (1, "Carla", 2, "waiting")
    assert body["phone_display"] == "+51 987 654 321"
    assert (body["position"], body["eta"]) == (1, {"min": 5, "max": 10})
    assert body["hold_ends_at"] is None and body["on_the_way"] is False
    assert body["venue"] == {"slug": SLUG, "name": "La Terraza Azul"}


async def test_joining_again_with_the_same_phone_returns_the_same_turn_with_200(db, client):
    await db.create_venue()
    first = (await join(client)).json()

    again = await join(client, phone="+51987654321", name="Otra")

    assert again.status_code == 200
    assert again.json()["already_in_queue"] is True
    assert again.json()["token"] == first["token"] and again.json()["ticket"] == 1


@pytest.mark.parametrize(
    ("overrides", "code", "field"),
    [
        ({"name": "   "}, "name_required", "name"),
        ({"phone": "12345"}, "invalid_phone", "phone"),
        ({"party_size": 21}, "party_size_out_of_range", "party_size"),
        ({"party_size": 0}, "party_size_out_of_range", "party_size"),
        ({"consent": False}, "consent_required", "consent"),
    ],
)
async def test_join_validation_errors_carry_a_code_and_the_field(db, client, overrides, code, field):
    await db.create_venue()

    response = await join(client, **overrides)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code and response.json()["error"]["field"] == field


async def test_malformed_body_is_a_422_in_the_same_format(db, client):
    await db.create_venue()

    response = await client.post(f"{DINER}/join", json={"name": "Carla"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["field"] == "phone"


async def test_cannot_join_outside_hours_or_while_paused(db, client):
    venue = await db.create_venue()
    db.clock.set(CLOSED_AT)
    closed = await join(client)
    assert (closed.status_code, closed.json()["error"]["code"]) == (409, "list_closed")

    db.clock.set(datetime(2026, 9, 19, 1, 0, tzinfo=UTC))
    async with db.scope() as w:
        await w.set_paused.execute(venue.id, True)
    paused = await join(client)
    assert (paused.status_code, paused.json()["error"]["code"]) == (409, "list_paused")


async def test_get_my_turn_and_the_token_only_works_in_its_own_venue(db, client):
    await db.create_venue()
    await db.create_venue(slug="cuatro-vientos", name="Cuatro Vientos")
    token = (await join(client)).json()["token"]

    mine = await client.get(f"{DINER}/entries/{token}")
    other_venue = await client.get(f"{API}/cuatro-vientos/diner/entries/{token}")
    unknown = await client.get(f"{DINER}/entries/inventado")

    assert mine.status_code == 200 and mine.json()["token"] == token
    assert other_venue.status_code == 404 and unknown.status_code == 404
    assert other_venue.json()["error"]["code"] == "entry_not_found"


async def test_a_diner_never_sees_data_from_other_diners(db, client):
    await db.create_venue()
    await join(client, name="Secreta Persona", phone="987111222")
    mine = await join(client, name="Yo", phone="987333444")

    body = (await client.get(f"{DINER}/entries/{mine.json()['token']}")).json()

    assert set(body) == ENTRY_KEYS
    assert body["position"] == 2  # sabe cuántos hay delante, no quiénes
    text = (await client.get(f"{DINER}/entries/{mine.json()['token']}")).text
    assert "Secreta" not in text and "987111222" not in text and "+51987111222" not in text


async def test_cancel_is_idempotent_and_cannot_undo_a_final_state(db, client):
    venue = await db.create_venue()
    token = (await join(client)).json()["token"]

    first = await client.post(f"{DINER}/entries/{token}/cancel")
    again = await client.post(f"{DINER}/entries/{token}/cancel")

    assert (first.status_code, first.json()["status"]) == (200, "cancelled")
    assert (again.status_code, again.json()["status"]) == (200, "cancelled")
    assert first.json()["position"] is None

    async with db.scope() as w:  # un turno ya sentado no se puede cancelar
        entry = (await join(client, phone="987000111")).json()
        user = await db.create_user(venue.id)
        await w.change_status.execute(venue.id, user.id, await _entry_id(db, entry["token"]), EntryStatus("called"))
        await w.change_status.execute(venue.id, user.id, await _entry_id(db, entry["token"]), EntryStatus("seated"))
    conflict = await client.post(f"{DINER}/entries/{entry['token']}/cancel")
    assert (conflict.status_code, conflict.json()["error"]["code"]) == (409, "invalid_transition")


async def test_on_the_way_needs_a_call_first_and_does_not_change_the_state(db, client):
    venue = await db.create_venue()
    user = await db.create_user(venue.id)
    token = (await join(client)).json()["token"]

    early = await client.post(f"{DINER}/entries/{token}/on-the-way")
    assert (early.status_code, early.json()["error"]["code"]) == (409, "invalid_transition")

    async with db.scope() as w:
        await w.change_status.execute(venue.id, user.id, await _entry_id(db, token), EntryStatus("called"))
    ends_at = (await client.get(f"{DINER}/entries/{token}")).json()["hold_ends_at"]
    db.clock.advance(minutes=3)

    response = await client.post(f"{DINER}/entries/{token}/on-the-way")

    body = response.json()
    assert response.status_code == 200 and body["status"] == "called" and body["on_the_way"] is True
    assert body["hold_ends_at"] == ends_at  # no extiende el plazo


async def test_lookup_recovers_the_turn_and_hides_which_field_failed(db, client):
    await db.create_venue()
    token = (await join(client)).json()["token"]

    found = await client.post(f"{DINER}/tickets/lookup", json={"ticket": 1, "phone": "987 654 321"})
    assert found.status_code == 200 and found.json()["token"] == token

    for body in ({"ticket": 1, "phone": "987654322"}, {"ticket": 9, "phone": "987654321"}, {"ticket": 1, "phone": "1"}):
        missing = await client.post(f"{DINER}/tickets/lookup", json=body)
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "ticket_not_found"


async def test_rate_limit_on_join_returns_429_with_retry_after(db, make_client):
    limited = make_client(rate_limit=True)
    await db.create_venue()

    statuses = [(await join(limited)).status_code for _ in range(10)]
    blocked = await join(limited)

    assert statuses == [201] + [200] * 9
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) >= 1


async def _entry_id(db, token: str) -> int:
    async with db.scope() as w:
        return (await w.entries.get_by_token(token)).id
