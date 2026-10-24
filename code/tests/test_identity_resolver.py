from __future__ import annotations

import unittest

from ghost_data_audit.identity_resolver import IdentityResolver, normalize_email


class IdentityResolverTests(unittest.TestCase):
    def test_normalizes_email_case_and_outer_whitespace_only(self) -> None:
        self.assertEqual(normalize_email("  User.Name@Example.com "), "user.name@example.com")
        self.assertEqual(normalize_email("user.name+tag@example.com"), "user.name+tag@example.com")

    def test_resolves_current_email(self) -> None:
        resolver = IdentityResolver(
            [{"user_id": "user_1", "email": "Alice@Example.com", "phone": "", "email_hash": "", "updated_at": "2026-01-01T00:00:00Z"}],
            [],
        )
        result = resolver.resolve("alice@example.com", "2026-02-01T00:00:00Z")
        self.assertEqual(result.matched_user_ids, ("user_1",))
        self.assertTrue(result.resolved)

    def test_resolves_historical_email_only_after_change_event(self) -> None:
        identities = [
            {"user_id": "user_1", "email": "new@example.com", "phone": "", "email_hash": "", "updated_at": "2026-02-01T00:00:00Z"}
        ]
        audit = [
            {"audit_id": "audit_1", "user_id": "user_1", "event_time": "2026-01-10T00:00:00Z", "field_name": "email", "old_value": "old@example.com", "new_value": "new@example.com"}
        ]
        resolver = IdentityResolver(identities, audit)
        before_change = resolver.resolve("old@example.com", "2026-01-09T23:59:59Z")
        after_change = resolver.resolve("old@example.com", "2026-01-11T00:00:00Z")
        self.assertEqual(before_change.matched_user_ids, ())
        self.assertEqual(after_change.matched_user_ids, ("user_1",))

    def test_excludes_alias_introduced_after_cutoff(self) -> None:
        resolver = IdentityResolver(
            [{"user_id": "user_1", "email": "new@example.com", "phone": "", "email_hash": "", "updated_at": "2026-03-01T00:00:00Z"}],
            [{"audit_id": "audit_1", "user_id": "user_1", "event_time": "2026-02-01T00:00:00Z", "field_name": "email", "old_value": "older@example.com", "new_value": "new@example.com"}],
        )
        result = resolver.resolve("new@example.com", "2026-01-01T00:00:00Z")
        self.assertEqual(result.matched_user_ids, ())

    def test_reports_ambiguous_alias_instead_of_picking_one(self) -> None:
        identities = [
            {"user_id": "user_1", "email": "same@example.com", "updated_at": "2026-01-01T00:00:00Z"},
            {"user_id": "user_2", "email": "same@example.com", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        result = IdentityResolver(identities, []).resolve("same@example.com", "2026-02-01T00:00:00Z")
        self.assertTrue(result.ambiguous)
        self.assertEqual(result.matched_user_ids, ("user_1", "user_2"))


if __name__ == "__main__":
    unittest.main()
