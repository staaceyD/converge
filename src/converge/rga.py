"""RGA: a replicated growable array, which is a text document that merges.

The problem it solves: two people type into the same document at the same
moment, each sees only their own edit, and later the two edits meet. There is
no server to decide what happened. Both sides must reach the same document on
their own, from the same set of edits in any order, and never have to ask.

The idea, in three moves:

1. Every character gets an id that is unique forever (`Id`).
2. An insert records which character it went *after*, by id, not by position.
   Positions shift when other people type; identities do not.
3. When several characters were concurrently inserted after the same one, every
   replica breaks the tie the same way: higher id first.

Deletion cannot remove anything, because an insert might still arrive naming
the deleted character as its origin. So characters are tombstoned, never
dropped, and the document grows forever. That is the price, and `tombstones()`
is here so the price can be measured rather than ignored.

This is written to be read and to be tested, not to be fast: positions are
found by scanning, so applying an operation is O(n). The data structure that
makes this O(log n) is a different exercise, and worth doing only once the
property tests below are passing and can hold the faster version to the same
standard.
"""

from dataclasses import dataclass, field

from converge.ids import Id
from converge.ops import Delete, Insert, Operation


@dataclass(slots=True)
class Element:
    """One character, and whether it is still visible."""

    id: Id
    value: str
    origin: Id | None
    deleted: bool = False


@dataclass
class RGA:
    """One replica of a shared text document."""

    replica: str
    _order: list[Element] = field(default_factory=list)
    _by_id: dict[Id, Element] = field(default_factory=dict)
    _counter: int = 0
    # Operations that named something this replica has not seen yet. A late
    # insert is not an error, just an insert whose origin is still in flight.
    _waiting: list[Operation] = field(default_factory=list)

    # ---------------------------------------------------------------- reading

    def text(self) -> str:
        """The document as a reader sees it, tombstones omitted."""
        return "".join(e.value for e in self._order if not e.deleted)

    def ids(self) -> list[Id]:
        """Every element in document order, tombstones included.

        Two replicas agreeing on `text()` is necessary but not sufficient:
        convergence means agreeing on this, because this is what the next
        operation will be interpreted against.
        """
        return [e.id for e in self._order]

    def tombstones(self) -> int:
        return sum(1 for e in self._order if e.deleted)

    def waiting(self) -> int:
        """Operations buffered awaiting a causal dependency."""
        return len(self._waiting)

    # ------------------------------------------------------------ local edits

    def insert(self, index: int, value: str) -> list[Insert]:
        """Type `value` at visible position `index`. Returns ops to broadcast."""
        if not 0 <= index <= len(self.text()):
            raise IndexError(f"index {index} outside document of length {len(self.text())}")
        ops = []
        origin = self._visible(index - 1).id if index > 0 else None
        for offset, char in enumerate(value):
            op = Insert(id=self._tick(), value=char, origin=origin)
            self._insert(op)
            origin = op.id
            ops.append(op)
            del offset
        return ops

    def delete(self, index: int, count: int = 1) -> list[Delete]:
        """Delete `count` visible characters from `index`. Returns ops to broadcast."""
        targets = [self._visible(index + n).id for n in range(count)]
        ops = [Delete(target=t) for t in targets]
        for op in ops:
            self._delete(op)
        return ops

    # ----------------------------------------------------------- remote edits

    def apply(self, op: Operation) -> None:
        """Apply an operation from another replica.

        Safe to call with the same operation twice, and with operations in any
        order: anything that names something not yet seen waits until it is.
        """
        self._waiting.append(op)
        self._drain()

    def _drain(self) -> None:
        # Applying one operation can unblock others, so go round until a full
        # pass applies nothing.
        moved = True
        while moved:
            moved = False
            for op in list(self._waiting):
                if not self._ready(op):
                    continue
                self._waiting.remove(op)
                if isinstance(op, Insert):
                    self._insert(op)
                else:
                    self._delete(op)
                moved = True

    def _ready(self, op: Operation) -> bool:
        if isinstance(op, Insert):
            return op.origin is None or op.origin in self._by_id
        return op.target in self._by_id

    # ------------------------------------------------------------------ cogs

    def _insert(self, op: Insert) -> None:
        if op.id in self._by_id:
            return  # already applied; inserts are idempotent by id
        self._observe(op.id)

        start = 0 if op.origin is None else self._position(op.origin) + 1

        # Walk past everything that sorts above us.
        #
        # Why this is enough: anything sitting after our origin with a greater
        # id is either a sibling that won the tie-break, or a descendant of
        # one. A descendant is always inserted by a replica that had already
        # seen its parent, so its counter is strictly higher than its parent's
        # — which means a losing sibling's whole subtree also sorts above us,
        # and this one loop steps over all of it without needing to know the
        # tree is there.
        at = start
        while at < len(self._order) and op.id < self._order[at].id:
            at += 1

        element = Element(id=op.id, value=op.value, origin=op.origin)
        self._order.insert(at, element)
        self._by_id[op.id] = element

    def _delete(self, op: Delete) -> None:
        self._by_id[op.target].deleted = True

    def _position(self, id_: Id) -> int:
        for i, element in enumerate(self._order):
            if element.id == id_:
                return i
        raise KeyError(id_)

    def _visible(self, index: int) -> Element:
        seen = -1
        for element in self._order:
            if element.deleted:
                continue
            seen += 1
            if seen == index:
                return element
        raise IndexError(f"no visible element at {index}")

    def _tick(self) -> Id:
        self._counter += 1
        return Id(self._counter, self.replica)

    def _observe(self, id_: Id) -> None:
        # Our next id must sort above anything we have already seen, or we
        # would claim to have typed before an edit we are reacting to.
        self._counter = max(self._counter, id_.counter)
