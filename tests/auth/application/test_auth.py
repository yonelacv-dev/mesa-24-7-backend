from datetime import timedelta

import pytest

from app.auth.application.errors import InvalidCredentials, InvalidToken
from app.auth.domain.tokens import hash_token


async def login(world, password="secreto", device="Tablet mostrador"):
    return await world.login.execute("terraza", password, device)


async def test_login_returns_a_token_and_stores_only_its_hash(world):
    result = await login(world)

    assert result.token == "token-1"
    assert (result.user.user_id, result.user.venue_id, result.user.username) == (10, 1, "terraza")
    (session,) = world.sessions.items
    assert session.token_hash == hash_token(result.token) and session.token_hash != result.token
    assert session.device_label == "Tablet mostrador" and session.is_active
    assert world.user.last_login_at == world.clock.now()


async def test_wrong_password_is_rejected_and_opens_no_session(world):
    with pytest.raises(InvalidCredentials):
        await login(world, password="mala")
    assert world.sessions.items == []


async def test_unknown_user_is_rejected_like_a_wrong_password_and_costs_the_same_time(world):
    with pytest.raises(InvalidCredentials) as unknown:
        await world.login.execute("nadie", "secreto")
    with pytest.raises(InvalidCredentials) as wrong:
        await login(world, password="mala")

    assert unknown.value.code == wrong.value.code and unknown.value.message == wrong.value.message
    assert world.hasher.burns == 1  # se gastó tiempo de verificación aunque el usuario no exista


async def test_inactive_user_cannot_log_in(world):
    world.user.is_active = False
    with pytest.raises(InvalidCredentials):
        await login(world)


async def test_two_tablets_can_use_the_same_account_at_once(world):
    first = await login(world, device="Tablet 1")
    second = await login(world, device="Tablet 2")

    assert first.token != second.token
    assert len(world.sessions.items) == 2 and all(s.is_active for s in world.sessions.items)
    assert (await world.authenticate.execute(first.token)).venue_id == 1
    assert (await world.authenticate.execute(second.token)).venue_id == 1  # el segundo login no cerró el primero


async def test_valid_token_identifies_the_user_and_venue(world):
    token = (await login(world)).token

    user = await world.authenticate.execute(token)

    assert (user.user_id, user.venue_id, user.username) == (10, 1, "terraza")


@pytest.mark.parametrize("token", ["", "inventado", "token-999"])
async def test_unknown_token_is_rejected(world, token):
    with pytest.raises(InvalidToken):
        await world.authenticate.execute(token)


async def test_sessions_do_not_expire_over_time(world):
    token = (await login(world)).token
    world.clock.advance(days=365)

    assert (await world.authenticate.execute(token)).user_id == 10


async def test_logout_revokes_only_that_tablet(world):
    first = await login(world)
    second = await login(world)

    await world.logout.execute(first.token)

    with pytest.raises(InvalidToken):
        await world.authenticate.execute(first.token)
    assert (await world.authenticate.execute(second.token)).user_id == 10
    assert world.sessions.items[0].revoked_at == world.clock.now()


async def test_logout_is_idempotent_and_tolerates_unknown_tokens(world):
    token = (await login(world)).token
    await world.logout.execute(token)
    revoked_at = world.sessions.items[0].revoked_at
    world.clock.advance(minutes=5)

    await world.logout.execute(token)
    await world.logout.execute("inventado")

    assert world.sessions.items[0].revoked_at == revoked_at


async def test_deactivating_the_user_kills_every_session(world):
    token = (await login(world)).token
    world.user.is_active = False

    with pytest.raises(InvalidToken):
        await world.authenticate.execute(token)


async def test_last_used_is_refreshed_at_most_once_per_minute(world):
    token = (await login(world)).token
    session = world.sessions.items[0]
    created = session.last_used_at
    commits = world.uow.commits

    world.clock.advance(seconds=30)
    await world.authenticate.execute(token)
    assert session.last_used_at == created and world.uow.commits == commits  # sin escritura

    world.clock.advance(minutes=2)
    await world.authenticate.execute(token)
    assert session.last_used_at == world.clock.now() and world.uow.commits == commits + 1
    assert world.clock.now() - created >= timedelta(minutes=2)
