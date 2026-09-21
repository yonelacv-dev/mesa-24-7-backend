from enum import Enum

from app.waitlist.domain.enums import Actor, EntryStatus
from app.waitlist.domain.errors import ActorNotAllowed, InvalidTransition

ALLOWED_TRANSITIONS: dict[EntryStatus, frozenset[EntryStatus]] = {
    EntryStatus.WAITING: frozenset({EntryStatus.CALLED, EntryStatus.CANCELLED, EntryStatus.REMOVED}),
    EntryStatus.CALLED: frozenset(
        {EntryStatus.SEATED, EntryStatus.NO_SHOW, EntryStatus.CANCELLED, EntryStatus.REMOVED}
    ),
}

# Quién puede provocar cada estado destino.
ALLOWED_ACTORS: dict[EntryStatus, frozenset[Actor]] = {
    EntryStatus.CALLED: frozenset({Actor.HOST}),
    EntryStatus.SEATED: frozenset({Actor.HOST}),
    EntryStatus.NO_SHOW: frozenset({Actor.HOST}),
    EntryStatus.REMOVED: frozenset({Actor.HOST}),
    EntryStatus.CANCELLED: frozenset({Actor.DINER}),
}


class Decision(Enum):
    APPLY = "apply"
    NOOP = "noop"


def decide(current: EntryStatus, target: EntryStatus, actor: Actor) -> Decision:
    """Repetir una acción ya aplicada es NOOP (idempotente); una transición imposible lanza."""
    if actor not in ALLOWED_ACTORS.get(target, frozenset()):
        if target not in ALLOWED_ACTORS:
            raise InvalidTransition("invalid_transition", f"No se puede pasar a {target.value}.")
        raise ActorNotAllowed("actor_not_allowed", f"{actor.value} no puede pasar una entrada a {target.value}.")
    if current == target:
        return Decision.NOOP
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition("invalid_transition", f"No se puede pasar de {current.value} a {target.value}.")
    return Decision.APPLY
