# AI evaluation case format

Store one JSON object per case under `cases/<category>/<id>.json`. Every case names a fixture, one question or a
`user_turns` sequence, and whether one turn should propose a schedule change. Proposal cases default to the final
turn. Set the one-based `proposal_turn` when a later turn should discuss an earlier proposal without reproposing it.
Every other turn is explicitly graded as producing no proposal.

Use ordered `proposal_turns` when revisions should produce more than one proposal. The last listed proposal is graded
by `expected_diff`. Use `turn_actions` to apply a trusted frontend `approve`, `reject`, or external `update` after a
turn. An update supplies a shallow top-level `schedule_patch` and invalidates any pending proposal.

Use `expected_diff` for a deterministic mutation to a list-valued path. Each entry gives the complete semantic
multiset delta, so an unlisted addition or removal at that path fails:

```json
{
  "expected_diff": [
    {
      "path": "people.items",
      "removed": [{"id": "P1", "description": "", "history": ["OFF"]}],
      "added": [{"id": "P1", "description": "Lead", "history": ["OFF"]}]
    }
  ],
  "changes": ["people.items"]
}
```

Object key order and list position within the selected collection do not matter. Nested list order remains semantic,
which is required for values such as succession patterns. Include complete objects rather than partial patterns.

For a scalar, mapping, or whole-section replacement, use `before` and `after` instead of `removed` and `added`.
Use `null` for a missing path, such as an export section created from scratch.

Keep `assert` for outcomes that intentionally allow multiple valid objects or need invariants across a large cascade.
Examples include optional descriptions, case-insensitive natural-language values, and deleting one ID from many
history entries while preserving similarly named IDs. Use `answer_contains` for read-only and refusal cases,
`intermediate_answer_contains` for clarification turns, and `tool_usage` only when the trajectory itself is under test.

Every proposal case must also declare `changes`. It guards all schedule paths outside the listed scope. Diff checks
guard every addition and removal inside their selected collection.
