from enum import StrEnum


class EntryStatus(StrEnum):
    WAITING = "waiting"
    CALLED = "called"
    SEATED = "seated"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    REMOVED = "removed"

    @property
    def is_active(self) -> bool:
        return self in ACTIVE_STATUSES

    @property
    def is_final(self) -> bool:
        return self in FINAL_STATUSES


ACTIVE_STATUSES = frozenset({EntryStatus.WAITING, EntryStatus.CALLED})
FINAL_STATUSES = frozenset({EntryStatus.SEATED, EntryStatus.CANCELLED, EntryStatus.NO_SHOW, EntryStatus.REMOVED})


class Actor(StrEnum):
    DINER = "diner"
    HOST = "host"


class EventType(StrEnum):
    JOINED = "joined"
    CALLED = "called"
    SEATED = "seated"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"
    REMOVED = "removed"
    ON_THE_WAY = "on_the_way"
