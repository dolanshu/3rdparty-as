# `testbed/contracts/decision/` — declarative decision contract

This directory holds the **decision contract case set**: data, not code. Each case
states one fact in the form "given this number and this configuration, this is the
verdict", and it does so without reference to Python, Go or any other host
language. Every implementation has to reproduce the whole set, case for case
(ADR-0012).

It sits next to `../sip-baseline/` but the two are different in kind:

| | `../sip-baseline/` | `decision/` (here) |
|---|---|---|
| What is captured | captured **wire bytes** of SIP messages | an **expected verdict** |
| Answer to | "what exactly went on the socket?" | "what does the AS decide?" |
| Adapting to | one SIP stack, one message grammar | no protocol at all |
| Replayable by | anything that parses SIP | any language, any stack |

The baseline constrains the SIP adapter; this case set constrains the decision.
A Go implementation that keeps its own SIP stack still has to answer every case
here identically, and that is the entry ticket for the migration.

## Files

| File | Contents |
|---|---|
| `cases.json` | the case set, a JSON array of cases |
| `README.md` | this file: what the fields mean |

## Case fields

| Field | Type | Meaning |
|---|---|---|
| `case_id` | string | Stable identifier. It is the replay test's parameter name. |
| `description` | string | One sentence on which fact the case pins down. |
| `applies_to` | array | Which use cases must replay it. See below. |
| `call_id` | string | The Call-ID, carried for traces; it never affects the verdict. |
| `calling_number` | string | The calling party number, as it arrived. |
| `called_number` | string | The called party number, as it arrived. Rules match on this. |
| `received_at` | number | When the request arrived, **as data**. An implementation must never read a clock; the value is an argument. |
| `rules` | array | The kernel rule set of the loaded configuration: `{ "rule_id", "prefix", "action" }`. |
| `translations` | array | Translation-only: `{ "rule_id", "prefix", "strip_prefix", "add_prefix" }`. |
| `limits` | array | Anti-fraud-only: `{ "rule_id", "prefix", "window_seconds", "max_calls" }`. |
| `counters` | object | Anti-fraud-only: `rule_id` to the calls already counted in the current window. Injected by the caller from the state store; an implementation never counts. |
| `expected` | object | `{ "action", "target", "reason_code", "matched_rule_id" }`. `target` and `matched_rule_id` may be `null`. |

`rules[].action` takes the kernel's three values: `forward`, `translate`, `block`.
`expected.action` takes the four decision outcomes: `forward`, `translate`,
`decline`, `not_found`. A `block` rule therefore answers `decline`, never
`block`.

`translations`, `limits` and `counters` are omitted, or empty, when a case does
not need them. An empty `limits` is not the same thing as an unused counter: a
number that no window covers is not screened at all.

## `applies_to`

| Value | Meaning |
|---|---|
| `both` | Shared kernel semantics. Every implementation must agree, field for field. |
| `translation` | Only the number-translation use case can answer this. |
| `anti-fraud` | Only the anti-fraud use case can answer this. |

### Why the `translate` cases that assert a rewritten number are `translation` only

A contract case may not ask one implementation to contradict another, and on a
`TRANSLATE` verdict the two use cases genuinely differ: the kernel leaves the
outbound number open, the translation use case fills it in from its translation
rules, and the anti-fraud use case deliberately does **not** rewrite — it
screens, and passes the kernel's target through untouched. The same input
therefore yields a rewritten number from one and the kernel's target from the
other.

So the two use cases are held together where they can be: the translate facts
they share (`block-outranks-translate`, `no-rule-matches-is-not-found`,
`longest-prefix-wins`) are `both`, and the rewriting itself is stated as
`translation` cases. The baseline fact `+8613800138000` → `013800138000` is one
of them, and it is the same number the captured S1 baseline carries on its
outbound leg.

## Normalization

Numbers are compared in normalized form: separators (space, `-`, `(`, `)`, `.`,
`/`) carry no routing meaning and are dropped, and a leading `+` is added when
missing. `+86-755-1234-5678` and `+8675512345678` are one number. Prefixes in
`rules`, `translations` and `limits` are normalized the same way before matching.

## Replaying the case set

The Python implementation replays it under the `contract` marker:

```console
uv run pytest -m contract -q
```

`apps/translation/tests/test_contract_replay.py` takes the cases whose
`applies_to` contains `translation` or `both`;
`apps/anti-fraud/tests/test_contract_replay.py` takes `anti-fraud` or `both`. A
missing `cases.json` fails the replay loudly — a contract that is not replayed is
not enforced. A Go implementation adds a third replay against the same file.

## Changing the case set

Per `../README.md`: adding or changing a contract case is an interface change. It
needs an ADR, and every implementation's gate has to be re-run. An implementation
that cannot express a case has found a real difference between the stacks; it is
not a reason to weaken the case.
