"""
Unit tests for synapse-harness verify.py and model_sanitizer.py.
"""

import os
import sys
import unittest
import subprocess
import json
import tempfile

# Suppress bytecode generation
sys.dont_write_bytecode = True

# Ensure scripts dir is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from verify import (
    verify_file,
    parse_pytest_output,
    parse_unittest_output,
)
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

    def test_verify_non_py_json_with_test_flag_fails_isolated(self):
        # Safely create JSON in an isolated temporary directory (no workspace pollution)
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = os.path.join(tmp_dir, "isolated_test.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write('{"test": true}')
            res = verify_file(json_path, run_tests=True)
            self.assertFalse(res["success"], "Requesting --test on JSON must fail.")
            self.assertEqual(res["report"]["test_status"], "unsupported")

    def test_verify_non_py_json_with_smoke_flag_fails_isolated(self):
        # Safely create JSON in an isolated temporary directory (no workspace pollution)
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = os.path.join(tmp_dir, "isolated_test_smoke.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write('{"test": true}')
            res = verify_file(json_path, smoke=True)
            self.assertFalse(res["success"], "Requesting --smoke on JSON must fail.")
            self.assertEqual(res["report"]["smoke_status"], "unsupported")

    def test_verify_non_py_both_flags_fail(self):
        target_path = os.path.join(BASE_DIR, "SECURITY.md")
        res = verify_file(target_path, run_tests=True, smoke=True)
        self.assertFalse(res["success"])
        self.assertEqual(res["report"]["test_status"], "unsupported")
        self.assertEqual(res["report"]["smoke_status"], "unsupported")

    def test_verify_strict_mode(self):
        sample_path = os.path.join(BASE_DIR, "tests", "sample_valid.py")
        res = verify_file(sample_path, strict=True)
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

    def test_pytest_parse_ten_passed(self):
        # Directly test parse_pytest_output with 10 passed in summary line
        raw_output = "rootdir: /test\ncollected 10 items\n\n= 10 passed in 0.15s ="
        passed, out = parse_pytest_output(0, raw_output)
        self.assertTrue(passed, f"10 passed must succeed: {out}")

    def test_pytest_parse_warning_with_passed_text_fails_when_zero_pass(self):
        # Warning contains '1 passed' text but summary is 0 passed
        raw_output = "UserWarning: previous run had 1 passed\ncollected 1 item\n\n= 0 passed, 1 skipped in 0.05s ="
        passed, out = parse_pytest_output(0, raw_output)
        self.assertFalse(passed, "0 passed summary with warning text must fail.")

    def test_pytest_parse_warning_with_skipped_only_fails(self):
        # Warning contains '1 passed' text and summary is 1 skipped (no passed)
        raw_output = "UserWarning: previous run had 1 passed\n1 skipped in 0.05s"
        passed, out = parse_pytest_output(0, raw_output)
        self.assertFalse(passed, "Skipped only with warning text must fail.")

    def test_pytest_parse_trailing_warning_after_skipped_fails(self):
        # Counterexample: 1 skipped summary followed by trailing warning on the last line
        raw_output = "1 skipped in 0.05s\nUserWarning: previous run had 1 passed"
        passed, out = parse_pytest_output(0, raw_output)
        self.assertFalse(passed, "Trailing warning after skipped summary must not cause false PASS.")

    def test_pytest_parse_fake_warning_with_summary_pattern_fails(self):
        # Counterexample: fake summary line with arbitrary text (UserWarning previous run had 1 passed in 0.05s)
        raw_output = "1 skipped in 0.05s\n1 UserWarning previous run had 1 passed in 0.05s"
        passed, out = parse_pytest_output(0, raw_output)
        self.assertFalse(passed, "Arbitrary non-pytest keyword line must not be recognized as summary.")

    def test_unittest_parse_all_skipped_fails(self):
        # Directly test parse_unittest_output when all tests are skipped
        raw_output = "test_foo (tests.test_bar) ... skipped 'reason'\n\nRan 2 tests in 0.001s\n\nOK (skipped=2)"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, f"All skipped tests must fail: {out}")

    def test_unittest_parse_zero_tests_fails(self):
        raw_output = "\nRan 0 tests in 0.000s\n\nOK"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, "Ran 0 tests must fail.")

    def test_unittest_parse_no_summary_fails(self):
        # Missing unittest execution summary line must fail
        raw_output = "module initialization message"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, "Missing summary must fail.")

    def test_unittest_parse_mixed_progress_all_skipped_fails(self):
        # Counterexample: progress message contains 'Ran 2 tests' but final block is all skipped
        raw_output = "progress: Ran 2 tests in 0.01s\ns\n-----\nRan 1 test in 0.001s\n\nOK (skipped=1)"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, "Final block with all skipped must fail even if earlier line had higher test count.")

    def test_unittest_parse_prefixed_ran_mixed_blocks_fails(self):
        # Counterexample: earlier valid all-skipped block followed by prefixed progress and arbitrary OK line
        raw_output = "Ran 1 test in 0.001s\n\nOK (skipped=1)\nprogress: Ran 2 tests in 0.01s\nOK: progress continued"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, "Prefixed progress lines and arbitrary OK lines must not be parsed as unittest summary block.")

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
