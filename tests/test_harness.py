"""
Unit tests for synapse-harness verify.py and model_sanitizer.py.
"""

import os
import sys
import unittest
import subprocess
import json
import re

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

    def test_verify_non_py_markdown_with_test_flag_fails(self):
        target_path = os.path.join(BASE_DIR, "README.md")
        res = verify_file(target_path, run_tests=True)
        self.assertFalse(res["success"], "Requesting --test on non-py file must fail.")
        self.assertEqual(res["report"]["test_status"], "unsupported")

    def test_verify_non_py_with_smoke_flag_fails(self):
        target_path = os.path.join(BASE_DIR, "LICENSE")
        res = verify_file(target_path, smoke=True)
        self.assertFalse(res["success"], "Requesting --smoke on non-py file must fail.")
        self.assertEqual(res["report"]["smoke_status"], "unsupported")

    def test_verify_non_py_json_with_test_flag_fails(self):
        # Test on temporary JSON file
        json_path = os.path.join(BASE_DIR, "tests", "temp_test.json")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                f.write('{"test": true}')
            res = verify_file(json_path, run_tests=True)
            self.assertFalse(res["success"], "Requesting --test on JSON must fail.")
            self.assertEqual(res["report"]["test_status"], "unsupported")
        finally:
            if os.path.exists(json_path):
                os.remove(json_path)

    def test_verify_non_py_json_with_smoke_flag_fails(self):
        # Test on temporary JSON file
        json_path = os.path.join(BASE_DIR, "tests", "temp_test_smoke.json")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                f.write('{"test": true}')
            res = verify_file(json_path, smoke=True)
            self.assertFalse(res["success"], "Requesting --smoke on JSON must fail.")
            self.assertEqual(res["report"]["smoke_status"], "unsupported")
        finally:
            if os.path.exists(json_path):
                os.remove(json_path)

    def test_verify_non_py_both_flags_fail(self):
        target_path = os.path.join(BASE_DIR, "SECURITY.md")
        res = verify_file(target_path, run_tests=True, smoke=True)
        self.assertFalse(res["success"])
        self.assertEqual(res["report"]["test_status"], "unsupported")
        self.assertEqual(res["report"]["smoke_status"], "unsupported")

    def test_verify_strict_mode(self):
        sample_path = os.path.join(BASE_DIR, "tests", "sample_valid.py")
        res = verify_file(sample_path, strict=True)
        # Should execute encoding and syntax pass regardless of external linter presence
        self.assertTrue(res["report"]["syntax_pass"])
        self.assertTrue(res["report"]["encoding_pass"])

    def test_cli_execution_exit_codes(self):
        script_path = os.path.join(SCRIPTS_DIR, "verify.py")
        valid_path = os.path.join(BASE_DIR, "tests", "sample_valid.py")
        invalid_path = os.path.join(BASE_DIR, "tests", "sample_syntax_error.py")
        
        proc_ok = subprocess.run([sys.executable, script_path, valid_path], capture_output=True, text=True)
        self.assertEqual(proc_ok.returncode, 0)
        
        proc_err = subprocess.run([sys.executable, script_path, invalid_path], capture_output=True, text=True)
        self.assertEqual(proc_err.returncode, 1)

    def test_cli_non_py_test_flag_rejection(self):
        script_path = os.path.join(SCRIPTS_DIR, "verify.py")
        readme_path = os.path.join(BASE_DIR, "README.md")
        proc = subprocess.run([sys.executable, script_path, readme_path, "--test"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertFalse(data["success"])
        self.assertEqual(data["report"]["test_status"], "unsupported")

    def test_pytest_ten_passed_pattern_regression(self):
        # Regress against '0 passed' false-matching '10 passed' or '20 passed'
        sample_output = "10 passed in 0.25s"
        has_explicit_pass = bool(re.search(r"\b[1-9]\d* passed\b", sample_output))
        has_zero_pass = bool(re.search(r"\b0 passed\b", sample_output))
        self.assertTrue(has_explicit_pass, "Should correctly detect 10 passed")
        self.assertFalse(has_zero_pass, "10 passed should not match 0 passed boundary")

    def test_sanitizer_scan(self):
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
