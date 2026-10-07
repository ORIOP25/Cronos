import base64
import copy
import hashlib
import hmac
import json
import unittest

from scripts.e2e_cleanup_policy import cleanup_targets, verify_registry


class CleanupOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "schema_version": 1,
            "run_id": "run-1",
            "started_at": "2026-10-07T08:00:00+00:00",
            "finished_at": "2026-10-07T09:00:00+00:00",
            "organizations": [
                {
                    "local_id": 17,
                    "clerk_id": "org_owned",
                    "type": "disposable",
                    "creation_run_id": "run-1",
                    "created_at": "2026-10-07T08:10:00+00:00",
                    "provenance": "ui",
                    "creator_id": "user_founder",
                    "actors": [{"id": "user_founder", "email": "admincronos100+run-1@gmail.com"}],
                }
            ],
        }
        self.observed = {
            17: {
                "local_id": 17,
                "clerk_id": "org_owned",
                "created_at": "2026-10-07T08:10:00+00:00",
                "creator_id": "user_founder",
                "actor_ids": ["user_founder"],
                "actors": [{"id": "user_founder", "email": "admincronos100+run-1@gmail.com"}],
                "active_jobs": [],
            }
        }

    def test_only_owned_disposable_organizations_are_targets(self):
        self.assertEqual(cleanup_targets(self.record, "run-1", self.observed), [(17, "org_owned")])
        self.record["organizations"][0]["type"] = "persistent"
        self.assertEqual(cleanup_targets(self.record, "run-1", {}), [])

    def test_boolean_schema_versions_are_not_valid_registry_versions(self):
        self.record["schema_version"] = True
        with self.assertRaises(ValueError):
            cleanup_targets(self.record, "run-1", self.observed)

    def test_any_ownership_mismatch_aborts_the_entire_plan(self):
        for field, value in [
            ("local_id", 99),
            ("clerk_id", "org_customer"),
            ("creator_id", "user_customer"),
            ("created_at", "2026-09-01T08:10:00+00:00"),
            ("actors", [{"id": "user_customer", "email": "customer@example.com"}]),
            ("active_jobs", ["job-1"]),
        ]:
            with self.subTest(field=field):
                observed = copy.deepcopy(self.observed)
                observed[17][field] = value
                with self.assertRaises(ValueError):
                    cleanup_targets(self.record, "run-1", observed)
        for field, value in [
            ("type", "customer"),
            ("creation_run_id", "other"),
            ("provenance", "api"),
            ("local_id", True),
        ]:
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                record["organizations"][0][field] = value
                with self.assertRaises(ValueError):
                    cleanup_targets(record, "run-1", self.observed)
        with self.assertRaises(ValueError):
            cleanup_targets(self.record, "other", self.observed)

    def test_base_accounts_and_duplicate_targets_cannot_be_erased(self):
        self.record["organizations"][0]["actors"][0]["email"] = "admincronos100@gmail.com"
        with self.assertRaises(ValueError):
            cleanup_targets(self.record, "run-1", self.observed)

    def test_registry_signature_is_verified_before_using_its_payload(self):
        key = bytes(range(32))
        payload = json.dumps(self.record, separators=(",", ":")).encode()
        envelope = {
            "version": 1,
            "payload": base64.b64encode(payload).decode(),
            "signature": hmac.new(key, payload, hashlib.sha256).hexdigest(),
        }
        self.assertEqual(verify_registry(envelope, key), self.record)
        for changed in [
            {**envelope, "version": True},
            {**envelope, "payload": envelope["payload"] + "\n"},
            {**envelope, "payload": base64.b64encode(b"{bad-json").decode()},
            {**envelope, "signature": "00" * 32},
            {**envelope, "signature": "invalid"},
            {**envelope, "payload": None},
        ]:
            with self.subTest(envelope=changed), self.assertRaises(ValueError):
                verify_registry(changed, key)
        with self.assertRaises(ValueError):
            verify_registry(envelope, b"short")
        with self.assertRaises(ValueError):
            verify_registry(envelope, bytes(reversed(range(32))))

    def test_live_actor_email_must_match_the_run_alias_not_only_its_clerk_id(self):
        for email in [
            "admincronos100@gmail.com",
            "customer@example.com",
            "admincronos100+other@gmail.com",
        ]:
            with self.subTest(email=email):
                observed = copy.deepcopy(self.observed)
                observed[17]["actors"][0]["email"] = email
                with self.assertRaises(ValueError):
                    cleanup_targets(self.record, "run-1", observed)
        self.record["organizations"][0]["actors"][0]["email"] = "admincronos100+run-1@gmail.com"
        self.record["organizations"].append(copy.deepcopy(self.record["organizations"][0]))
        with self.assertRaises(ValueError):
            cleanup_targets(self.record, "run-1", self.observed)


if __name__ == "__main__":
    unittest.main()
