import pytest

from app.waitlist.domain.enums import FINAL_STATUSES, Actor, EntryStatus
from app.waitlist.domain.errors import ActorNotAllowed, InvalidTransition
from app.waitlist.domain.state_machine import Decision, decide

W, C = EntryStatus.WAITING, EntryStatus.CALLED
SEATED, CANCELLED, NO_SHOW, REMOVED = (
    EntryStatus.SEATED,
    EntryStatus.CANCELLED,
    EntryStatus.NO_SHOW,
    EntryStatus.REMOVED,
)
HOST, DINER = Actor.HOST, Actor.DINER


@pytest.mark.parametrize(
    ("current", "target", "actor"),
    [
        (W, C, HOST),
        (W, CANCELLED, DINER),
        (W, REMOVED, HOST),
        (C, SEATED, HOST),
        (C, NO_SHOW, HOST),
        (C, CANCELLED, DINER),
        (C, REMOVED, HOST),
    ],
)
def test_valid_transitions_apply(current, target, actor):
    assert decide(current, target, actor) is Decision.APPLY


@pytest.mark.parametrize(
    ("current", "target", "actor"),
    [
        (W, SEATED, HOST),  # hay que llamar antes de sentar
        (W, NO_SHOW, HOST),  # no vino solo aplica a quien fue llamado
        (C, W, HOST),  # no se vuelve a esperar
    ],
)
def test_invalid_transitions_raise(current, target, actor):
    with pytest.raises(InvalidTransition):
        decide(current, target, actor)


@pytest.mark.parametrize("final", sorted(FINAL_STATUSES))
@pytest.mark.parametrize("target", [C, SEATED, NO_SHOW, REMOVED])
def test_final_states_have_no_exit_for_host(final, target):
    if final == target:
        assert decide(final, target, HOST) is Decision.NOOP
    else:
        with pytest.raises(InvalidTransition):
            decide(final, target, HOST)


@pytest.mark.parametrize("final", sorted(FINAL_STATUSES - {CANCELLED}))
def test_final_states_have_no_exit_for_diner_cancel(final):
    with pytest.raises(InvalidTransition):
        decide(final, CANCELLED, DINER)


@pytest.mark.parametrize("target", [C, SEATED, NO_SHOW, REMOVED])
def test_diner_cannot_do_host_actions(target):
    with pytest.raises(ActorNotAllowed):
        decide(C, target, DINER)


def test_host_cannot_cancel_on_behalf_of_diner():
    with pytest.raises(ActorNotAllowed):
        decide(W, CANCELLED, HOST)


@pytest.mark.parametrize(
    ("current", "target", "actor"),
    [(C, C, HOST), (SEATED, SEATED, HOST), (CANCELLED, CANCELLED, DINER), (REMOVED, REMOVED, HOST)],
)
def test_repeating_an_action_is_a_noop(current, target, actor):
    assert decide(current, target, actor) is Decision.NOOP
