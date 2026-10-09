"""The two operations a replica broadcasts.

Both carry everything a receiving replica needs to apply them without asking
anything of the sender, which is what lets them arrive late, twice, or out of
order.
"""

from dataclasses import dataclass

from converge.ids import Id


@dataclass(frozen=True, slots=True)
class Insert:
    """Put `value` immediately after `origin`, or at the head when it is None.

    `origin` is the element the author saw to its left. It is not a position:
    positions move as other people type, identities do not.
    """

    id: Id
    value: str
    origin: Id | None


@dataclass(frozen=True, slots=True)
class Delete:
    """Tombstone `target`.

    Carries no id of its own: deleting twice is deleting once, so there is
    nothing to deduplicate.
    """

    target: Id


Operation = Insert | Delete
