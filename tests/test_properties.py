"""The tests that decide whether this is a CRDT or just a data structure.

A merge function cannot be checked by example. The interesting states are the
ones nobody would think to write down: an insert arriving before the character
it was typed after, the same delete twice, three replicas diverging and meeting
in a different order each. So the edits and the delivery order are generated,
and the properties are asserted over whatever comes out.

The property that matters is the last one: once every replica has seen every
operation, they all hold the same document. Not the same text — the same
sequence of ids, including tombstones, because that is what the next operation
will be interpreted against. Two replicas showing identical text over different
internal orders have not converged, they have got lucky, and the next
concurrent insert will pull them apart.
"""

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

from converge import RGA

REPLICAS = ("a", "b", "c")
TYPEABLE = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=3)


class Cluster(RuleBasedStateMachine):
    """Three replicas and an unreliable network between them."""

    def __init__(self) -> None:
        super().__init__()
        self.replicas: dict[str, RGA] = {}
        # (recipient, operation) pairs that have been sent but not delivered.
        self.inflight: list[tuple[str, object]] = []

    @initialize()
    def start(self) -> None:
        self.replicas = {name: RGA(name) for name in REPLICAS}

    # --------------------------------------------------------- what users do

    @rule(who=st.sampled_from(REPLICAS), where=st.integers(min_value=0), what=TYPEABLE)
    def types(self, who: str, where: int, what: str) -> None:
        replica = self.replicas[who]
        where = where % (len(replica.text()) + 1)
        self._broadcast(who, replica.insert(where, what))

    @rule(who=st.sampled_from(REPLICAS), where=st.integers(min_value=0))
    def deletes(self, who: str, where: int) -> None:
        replica = self.replicas[who]
        if not replica.text():
            return
        where = where % len(replica.text())
        self._broadcast(who, replica.delete(where))

    # ------------------------------------------------------ what the net does

    @precondition(lambda self: bool(self.inflight))
    @rule(pick=st.integers(min_value=0))
    def delivers_something(self, pick: int) -> None:
        """Deliver one message, chosen arbitrarily — not in the order sent."""
        to, op = self.inflight.pop(pick % len(self.inflight))
        self.replicas[to].apply(op)

    @precondition(lambda self: bool(self.inflight))
    @rule(pick=st.integers(min_value=0))
    def delivers_twice(self, pick: int) -> None:
        """Deliver a message and leave it queued, so it arrives again later."""
        to, op = self.inflight[pick % len(self.inflight)]
        self.replicas[to].apply(op)

    # ------------------------------------------------------------ properties

    @invariant()
    def a_replica_never_shows_a_deleted_character(self) -> None:
        for replica in self.replicas.values():
            visible = len(replica.text())
            assert visible == len(replica.ids()) - replica.tombstones()

    @invariant()
    def every_id_appears_once(self) -> None:
        for name, replica in self.replicas.items():
            ids = replica.ids()
            assert len(ids) == len(set(ids)), f"{name} holds a duplicate id"

    def teardown(self) -> None:
        """Flush the network, then require that everyone agrees."""
        if not self.replicas:
            return
        while self.inflight:
            to, op = self.inflight.pop()
            self.replicas[to].apply(op)

        for name, replica in self.replicas.items():
            assert replica.waiting() == 0, f"{name} is still waiting on {replica.waiting()} ops"

        reference = self.replicas[REPLICAS[0]]
        for name, replica in self.replicas.items():
            assert replica.ids() == reference.ids(), (
                f"{name} and {REPLICAS[0]} disagree on element order:\n"
                f"  {name}: {replica.ids()}\n"
                f"  {REPLICAS[0]}: {reference.ids()}"
            )
            assert replica.text() == reference.text()

    # ----------------------------------------------------------------- plumbing

    def _broadcast(self, sender: str, ops: list) -> None:
        for op in ops:
            for name in REPLICAS:
                if name != sender:
                    self.inflight.append((name, op))


Cluster.TestCase.settings = settings(
    max_examples=300,
    stateful_step_count=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
TestCluster = Cluster.TestCase
