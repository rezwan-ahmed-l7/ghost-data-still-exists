# Ghost Data Still Exists — Phase 1 Foundation

This directory contains the first implementation slice only:

- strict loading and header validation for all participant-facing CSV inputs;
- deterministic identity resolution from current identity snapshots and dated identity audit events;
- a smoke test for the first five public sample requests;
- unit tests for normalization, current and historical email matching, cutoff handling, and ambiguous identity collisions.

The Policy Engine, evidence extraction/replay, Steps Generator, and full output generation are intentionally not implemented yet.

## Requirements

- Python 3.10+
- No third-party packages required.

## Run from the repository root

Run the first-five sample smoke test:

\`\`\`bash
python code/scripts/check_first_five.py
\`\`\`

Run unit tests:

\`\`\`bash
PYTHONPATH=code/src python -m unittest discover -s code/tests -v
\`\`\`

The CSV loader expects the official dataset files under the repository's \`dataset/\` directory. It validates exact headers and rejects duplicate request IDs and duplicate current-snapshot user IDs.

## Identity-resolution behavior

- Email matching is case-insensitive and trims surrounding whitespace; it does not alter dots, plus tags, or provider-specific semantics.
- Current identity values are considered only when their snapshot \`updated_at\` is at or before the case's \`audit_at\`.
- Historical email, phone, and email-hash changes are filtered using \`event_time\`; values are not introduced before their recorded event.
- The resolver returns all matched stable \`user_id\` values and marks collisions as ambiguous rather than selecting an arbitrary person.
- Identity hash values are treated as opaque identifiers. The resolver does not assume an undocumented hash algorithm for stored values.
- This module does not decide whether deletion was authorized, inspect evidence files, reconstruct resource state, or make deletion-status decisions.

## Important scope note

The first-five smoke test checks exact current-email identity matches against the supplied snapshot and reports the public sample's expected status for context. It is not an end-to-end deletion audit and does not claim to validate the hidden evaluation cases.
