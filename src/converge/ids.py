"""Element identity.

Every character ever typed gets an id that no other character will ever hold,
and that every replica orders the same way. That is the whole trick: replicas
cannot agree on positions, because positions shift under them, but they can
agree on names.
"""

from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, order=False, slots=True)
class Id:
    """A Lamport timestamp paired with the replica that issued it.

    `counter` orders causally: an element inserted after seeing another always
    carries a higher counter. `replica` breaks ties between replicas that typed
    concurrently, arbitrarily but identically everywhere.
    """

    counter: int
    replica: str

    def __lt__(self, other: Self) -> bool:
        return (self.counter, self.replica) < (other.counter, other.replica)

    def __gt__(self, other: Self) -> bool:
        return (self.counter, self.replica) > (other.counter, other.replica)

    def __repr__(self) -> str:
        return f"{self.replica}{self.counter}"
