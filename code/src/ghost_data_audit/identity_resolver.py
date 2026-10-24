"""Conservative identity resolution using current snapshots and dated audit history."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


IDENTITY_FIELDS = {"email": "email", "phone": "phone", "email_hash": "email_hash"}


def normalize_email(value: str | None) -> str:
    """Normalize only case and surrounding whitespace; do not rewrite the local part."""
    return (value or "").strip().casefold()


def _parse_time(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Dataset timestamps are expected to be UTC. Treat naive values as UTC
        # deterministically, while keeping malformed values out of temporal matches.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_field(field_name: str, value: str | None) -> str:
    raw = (value or "").strip()
    if field_name == "email":
        return normalize_email(raw)
    if field_name == "email_hash":
        return raw.casefold()
    if field_name == "phone":
        # Keep the original phone as a returned identifier; normalization is used
        # only for comparisons and removes formatting punctuation, not country digits.
        return "".join(character for character in raw if character.isdigit() or character == "+")
    return raw


def _email_hash_candidates(email: str) -> set[str]:
    normalized = normalize_email(email)
    variants = {normalized, (email or "").strip()}
    return {hashlib.sha256(value.encode("utf-8")).hexdigest() for value in variants if value}


@dataclass(frozen=True)
class IdentityMatch:
    user_id: str
    match_type: str
    matched_identifier: str
    source_id: str


@dataclass(frozen=True)
class IdentityResolution:
    requested_email: str
    audit_at: str
    matched_user_ids: tuple[str, ...]
    matches: tuple[IdentityMatch, ...]
    identifiers_by_user: dict[str, dict[str, tuple[str, ...]]]
    ambiguous: bool

    @property
    def resolved(self) -> bool:
        return len(self.matched_user_ids) == 1


def _is_at_or_before(timestamp: str | None, cutoff: datetime) -> bool:
    parsed = _parse_time(timestamp)
    return parsed is not None and parsed <= cutoff


class IdentityResolver:
    """Resolve a request email to zero, one, or multiple stable user IDs.

    The resolver never chooses arbitrarily when aliases collide. Audit events are
    time-filtered against the case cutoff; a new identifier first introduced after
    the cutoff is not treated as an identifier known at that time.
    """

    def __init__(
        self,
        user_identities: Iterable[Mapping[str, Any]],
        user_audit_log: Iterable[Mapping[str, Any]],
    ) -> None:
        self._identities = [dict(row) for row in user_identities]
        self._audit_log = [dict(row) for row in user_audit_log]
        self._identity_by_user: dict[str, dict[str, Any]] = {}
        for row in self._identities:
            user_id = str(row.get("user_id", "")).strip()
            if not user_id:
                continue
            if user_id in self._identity_by_user:
                raise ValueError(f"Duplicate user_id in identity snapshot: {user_id}")
            self._identity_by_user[user_id] = row

    def resolve(self, email: str, audit_at: str) -> IdentityResolution:
        cutoff = _parse_time(audit_at)
        if cutoff is None:
            raise ValueError(f"Invalid audit_at timestamp: {audit_at!r}")

        requested = normalize_email(email)
        request_hashes = _email_hash_candidates(email)
        aliases: dict[str, dict[str, dict[str, str]]] = {}
        # alias index: user_id -> field -> normalized value -> provenance
        for user_id, identity in self._identity_by_user.items():
            updated_at = str(identity.get("updated_at", ""))
            if _is_at_or_before(updated_at, cutoff):
                for field_name in IDENTITY_FIELDS:
                    value = str(identity.get(field_name, "") or "").strip()
                    normalized = _normalize_field(field_name, value)
                    if normalized:
                        aliases.setdefault(user_id, {}).setdefault(field_name, {})[normalized] = {
                            "source_id": "identity_snapshot", "match_type": "current_" + field_name,
                            "raw_value": value,
                        }

        # Sort by event time and audit ID so duplicate timestamps remain deterministic.
        events_by_user_field: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for event in self._audit_log:
            user_id = str(event.get("user_id", "")).strip()
            field_name = str(event.get("field_name", "")).strip().casefold()
            if user_id and field_name in IDENTITY_FIELDS and _parse_time(str(event.get("event_time", ""))):
                events_by_user_field.setdefault((user_id, field_name), []).append(event)

        for (user_id, field_name), events in events_by_user_field.items():
            events.sort(key=lambda event: (_parse_time(str(event.get("event_time", ""))), str(event.get("audit_id", ""))))
            for index, event in enumerate(events):
                event_time = _parse_time(str(event.get("event_time", "")))
                if event_time is None:
                    continue
                # old_value was in use before this event. Include it only when its
                # history began by the cutoff (initial value or a prior event).
                old_value = str(event.get("old_value", "") or "").strip()
                old_norm = _normalize_field(field_name, old_value)
                previous = events[index - 1] if index else None
                previous_time = _parse_time(str(previous.get("event_time", ""))) if previous else None
                old_introduced_by_cutoff = previous is None or (previous_time is not None and previous_time <= cutoff)
                if old_norm and old_introduced_by_cutoff:
                    aliases.setdefault(user_id, {}).setdefault(field_name, {})[old_norm] = {
                        "source_id": str(event.get("audit_id", "")), "match_type": "historical_" + field_name,
                        "raw_value": old_value,
                    }

                # A new value is available to the resolver only from its event time.
                new_value = str(event.get("new_value", "") or "").strip()
                new_norm = _normalize_field(field_name, new_value)
                if new_norm and event_time <= cutoff:
                    aliases.setdefault(user_id, {}).setdefault(field_name, {})[new_norm] = {
                        "source_id": str(event.get("audit_id", "")), "match_type": "historical_" + field_name,
                        "raw_value": new_value,
                    }

        matches: dict[tuple[str, str, str], IdentityMatch] = {}
        identifiers_by_user: dict[str, dict[str, tuple[str, ...]]] = {}
        for user_id in sorted(aliases):
            field_aliases = aliases[user_id]
            identifiers_by_user[user_id] = {
                field_name: tuple(sorted({meta["raw_value"] for meta in values.values() if meta["raw_value"]}))
                for field_name, values in field_aliases.items()
            }
            for field_name, values in field_aliases.items():
                for normalized_value, metadata in values.items():
                    is_match = (
                        field_name == "email" and normalized_value == requested
                    ) or (
                        field_name == "email_hash" and normalized_value.casefold() in request_hashes
                    )
                    if is_match:
                        match = IdentityMatch(
                            user_id=user_id,
                            match_type=metadata["match_type"],
                            matched_identifier=metadata["raw_value"],
                            source_id=metadata["source_id"],
                        )
                        matches[(user_id, match.match_type, match.source_id)] = match

        # A request-side hash can be matched directly when a source supplies one.
        if requested and all(character in "0123456789abcdef" for character in requested) and len(requested) == 64:
            for user_id, field_aliases in aliases.items():
                for normalized_value, metadata in field_aliases.get("email_hash", {}).items():
                    if normalized_value == requested:
                        match = IdentityMatch(user_id, metadata["match_type"], metadata["raw_value"], metadata["source_id"])
                        matches[(user_id, match.match_type, match.source_id)] = match

        matched_ids = tuple(sorted({match.user_id for match in matches.values()}))
        return IdentityResolution(
            requested_email=email,
            audit_at=audit_at,
            matched_user_ids=matched_ids,
            matches=tuple(sorted(matches.values(), key=lambda item: (item.user_id, item.match_type, item.source_id))),
            identifiers_by_user={user_id: identifiers_by_user[user_id] for user_id in matched_ids},
            ambiguous=len(matched_ids) > 1,
        )
