"""Guard for the backend critical CI selection.

The fast CI job runs only the selected critical files and cases. The full corpus
is not deleted; it is just not executed in the fast gate. This test fails if the
selection is empty, points outside ``tests/``, duplicates a selector, references
a missing file, drops a protected source policy, or drifts from the committed
JSON manifest.

The critical coverage scope lives in the manifest only. ``pyproject.toml`` keeps
its whole-application default so the optional full developer run stays honest.
"""

import json
import re
import tomllib
from pathlib import Path

from tests import critical_selection

BACKEND = Path(__file__).resolve().parents[2]
GUARD = "tests/unit/test_critical_selection_policy.py"
SELECTOR = re.compile(r"tests/[A-Za-z0-9_\-/]+\.py(?:::[A-Za-z0-9_]+)?")
SOURCES = re.compile(r"app/[A-Za-z0-9_\-/]+\.py")


def _all_test_files() -> set[str]:
    return {path.relative_to(BACKEND).as_posix() for path in (BACKEND / "tests").rglob("test_*.py")}


def _selected_selectors() -> list[str]:
    return [
        *critical_selection.UNIT_PATHS,
        *critical_selection.db_selectors(),
    ]


def _file_of(selector: str) -> str:
    return selector.split("::", 1)[0]


def test_selection_is_not_empty_and_runs_its_own_guard():
    assert critical_selection.UNIT_PATHS
    assert critical_selection.DB_PATHS
    assert GUARD in critical_selection.UNIT_PATHS


def test_selection_selectors_are_unique_and_well_formed():
    selectors = _selected_selectors()
    assert len(selectors) == len(set(selectors))
    for path in critical_selection.UNIT_PATHS:
        assert path.startswith("tests/unit/") and path.endswith(".py"), path
    for selector in critical_selection.db_selectors():
        assert SELECTOR.fullmatch(selector), selector


def test_exact_cases_stay_on_the_trust_boundary():
    assert critical_selection.DB_CASES == (
        "tests/integration/committed/test_webhooks.py::test_webhook_invalid_signature_rejected",
        "tests/integration/committed/test_webhooks.py::test_webhook_idempotency_uses_svix_event_id",
    )
    assert "tests/unit/test_request_body_limit.py" in critical_selection.UNIT_PATHS
    assert "tests/unit/test_client_ip.py" in critical_selection.UNIT_PATHS


def test_every_selected_file_exists_locally():
    for selector in _selected_selectors():
        assert (BACKEND / _file_of(selector)).is_file(), selector


def test_selection_is_a_strict_subset_of_the_local_corpus():
    corpus = _all_test_files()
    files = {_file_of(selector) for selector in _selected_selectors()}
    assert files <= corpus
    assert files < corpus


def test_critical_sources_are_real_and_keep_the_protected_policies():
    assert critical_selection.CRITICAL_COVERAGE_MIN >= 70
    for source in critical_selection.CRITICAL_SOURCES:
        assert SOURCES.fullmatch(source), source
        assert (BACKEND / source).is_file(), source
    assert "app/scheduler/domain/constraint_policy.py" in critical_selection.CRITICAL_SOURCES
    assert "app/scheduler/domain/candidate_validation.py" in critical_selection.CRITICAL_SOURCES
    assert "app/core/client_ip.py" in critical_selection.CRITICAL_SOURCES
    assert "app/api/v1/endpoints/webhooks.py" in critical_selection.CRITICAL_SOURCES
    assert dict(critical_selection.PROTECTED_INCLUDES) == {
        "app/scheduler/domain/constraint_policy.py": 100,
        "app/scheduler/domain/candidate_validation.py": 90,
    }


def test_manifest_declares_the_critical_coverage_scope():
    coverage = critical_selection.manifest()["coverage"]
    assert coverage["sources"] == list(critical_selection.CRITICAL_SOURCES)
    assert coverage["fail_under"] == critical_selection.CRITICAL_COVERAGE_MIN
    assert coverage["includes"] == [
        {"path": path, "fail_under": threshold}
        for path, threshold in critical_selection.PROTECTED_INCLUDES
    ]


def test_manifest_matches_the_root_runner_schema():
    manifest = critical_selection.manifest()
    groups = manifest["groups"]
    assert groups
    names = [group["name"] for group in groups]
    assert len(names) == len(set(names))
    seen: set[str] = set()
    for group in groups:
        assert re.fullmatch(r"[a-z][a-z0-9-]*", group["name"]), group["name"]
        assert group["paths"]
        for selector in group["paths"]:
            assert SELECTOR.fullmatch(selector), selector
            assert selector not in seen, selector
            seen.add(selector)
        assert all(isinstance(arg, str) for arg in group["args"])
        assert isinstance(group["workers"], int) and group["workers"] >= 1
    assert seen == set(_selected_selectors())
    coverage = manifest["coverage"]
    assert 0 <= coverage["fail_under"] <= 100
    for source in coverage["sources"]:
        assert SOURCES.fullmatch(source), source
    for entry in coverage["includes"]:
        assert SOURCES.fullmatch(entry["path"]), entry["path"]
        assert 0 <= entry["fail_under"] <= 100


def test_default_coverage_stays_whole_application():
    with (BACKEND / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    report = config["tool"]["coverage"]["report"]
    assert report["fail_under"] == 70
    assert report["show_missing"] is True
    assert "include" not in report


def test_committed_manifest_matches_the_policy():
    committed = json.loads(
        (BACKEND / "tests" / "critical_manifest.json").read_text(encoding="utf-8")
    )
    assert committed == critical_selection.manifest()
