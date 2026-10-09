"""What one connection is currently listening to.

A thin wrapper over a set of :class:`Topic`, worth its own module for two
reasons: the cap belongs next to the thing it caps, and the add is all-or-nothing.

**All-or-nothing matters.** A ``subscribe`` naming eight topics where the fifth
would breach the cap must add none of them. Half-applying it would leave the
client's idea of its own subscriptions permanently wrong, and since ``ack``
reports the whole resulting set, the disagreement would be invisible until the
missing stream was noticed by a human.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from chartnexus.contexts.realtime_delivery.domain.topics import Topic


class TopicLimitExceededError(Exception):
    """Adding these topics would take the connection past its cap."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"A connection may hold at most {limit} topics.")
        self.limit = limit


class SubscriptionSet:
    """The topics one connection holds. Not thread-safe; one per connection."""

    __slots__ = ("_limit", "_topics")

    def __init__(self, *, limit: int) -> None:
        self._limit = limit
        self._topics: set[Topic] = set()

    def add(self, topics: Iterable[Topic]) -> None:
        """Add all of ``topics``, or none.

        Already-held topics are not re-counted, so re-sending the same set after
        a reconnect can never breach the cap.
        """
        candidate = self._topics | set(topics)
        if len(candidate) > self._limit:
            raise TopicLimitExceededError(self._limit)
        self._topics = candidate

    def remove(self, topics: Iterable[Topic]) -> None:
        """Drop ``topics``. Ones not held are ignored, never an error."""
        self._topics -= set(topics)

    def matching(self, kind: str, symbol: str) -> Topic | None:
        """The topic that entitles this connection to an event, if any.

        Returns the *held* topic — which may be a wildcard — so a caller can log
        what the delivery was owed to. A connection holding both
        ``snapshots:NIFTY`` and ``snapshots:*`` still gets one frame, because
        this answers with the first match rather than all of them.
        """
        for topic in self._topics:
            if topic.matches(kind, symbol):
                return topic
        return None

    def as_wire(self) -> tuple[str, ...]:
        """The set in its contract form, for an ``ack``."""
        return tuple(str(topic) for topic in self._topics)

    def __len__(self) -> int:
        return len(self._topics)

    def __iter__(self) -> Iterator[Topic]:
        return iter(self._topics)

    def __contains__(self, topic: object) -> bool:
        return topic in self._topics
