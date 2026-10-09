# converge

A text CRDT, written to be read, with the merge rule explained and the
convergence property actually tested rather than asserted in a sentence.

Two people type into the same document at the same moment. Each sees only
their own edit. Later the edits meet, and there is no server to decide what
happened. Both sides have to reach the same document on their own, from the
same edits in any order, and never have to ask.

That is the whole problem, and it is more interesting than it sounds, because
the obvious answer — "send the position you typed at" — is wrong the instant
anyone types above you.

## Where this is up to

Stage 0 is done: a reference implementation and the property tests that decide
whether it is correct.

- `src/converge/rga.py` — the merge, with the reasoning in comments
- `tests/test_properties.py` — generated edits, hostile delivery, convergence asserted
- `tests/test_rga.py` — worked examples, including the one RGA gets wrong

Nothing else exists yet. The plan below is the order it is worth building in.

## The plan

**1. Reference implementation** ✅

RGA over a flat list. Operations are `Insert(id, value, origin)` and
`Delete(target)`, both of which carry everything a receiver needs, so they can
arrive late, twice, or out of order.

**2. Property tests** ✅

A three-replica cluster and a network that reorders and duplicates. Hypothesis
generates the edits *and* the delivery order; the test asserts that once
everyone has seen everything, everyone holds the same document.

Both were checked by sabotage — see [Does the test actually
test?](#does-the-test-actually-test) below. A property test that cannot fail is
decoration.

**3. Make it a thing two browsers share**

A WebSocket relay that does nothing but fan out operations — no ordering, no
merging, no authority. Two tabs, plain text, each edit broadcast as it is made.

The relay being stupid is the point: if it had to order anything, the CRDT
would not be earning its keep.

**4. The split-brain toggle** ← *the reason to build this*

A button that disconnects a replica. Type in both. Reconnect. Watch them
converge, with the operations that crossed shown as they are applied.

This is the part that does not exist elsewhere. Plenty of repos implement a
CRDT; almost none let you *see* one heal, and nothing explains it as well as
watching it does.

**5. Admit what RGA gets wrong**

Two people typing whole words at the same position can have their words
braided together, character by character. RGA converges — that contract
holds — but the result is not what either person meant.

`test_concurrent_typing_interleaves_characters` already pins this. Stage 5 is
implementing Fugue alongside, running both from the same operation log, and
writing up what changes. Honest about a weakness beats quiet about it.

**6. Measure the tombstones**

Deleted characters cannot be removed — an insert might still arrive naming one
as its origin — so the document only grows. `tombstones()` already counts
them. This stage is a chart of document size against edits made, and a
straight answer about when that stops being acceptable.

Most CRDT write-ups skip this. It is the main reason people choose not to use
one.

## The merge rule

Three moves:

1. Every character gets an id that is unique forever: a Lamport counter plus
   the replica that issued it.
2. An insert records which character it went **after**, by id. Not a position —
   positions shift when other people type, identities do not.
3. When several characters were concurrently inserted after the same one,
   every replica breaks the tie identically: higher id first.

Applying an insert is then: find the origin, walk right past everything that
sorts above us, and sit down.

```python
at = start
while at < len(self._order) and op.id < self._order[at].id:
    at += 1
```

### Why that one loop is enough

This is the part worth slowing down for, because it looks too simple.

The elements after an origin form a tree — siblings that were typed
concurrently, each with its own descendants. The loop above does not know the
tree is there, and still steps over whole subtrees correctly.

It works because a descendant is always inserted by a replica that had already
seen its parent, so its counter is strictly higher. If a sibling sorts above
us, everything hanging off that sibling sorts above us too. Walking while
`op.id < candidate.id` therefore skips each losing sibling together with its
entire subtree, and stops in exactly the right place.

Get this wrong — skip only direct siblings — and replicas diverge. The property
tests catch it, which is the next section.

## Does the test actually test?

Both properties were verified by breaking the implementation on purpose:

| Sabotage | What the tests did |
| --- | --- |
| Skip only direct siblings, not their subtrees | Divergence: two replicas disagreed on element order |
| Apply operations immediately, no causal buffering | `KeyError` on an insert whose origin had not arrived |

Convergence is asserted on `ids()` — every element in order, tombstones
included — not on `text()`. Two replicas showing the same text over different
internal orders have not converged, they have got lucky, and the next
concurrent insert pulls them apart.

## Running it

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
```

The property tests run 300 generated scenarios of up to 40 steps each. To
reproduce one exactly, pin the seed:

```bash
uv run pytest tests/test_properties.py --hypothesis-seed=0
```

When changing the merge rule, raise `max_examples` and `stateful_step_count`
in the `settings(...)` at the bottom of `tests/test_properties.py` — the
defaults are tuned to keep CI quick, not to find rare bugs.

## Reading

- Roh, Jeon, Kim, Lee — *Replicated abstract data types: Building blocks for
  collaborative applications* (RGA)
- Weidner, Gentle, Kleppmann — *The Art of the Fugue* (the interleaving fix)
- Kleppmann's writing on local-first software, for why any of this matters

## Not a library

This is written to be understood, not depended on. Applying an operation is
O(n) because positions are found by scanning. Making that O(log n) is a
worthwhile exercise, and worth doing only once the property tests can hold the
faster version to the same standard.

If you need a CRDT in production, use Yjs or Automerge.
