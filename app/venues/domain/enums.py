from enum import StrEnum


class ListStatusKind(StrEnum):
    OPEN = "open"
    PAUSED = "paused"
    CLOSED = "closed"
