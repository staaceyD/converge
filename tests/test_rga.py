"""Worked examples, including the one RGA gets wrong."""

from converge import RGA


def test_a_single_replica_is_just_a_string() -> None:
    doc = RGA("a")
    doc.insert(0, "hello")
    doc.insert(5, " world")
    doc.delete(0)

    assert doc.text() == "ello world"


def test_an_insert_that_arrives_before_its_origin_waits() -> None:
    a, b = RGA("a"), RGA("b")
    first = a.insert(0, "x")
    second = a.insert(1, "y")

    # The second op names the first as its origin, and arrives first.
    b.apply(second[0])
    assert b.text() == "", "an op with an unseen origin must not be applied"
    assert b.waiting() == 1

    b.apply(first[0])
    assert b.text() == "xy"
    assert b.waiting() == 0


def test_delivering_the_same_operation_twice_changes_nothing() -> None:
    a, b = RGA("a"), RGA("b")
    ops = a.insert(0, "hi")
    for op in ops + ops:
        b.apply(op)

    assert b.text() == "hi"
    assert b.ids() == a.ids()


def test_concurrent_inserts_at_the_same_point_converge() -> None:
    a, b = RGA("a"), RGA("b")
    shared = a.insert(0, "-")
    b.apply(shared[0])

    # Both type after the same character, neither having seen the other.
    from_a = a.insert(1, "A")
    from_b = b.insert(1, "B")

    for op in from_b:
        a.apply(op)
    for op in from_a:
        b.apply(op)

    assert a.text() == b.text()
    assert a.ids() == b.ids()


def test_deleting_a_character_someone_else_is_typing_after_is_fine() -> None:
    a, b = RGA("a"), RGA("b")
    for op in a.insert(0, "xy"):
        b.apply(op)

    gone = a.delete(1)  # a removes "y"
    after = b.insert(2, "z")  # b types after it, not knowing

    for op in after:
        a.apply(op)
    for op in gone:
        b.apply(op)

    assert a.text() == b.text() == "xz"
    assert a.ids() == b.ids()


def test_concurrent_typing_interleaves_characters() -> None:
    """RGA's known weakness, pinned here rather than left as a surprise.

    Two people type a whole word at the same position at the same time. Both
    replicas converge — that is the contract and it holds — but the result can
    braid the two words together instead of keeping them whole, because every
    character is placed independently and nothing records that these six
    characters were one act of typing.

    Fugue is the fix, and replacing this with a test that asserts the words
    stay whole is the point of stage 4 in the README.
    """
    a, b = RGA("a"), RGA("b")

    for op in a.insert(0, "-"):
        b.apply(op)

    from_a = a.insert(1, "cat")
    from_b = b.insert(1, "dog")

    for op in from_b:
        a.apply(op)
    for op in from_a:
        b.apply(op)

    assert a.ids() == b.ids(), "convergence is the contract and must hold"
    assert a.text() == b.text()

    merged = a.text()
    assert sorted(merged) == sorted("-catdog")
    whole = merged in ("-catdog", "-dogcat")
    if not whole:
        # Not a failure: this is the anomaly, recorded.
        assert "cat" not in merged or "dog" not in merged
