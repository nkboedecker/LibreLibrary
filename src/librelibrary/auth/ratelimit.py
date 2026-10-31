"""A rate-limit store in the application's database.

Keeping counters in the database makes limits hold across workers without
another service. Each attempt writes a row, so this store is for sign-in, not
for every API request.
"""

import hashlib
from datetime import timedelta

from limits.storage import Storage
from sqlalchemy import Engine, delete, insert, select, update
from sqlalchemy.exc import DBAPIError

from librelibrary.db import is_constraint_violation, utcnow
from librelibrary.models import RateLimitCounter


def _hashed(key: str) -> str:
    """Hash a key, so that the table holds no usernames or addresses."""
    return hashlib.sha256(key.encode()).hexdigest()


class DatabaseStorage(Storage):
    """Fixed-window counters in the rate_limit_counter table."""

    STORAGE_SCHEME = ["librelibrary+database"]  # noqa: RUF012

    def __init__(self, engine: Engine) -> None:
        """Use the application's engine."""
        super().__init__(wrap_exceptions=False)
        self._engine = engine

    @property
    def base_exceptions(self) -> type[Exception]:
        """Return the errors this store can raise."""
        return DBAPIError

    def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        """Add to a window, starting a new one if the last has expired."""
        key_hash = _hashed(key)
        for _ in range(3):
            count = self._increment_live(key_hash, amount)
            if count is not None:
                return count
            if self._start_window(key_hash, expiry, amount):
                return amount
        return self._increment_live(key_hash, amount) or amount

    def _increment_live(self, key_hash: str, amount: int) -> int | None:
        """Add to an unexpired window, and return its count if there is one."""
        table = RateLimitCounter
        with self._engine.begin() as connection:
            result = connection.execute(
                update(table)
                .where(table.key_hash == key_hash, table.expires_at > utcnow())
                .values(count=table.count + amount)
            )
            if result.rowcount == 0:
                return None
            return connection.scalar(
                select(table.count).where(table.key_hash == key_hash)
            )

    def _start_window(self, key_hash: str, expiry: int, amount: int) -> bool:
        """Replace an expired window; return False if another worker got there."""
        now = utcnow()
        table = RateLimitCounter
        try:
            with self._engine.begin() as connection:
                connection.execute(delete(table).where(table.expires_at <= now))
                connection.execute(
                    insert(table).values(
                        key_hash=key_hash,
                        count=amount,
                        expires_at=now + timedelta(seconds=expiry),
                    )
                )
        except DBAPIError as error:
            if is_constraint_violation(error):
                return False
            raise
        return True

    def get(self, key: str) -> int:
        """Return a window's count, or zero if it has expired."""
        table = RateLimitCounter
        with self._engine.connect() as connection:
            count = connection.scalar(
                select(table.count).where(
                    table.key_hash == _hashed(key), table.expires_at > utcnow()
                )
            )
        return count or 0

    def get_expiry(self, key: str) -> float:
        """Return when a window ends, as a Unix timestamp."""
        table = RateLimitCounter
        with self._engine.connect() as connection:
            expires = connection.scalar(
                select(table.expires_at).where(table.key_hash == _hashed(key))
            )
        return (expires or utcnow()).timestamp()

    def check(self) -> bool:
        """Say whether the database answers."""
        with self._engine.connect() as connection:
            return connection.scalar(select(1)) == 1

    def reset(self) -> int | None:
        """Delete every window."""
        with self._engine.begin() as connection:
            return connection.execute(delete(RateLimitCounter)).rowcount

    def clear(self, key: str) -> None:
        """Delete one window."""
        table = RateLimitCounter
        with self._engine.begin() as connection:
            connection.execute(delete(table).where(table.key_hash == _hashed(key)))
