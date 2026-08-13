"""Who is watching what.

Both of the service's streams — a page's log and a page's file changes — have
the same problem underneath: a set of subscribers per key, a subscriber that
must be forgotten the moment its client hangs up, and a fan-out that costs
nothing when nobody is there. Only the *payload* differs, and each hub keeps
its own, because what to do with a subscriber who cannot keep up is a question
about the payload rather than about the registry.

A key is a *MusicorpusPage* ID today. It is a plain string so that a stream
scoped to a *User* rather than a page — which is what a client watching several
pages at once will want — needs nothing here changed.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Generic, TypeVar

S = TypeVar("S")


class Watchers(Generic[S]):
    """The subscribers of each key, and nothing about what they subscribe to."""

    def __init__(self, make: Callable[[str], S]):
        self._make = make
        self._watchers: dict[str, set[S]] = {}

    @contextmanager
    def watch(self, key: str) -> Iterator[S]:
        """Subscribe for as long as the block runs.

        A context manager because forgetting to unsubscribe is how a
        disconnected client goes on being fed forever; the stream's exit — a
        client hanging up included — is the end of the subscription.
        """
        subscription = self._make(key)
        self._watchers.setdefault(key, set()).add(subscription)
        try:
            yield subscription
        finally:
            watching = self._watchers.get(key)
            if watching is not None:
                watching.discard(subscription)
                if not watching:
                    del self._watchers[key]

    def of(self, key: str) -> list[S]:
        """Everyone watching this key, as a snapshot.

        A copy, so that a subscription ending while a message is being fanned
        out does not change the set underneath the loop.
        """
        return list(self._watchers.get(key, ()))

    def any(self, key: str) -> bool:
        return key in self._watchers
