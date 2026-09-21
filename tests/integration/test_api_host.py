from datetime import UTC, datetime

import pytest

from tests.integration.test_api_diner import API, DINER, SLUG, host_headers, join

HOST = f"{API}/{SLUG}/host"
LOGIN = "/api/v1/auth/login"
CLOSED_AT = datetime(2026, 9, 18, 15, 0, tzinfo=UTC)  # viernes 10:00 Lima


async def join_many(db, client, count):
    tokens = []
    for i in range(count):
        response = await join(client, name=f"Comensal {i + 1}", phone=f"98765432{i}")
        tokens.append(response.json()["token"])
        db.clock.advance(minutes=1)
    return tokens


async def test_login_returns_a_token_and_the_venue(db, client):
    venue = await db.create_venue()
    await db.create_user(venue.id, "terraza", "secreto")

    response = await client.post(LOGIN, json={"username": "terraza", "password": "secreto"})

    body = response.json()
    assert response.status_code == 200 and len(body["token"]) >= 20
    assert body["user"]["username"] == "terraza"
    assert body["user"]["venue"] == {"slug": SLUG, "name": "La Terraza Azul"}


async def test_wrong_credentials_are_a_401_that_does_not_say_which_part_failed(db, client):
    venue = await db.create_venue()
    await db.create_user(venue.id, "terraza", "secreto")

    wrong = await client.post(LOGIN, json={"username": "terraza", "password": "mala"})
    unknown = await client.post(LOGIN, json={"username": "nadie", "password": "secreto"})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert wrong.headers["WWW-Authenticate"] == "Bearer"


async def test_two_tablets_can_share_the_account_and_logout_closes_only_one(db, client):
    venue = await db.create_venue()
    await db.create_user(venue.id, "terraza", "secreto")
    creds = {"username": "terraza", "password": "secreto"}
    a = {"Authorization": f"Bearer {(await client.post(LOGIN, json=creds)).json()['token']}"}
    b = {"Authorization": f"Bearer {(await client.post(LOGIN, json=creds)).json()['token']}"}

    assert (await client.get("/api/v1/auth/me", headers=a)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=b)).status_code == 200
    assert (await client.post("/api/v1/auth/logout", headers=a)).status_code == 204

    assert (await client.get("/api/v1/auth/me", headers=a)).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=b)).json()["username"] == "terraza"


async def test_login_is_rate_limited_per_username(db, make_client):
    limited = make_client(rate_limit=True)
    venue = await db.create_venue()
    await db.create_user(venue.id, "terraza", "secreto")

    codes = [
        (await limited.post(LOGIN, json={"username": "terraza", "password": "mala"})).status_code for _ in range(6)
    ]

    assert codes == [401] * 5 + [429]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/queue"),
        ("GET", "/stream"),
        ("POST", "/pause"),
        ("POST", "/resume"),
        ("PUT", "/schedule"),
        ("POST", "/entries/1/call"),
        ("POST", "/entries/1/seat"),
        ("POST", "/entries/1/no-show"),
        ("POST", "/entries/1/remove"),
    ],
)
async def test_every_host_endpoint_requires_a_valid_token(db, client, method, path):
    await db.create_venue()

    missing = await client.request(method, f"{HOST}{path}")
    invalid = await client.request(method, f"{HOST}{path}", headers={"Authorization": "Bearer inventado"})

    assert missing.status_code == invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_token"


async def test_a_host_can_only_operate_on_their_own_venue(db, client):
    terraza = await db.create_venue()
    await db.create_venue(slug="cuatro-vientos", name="Cuatro Vientos")
    headers = await host_headers(db, client, terraza)

    other = await client.get(f"{API}/cuatro-vientos/host/queue", headers=headers)
    unknown = await client.get(f"{API}/no-existe/host/queue", headers=headers)

    assert other.status_code == 403 and other.json()["error"]["code"] == "venue_forbidden"
    assert unknown.status_code == 403


async def test_the_queue_lists_waiting_and_called_in_arrival_order(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    await join_many(db, client, 3)

    body = (await client.get(f"{HOST}/queue", headers=headers)).json()

    assert [r["ticket"] for r in body["rows"]] == [1, 2, 3]
    assert (body["waiting"], body["called"]) == (3, 0)
    assert body["finished"] == {"seated": 0, "left": 0, "no_show": 0}
    first = body["rows"][0]
    assert first["phone_e164"] == "+51987654320" and first["phone_display"] == "+51 987 654 320"
    assert first["status"] == "waiting" and first["hold_ends_at"] is None and first["hold_expired"] is False
    assert body["venue"]["list_status"]["kind"] == "open" and len(body["venue"]["schedule"]) == 7
    assert body["venue"]["schedule"][0] == {
        "weekday": 0,
        "is_open": True,
        "start": "11:00",
        "end": "01:00",
        "crosses_midnight": True,
    }


async def test_call_seat_flow_updates_the_diner_and_returns_the_queue(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    first, second = await join_many(db, client, 2)
    rows = (await client.get(f"{HOST}/queue", headers=headers)).json()["rows"]

    called = await client.post(f"{HOST}/entries/{rows[0]['id']}/call", headers=headers)

    assert called.status_code == 200
    row = called.json()["rows"][0]
    assert row["status"] == "called" and row["hold_ends_at"] is not None
    assert (called.json()["waiting"], called.json()["called"]) == (1, 1)
    mine = (await client.get(f"{DINER}/entries/{first}")).json()
    assert mine["status"] == "called" and mine["position"] is None and mine["hold_ends_at"] == row["hold_ends_at"]
    assert (await client.get(f"{DINER}/entries/{second}")).json()["position"] == 1  # el de atrás avanza

    seated = await client.post(f"{HOST}/entries/{rows[0]['id']}/seat", headers=headers)
    assert seated.json()["finished"]["seated"] == 1 and len(seated.json()["rows"]) == 1
    assert (await client.get(f"{DINER}/entries/{first}")).json()["status"] == "seated"


async def test_repeating_an_action_is_a_200_without_double_effect(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    await join_many(db, client, 1)
    entry_id = (await client.get(f"{HOST}/queue", headers=headers)).json()["rows"][0]["id"]

    first = await client.post(f"{HOST}/entries/{entry_id}/call", headers=headers)
    db.clock.advance(minutes=2)
    again = await client.post(f"{HOST}/entries/{entry_id}/call", headers=headers)

    assert first.status_code == again.status_code == 200
    assert first.json()["rows"][0]["called_at"] == again.json()["rows"][0]["called_at"]


async def test_impossible_actions_are_409_and_unknown_or_foreign_entries_are_404(db, client):
    terraza = await db.create_venue()
    cuatro = await db.create_venue(slug="cuatro-vientos", name="Cuatro Vientos")
    headers = await host_headers(db, client, terraza)
    await join_many(db, client, 1)
    foreign = (await join(client, slug="cuatro-vientos", phone="987000111")).json()
    async with db.scope() as w:
        foreign_id = (await w.entries.get_by_token(foreign["token"])).id
    entry_id = (await client.get(f"{HOST}/queue", headers=headers)).json()["rows"][0]["id"]

    seat_waiting = await client.post(f"{HOST}/entries/{entry_id}/seat", headers=headers)
    no_show_waiting = await client.post(f"{HOST}/entries/{entry_id}/no-show", headers=headers)
    foreign_entry = await client.post(f"{HOST}/entries/{foreign_id}/call", headers=headers)
    unknown = await client.post(f"{HOST}/entries/99999/call", headers=headers)

    assert seat_waiting.status_code == no_show_waiting.status_code == 409
    assert seat_waiting.json()["error"]["code"] == "invalid_transition"
    assert foreign_entry.status_code == unknown.status_code == 404
    assert cuatro.id != terraza.id


async def test_no_show_and_remove_close_the_entry_and_free_the_phone(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    await join_many(db, client, 2)
    rows = (await client.get(f"{HOST}/queue", headers=headers)).json()["rows"]

    await client.post(f"{HOST}/entries/{rows[0]['id']}/call", headers=headers)
    no_show = await client.post(f"{HOST}/entries/{rows[0]['id']}/no-show", headers=headers)
    removed = await client.post(f"{HOST}/entries/{rows[1]['id']}/remove", headers=headers)

    assert no_show.json()["finished"]["no_show"] == 1
    assert removed.json()["finished"]["left"] == 1 and removed.json()["rows"] == []
    rejoin = await join(client, phone="987654320")
    assert rejoin.status_code == 201 and rejoin.json()["ticket"] == 3  # entra al final con ticket nuevo


async def test_the_host_sees_that_the_diner_is_on_the_way_and_when_the_hold_expired(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    (token,) = await join_many(db, client, 1)
    entry_id = (await client.get(f"{HOST}/queue", headers=headers)).json()["rows"][0]["id"]
    await client.post(f"{HOST}/entries/{entry_id}/call", headers=headers)
    await client.post(f"{DINER}/entries/{token}/on-the-way")

    db.clock.advance(minutes=10, seconds=1)
    row = (await client.get(f"{HOST}/queue", headers=headers)).json()["rows"][0]

    assert row["on_the_way"] is True and row["hold_expired"] is True and row["status"] == "called"


async def test_pause_and_resume(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)

    paused = await client.post(f"{HOST}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["paused"] is True and paused.json()["list_status"]["kind"] == "paused"
    assert (await client.get(f"{DINER}/status")).json()["status"]["kind"] == "paused"
    assert (await join(client)).json()["error"]["code"] == "list_paused"

    resumed = await client.post(f"{HOST}/resume", headers=headers)
    assert resumed.json()["paused"] is False and resumed.json()["list_status"]["kind"] == "open"
    assert (await join(client)).status_code == 201


async def test_saving_a_schedule_changes_when_the_list_accepts_people(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    day = {"is_open": True, "start": "09:00", "end": "17:00"}

    response = await client.put(f"{HOST}/schedule", headers=headers, json={"days": [day] * 7})

    assert response.status_code == 200
    body = response.json()
    assert body["schedule"][4] == {
        "weekday": 4,
        "is_open": True,
        "start": "09:00",
        "end": "17:00",
        "crosses_midnight": False,
    }
    assert body["list_status"] == {
        "kind": "closed",
        "closes_at": None,
        "next_open": {"day_offset": 1, "weekday": 5, "time": "09:00"},
    }  # viernes 20:00 Lima, ya pasó el cierre de las 17:00
    assert (await join(client)).json()["error"]["code"] == "list_closed"


async def test_invalid_schedules_are_rejected(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    good = {"is_open": True, "start": "11:00", "end": "01:00"}
    equal = {"is_open": True, "start": "11:00", "end": "11:00"}

    same_time = await client.put(f"{HOST}/schedule", headers=headers, json={"days": [equal] + [good] * 6})
    six_days = await client.put(f"{HOST}/schedule", headers=headers, json={"days": [good] * 6})

    assert same_time.status_code == 422
    assert same_time.json()["error"]["code"] == "schedule_start_equals_end"
    assert six_days.status_code == 422 and six_days.json()["error"]["code"] == "validation_error"
    assert (await client.get(f"{HOST}/queue", headers=headers)).json()["venue"]["schedule"][0]["end"] == "01:00"


async def test_a_closed_list_still_shows_the_people_who_are_already_in_it(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    await join_many(db, client, 2)
    db.clock.set(datetime(2026, 9, 19, 7, 0, tzinfo=UTC))  # sábado 02:00 Lima, ya cerró

    body = (await client.get(f"{HOST}/queue", headers=headers)).json()

    assert body["venue"]["list_status"]["kind"] == "closed" and len(body["rows"]) == 2
    entry_id = body["rows"][0]["id"]
    assert (await client.post(f"{HOST}/entries/{entry_id}/call", headers=headers)).status_code == 200
