import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "inspector", ROOT / "scripts/inspect-e2e-data.py"
)
inspector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspector)


class OriginalDataTests(unittest.TestCase):
    def test_full_originals_and_expanded_minutes(self):
        result = inspector.inspect(ROOT / "frontend/e2e/data/originals")
        self.assertEqual(
            result["counts"],
            {
                "rooms": 48,
                "teachers": 40,
                "subjects": 52,
                "modules": 208,
                "classes": 48,
                "courses": 16,
                "assignments": 336,
            },
        )
        self.assertEqual(len(result["demand"]), 336)
        self.assertEqual(len(result["rooms"]), 48)
        self.assertEqual(len(result["classes"]), 48)
        self.assertGreater(result["required_minutes"], 0)
        self.assertEqual(
            sum(item["minutes"] for item in result["demand"]),
            result["required_minutes"],
        )

    def test_missing_and_changed_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data"
            shutil.copytree(ROOT / "frontend/e2e/data/originals", target)
            original = target / "Cronos_Atribuicoes_Template_Maior.csv"
            original.write_bytes(original.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, "integrity"):
                inspector.inspect(target)
            original.unlink()
            with self.assertRaises(FileNotFoundError):
                inspector.inspect(target)

    def test_decimal_minutes_must_be_positive_and_integral(self):
        self.assertEqual(inspector.minutes("0,75"), 45)
        self.assertEqual(inspector.minutes("1.5"), 90)
        for value in ["0", "-1", "0.001", "NaN", "Infinity"]:
            with self.assertRaises(ValueError):
                inspector.minutes(value)

    def test_unknown_reference_with_matching_hash_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data"
            shutil.copytree(ROOT / "frontend/e2e/data/originals", target)
            name = "Cronos_Atribuicoes_Template_Maior.csv"
            original = target / name
            original.write_bytes(
                original.read_bytes().replace("Português".encode(), b"Unknown", 1)
            )
            manifest_path = target / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            manifest["files"][name] = {
                "bytes": original.stat().st_size,
                "sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown assignment"):
                inspector.inspect(target)


if __name__ == "__main__":
    unittest.main()
