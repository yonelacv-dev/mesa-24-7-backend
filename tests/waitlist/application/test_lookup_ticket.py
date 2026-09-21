import pytest

from app.shared.application.errors import NotFound
from app.waitlist.domain.enums import EntryStatus
from tests.support.world import OTHER_SLUG


async def test_ticket_and_phone_recover_the_turn(world):
    joined = (await world.join(phone="987654321")).entry

    view = await world.lookup(ticket=1, phone="987 654 321")

    assert view.entry is joined
    assert view.entry.public_token == joined.public_token  # el front lo guarda para volver directo
    assert view.position == 1


@pytest.mark.parametrize(
    ("ticket", "phone"),
    [
        (1, "987654322"),  # teléfono de otra persona
        (2, "987654321"),  # ticket que no es de ese teléfono
        (99, "987654321"),  # ticket inexistente
        (1, "12345"),  # teléfono inválido
        (1, ""),
    ],
)
async def test_wrong_data_always_gives_the_same_not_found(world, ticket, phone):
    await world.join(phone="987654321")
    await world.join(name="Otro", phone="987654322")

    with pytest.raises(NotFound) as error:
        await world.lookup(ticket=ticket, phone=phone)

    assert error.value.code == "ticket_not_found"


async def test_ticket_number_alone_is_not_enough(world):
    await world.join(phone="987654321")
    with pytest.raises(NotFound):
        await world.lookup(ticket=1, phone="999999999")


async def test_ticket_of_another_venue_is_not_found(world):
    await world.join(phone="987654321")
    with pytest.raises(NotFound):
        await world.lookup(ticket=1, phone="987654321", slug=OTHER_SLUG)


async def test_an_ended_ticket_still_shows_its_final_state_without_position(world):
    entry = (await world.join(phone="987654321")).entry
    await world.leave_queue.execute(entry.public_token)

    view = await world.lookup(ticket=1, phone="987654321")

    assert view.entry.status is EntryStatus.CANCELLED
    assert view.position is None and view.eta is None
