from datetime import UTC, datetime

from app.shared.application.ports import Clock


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
