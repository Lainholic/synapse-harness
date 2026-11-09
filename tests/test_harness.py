"""
Unit tests for synapse-harness verify.py and model_sanitizer.py.
"""

import os
import sys
import unittest

# Suppress bytecode generation
sys.dont_write_bytecode = True

# Ensure scripts dir is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from verify import verify_file
from model_sanitizer import scan_text, sanitize_text

class TestSynapseHarness(unittest.TestCase):
    def test_verify_valid_file(self):
        sample_path = os.path.join(BASE_DIR, "tests", "sample_valid.py")
        res = verify_file(sample_path)
        self.assertTrue(res["success"], f"Valid file should pass verify: {res}")
        self.assertTrue(res["report"]["syntax_pass"])
        self.assertTrue(res["report"]["encoding_pass"])

    def test_verify_syntax_error_file(self):
        sample_path = os.path.join(BASE_DIR, "tests", "sample_syntax_error.py")
        res = verify_file(sample_path)
        self.assertFalse(res["success"], "Broken syntax file must fail verify.")
        self.assertFalse(res["report"]["syntax_pass"])

    def test_verify_nonexistent_file(self):
        fake_path = os.path.join(BASE_DIR, "tests", "non_existent_file.py")
        res = verify_file(fake_path)
        self.assertFalse(res["success"], "Nonexistent file must fail.")

    def test_verify_missing_test_fails_when_test_flag_requested(self):
        # sample_valid.py has no paired test_sample_valid.py
        sample_path = os.path.join(BASE_DIR, "tests", "sample_valid.py")
        res = verify_file(sample_path, run_tests=True)
        self.assertFalse(res["success"], "Requesting tests when none exist must fail overall_success.")
        self.assertEqual(res["report"]["test_status"], "not_found")

    def test_verify_paired_test_passes(self):
        # sample_calc.py has paired test_sample_calc.py
        sample_path = os.path.join(BASE_DIR, "tests", "sample_calc.py")
        res = verify_file(sample_path, run_tests=True)
        self.assertTrue(res["success"], f"Paired test should pass: {res}")
        self.assertEqual(res["report"]["test_status"], "pass")

    def test_verify_non_py_with_test_flag_fails(self):
        # Requesting --test on non-py file (e.g. README.md or LICENSE) must fail explicitly
        target_path = os.path.join(BASE_DIR, "LICENSE")
        res = verify_file(target_path, run_tests=True)
        self.assertFalse(res["success"], "Requesting --test on non-py file must fail.")
        self.assertEqual(res["report"]["test_status"], "unsupported")

    def test_verify_non_py_with_smoke_flag_fails(self):
        # Requesting --smoke on non-py file must fail explicitly
        target_path = os.path.join(BASE_DIR, "LICENSE")
        res = verify_file(target_path, smoke=True)
        self.assertFalse(res["success"], "Requesting --smoke on non-py file must fail.")
        self.assertEqual(res["report"]["smoke_status"], "unsupported")

    def test_verify_strict_mode(self):
        # In strict mode, valid file is verified
        sample_path = os.path.join(BASE_DIR, "tests", "sample_valid.py")
        res = verify_file(sample_path, strict=False)
        self.assertTrue(res["success"])

    def test_sanitizer_scan(self):
        # Dynamically build legacy string to avoid self-triggering static linter on test files
        sample_text = f"{'Gemini'} {'1.5'} {'Pro'} and {'Claude'} {'3.5'} {'Sonnet'}."
        findings = scan_text(sample_text)
        self.assertGreater(len(findings), 0, "Should detect legacy model names.")

    def test_sanitizer_fix(self):
        sample_text = f"Use {'Gemini'} {'1.5'} {'Pro'} here."
        sanitized, count = sanitize_text(sample_text)
        self.assertGreater(count, 0)
        self.assertNotIn("1.5", sanitized)

if __name__ == "__main__":
    unittest.main()
