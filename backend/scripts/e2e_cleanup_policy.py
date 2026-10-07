"""Pure ownership checks. Validate the whole plan before any destructive effect."""

import base64
import binascii
import hashlib
import hmac
import json
import re
from datetime import datetime


def verify_registry(envelope, key):
    """Authenticate the Node registry envelope before parsing any ownership IDs."""
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("Registry key must contain exactly 32 bytes")
    if (
        not isinstance(envelope, dict)
        or type(envelope.get("version")) is not int
        or envelope["version"] != 1
        or not isinstance(envelope.get("payload"), str)
        or not isinstance(envelope.get("signature"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", envelope["signature"])
    ):
        raise ValueError("Invalid registry envelope")
    try:
        payload = base64.b64decode(envelope["payload"], validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Invalid registry encoding") from error
    if base64.b64encode(payload).decode() != envelope["payload"]:
        raise ValueError("Invalid registry encoding")
    signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, envelope["signature"]):
        raise ValueError("Invalid registry signature")
    try:
        registry = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid registry payload") from error
    if not isinstance(registry, dict):
        raise ValueError("Invalid registry payload")
    return registry


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Cleanup timestamps require a timezone")
        return parsed
    except (TypeError, AttributeError) as error:
        raise ValueError("Invalid cleanup timestamp") from error


def _actor_emails(actors):
    if not isinstance(actors, list) or not actors:
        raise ValueError("Cleanup actor provenance is missing")
    identities = {}
    for actor in actors:
        if (
            not isinstance(actor, dict)
            or not isinstance(actor.get("id"), str)
            or not re.fullmatch(r"user_[a-zA-Z0-9]+", actor["id"])
            or not isinstance(actor.get("email"), str)
            or actor["id"] in identities
        ):
            raise ValueError("Invalid cleanup actor identity")
        identities[actor["id"]] = actor["email"]
    return identities


def cleanup_targets(registry, expected_run_id, observed):
    if (
        type(registry.get("schema_version")) is not int
        or registry.get("schema_version") != 1
        or not expected_run_id
        or registry.get("run_id") != expected_run_id
    ):
        raise ValueError("Cleanup run identity does not match")
    started = _timestamp(registry.get("started_at"))
    finished = _timestamp(registry.get("finished_at"))
    if finished < started or not isinstance(registry.get("organizations"), list):
        raise ValueError("Invalid cleanup registry")
    targets = []
    seen_local = set()
    seen_clerk = set()
    for organization in registry["organizations"]:
        local_id = organization.get("local_id")
        clerk_id = organization.get("clerk_id")
        if (
            type(local_id) is not int
            or local_id <= 0
            or not isinstance(clerk_id, str)
            or not re.fullmatch(r"org_[a-zA-Z0-9]+", clerk_id)
        ):
            raise ValueError("Invalid cleanup organization identity")
        if local_id in seen_local or clerk_id in seen_clerk:
            raise ValueError("Duplicate cleanup organization identity")
        seen_local.add(local_id)
        seen_clerk.add(clerk_id)
        if organization.get("type") == "persistent":
            continue
        if (
            organization.get("type") != "disposable"
            or organization.get("provenance") != "ui"
            or organization.get("creation_run_id") != expected_run_id
        ):
            raise ValueError("Organization does not belong to this disposable UI run")
        created = _timestamp(organization.get("created_at"))
        if not started <= created <= finished:
            raise ValueError("Organization creation is outside the run")
        actors = organization.get("actors")
        actor_emails = _actor_emails(actors)
        for actor in actors:
            if not re.fullmatch(
                r"(admincronos100|professorcronos100)\+"
                + re.escape(expected_run_id)
                + r"@gmail\.com",
                actor.get("email", ""),
            ):
                raise ValueError("Cleanup actors must use aliases belonging to this run")
        current = observed.get(local_id)
        if (
            not current
            or current.get("local_id") != local_id
            or current.get("clerk_id") != clerk_id
            or current.get("creator_id") != organization.get("creator_id")
            or current.get("creator_id") not in actor_emails
            or _timestamp(current.get("created_at")) != created
            or _actor_emails(current.get("actors")) != actor_emails
        ):
            raise ValueError("Live ownership does not match the run registry")
        if current.get("active_jobs") != []:
            raise ValueError("Cleanup refused while jobs are active or unknown")
        targets.append((local_id, clerk_id))
    return targets
