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
    parse_pytest_xml,
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

    def test_pytest_parse_contradictory_summary_fails(self):
        # Contradictory summary with failed count reported alongside passed count
        raw_output = "1 passed, 1 failed in 0.05s"
        passed, out = parse_pytest_output(0, raw_output)
        self.assertFalse(passed, "Contradictory summary with failed count must fail.")

    def test_pytest_xml_parsing(self):
        # Directly test parse_pytest_xml with structured JUnit XML
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_pass_file = os.path.join(tmp_dir, "pass.xml")
            with open(xml_pass_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="5"><testcase name="t1"/></testsuite>')
            passed, msg = parse_pytest_xml(xml_pass_file)
            self.assertTrue(passed, msg)

            xml_fail_file = os.path.join(tmp_dir, "fail.xml")
            with open(xml_fail_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuite name="pytest" errors="0" failures="1" skipped="0" tests="5"></testsuite>')
            passed_f, msg_f = parse_pytest_xml(xml_fail_file)
            self.assertFalse(passed_f, msg_f)

    def test_pytest_xml_multi_suites_aggregation(self):
        # Multiple testsuites aggregation: if second suite fails, whole result must fail
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "multi.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuites>'
                        '<testsuite name="s1" errors="0" failures="0" skipped="0" tests="2"/>'
                        '<testsuite name="s2" errors="0" failures="1" skipped="0" tests="3"/>'
                        '</testsuites>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "Multi-suite with any failure must fail.")

    def test_pytest_xml_negative_counter_fails(self):
        # Negative counter values must be rejected
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "negative.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="-1"/>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "Negative tests counter must fail.")

    def test_pytest_xml_direct_failure_tag_detected(self):
        # Counter attributes lie (failures=0), but direct <failure> tag exists in XML
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "stealth_fail.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2">'
                        '<testcase name="c1"><failure message="error">crash</failure></testcase>'
                        '</testsuite>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "Stealth failure tag must be detected and rejected.")

    def test_pytest_xml_all_skipped_fails(self):
        # All tests skipped (pure passed count is 0) must fail
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "all_skipped.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<testsuite name="pytest" errors="0" failures="0" skipped="2" tests="2"/>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "All skipped in XML must fail.")

    def test_unittest_parse_clean_ok_passes(self):
        # Positive test: clean unittest OK output
        raw_output = "Ran 1 test in 0.001s\n\nOK"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertTrue(passed, f"Clean OK should pass: {out}")

    def test_unittest_parse_passed_with_expected_failures(self):
        # Positive test: OK with 1 expected failure out of 2 tests (1 pure passed) should succeed
        raw_output = "Ran 2 tests in 0.001s\n\nOK (expected failures=1)"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertTrue(passed, f"OK with 1 pure pass and 1 expected failure should pass: {out}")

    def test_unittest_parse_all_expected_failures_fails(self):
        # Negative test: Ran 1 test, expected failures=1 (pure passed = 0) must fail
        raw_output = "Ran 1 test in 0.001s\n\nOK (expected failures=1)"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, f"OK with 0 pure passed tests must fail: {out}")

    def test_unittest_parse_contradictory_ok_with_failures_fails(self):
        # Negative test: OK (failures=1) counter contradiction must fail
        raw_output = "Ran 1 test in 0.001s\n\nOK (failures=1)"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, f"Contradictory OK (failures=1) must fail: {out}")

    def test_unittest_parse_all_skipped_with_zero_expected_fails(self):
        # Counterexample: OK (skipped=1, expected failures=0) must fail
        raw_output = "Ran 1 test in 0.001s\n\nOK (skipped=1, expected failures=0)"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, f"All skipped with 0 expected failures must fail: {out}")

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

    def test_json_reject_nan_infinity(self):
        # RFC 8259 strict compliance: NaN and Infinity must fail
        with tempfile.TemporaryDirectory() as tmp_dir:
            nan_file = os.path.join(tmp_dir, "nan.json")
            with open(nan_file, "w", encoding="utf-8") as f:
                f.write('{"val": NaN}')
            res = verify_file(nan_file)
            self.assertFalse(res["success"], "JSON with NaN must fail.")

            inf_file = os.path.join(tmp_dir, "inf.json")
            with open(inf_file, "w", encoding="utf-8") as f:
                f.write('{"val": Infinity}')
            res2 = verify_file(inf_file)
            self.assertFalse(res2["success"], "JSON with Infinity must fail.")

    def test_markdown_syntax_pass_is_none(self):
        # Markdown and text files must have syntax_pass as None (unsupported linter), not True
        with tempfile.TemporaryDirectory() as tmp_dir:
            md_file = os.path.join(tmp_dir, "sample.md")
            with open(md_file, "w", encoding="utf-8") as f:
                f.write("# Sample Markdown\n\nContent here.")
            res = verify_file(md_file)
            self.assertTrue(res["success"])
            self.assertIsNone(res["report"]["syntax_pass"], "Markdown syntax_pass should be None (not falsely claiming AST parsing).")
            self.assertTrue(res["report"]["encoding_pass"], "Encoding pass must be True.")

    def test_external_test_file_legacy_model_scanned(self):
        # External project's test_*.py must NOT be exempt from legacy model scan
        legacy_name = "gpt-4o"
        with tempfile.TemporaryDirectory() as tmp_dir:
            ext_test_file = os.path.join(tmp_dir, "test_external.py")
            with open(ext_test_file, "w", encoding="utf-8") as f:
                f.write(f'# External test file\nMODEL_NAME = "{legacy_name}"\n')
            res = verify_file(ext_test_file)
            self.assertFalse(res["success"], "External test file with legacy model must fail.")
            self.assertEqual(res["report"]["model_scan_status"], "failed")

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
