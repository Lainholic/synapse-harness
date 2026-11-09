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

from unittest.mock import patch
from verify import (
    verify_file,
    run_unit_test,
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
        if res["report"]["linter_status"] == "not_installed" or res["report"]["type_check_status"] == "not_installed":
            self.assertFalse(res["success"], "Strict mode must fail when external linters/type checkers are missing.")
        else:
            self.assertTrue(res["success"])

    @patch("subprocess.run")
    def test_verify_strict_mode_missing_linter_failure(self, mock_run):
        # 1. Simulate ruff missing only
        def side_effect_ruff_missing(cmd, *args, **kwargs):
            if cmd[0] == "ruff":
                raise FileNotFoundError("ruff not found")
            return subprocess.CompletedProcess(cmd, 0, stdout="Success: no issues found\n", stderr="")

        mock_run.side_effect = side_effect_ruff_missing
        sample_path = os.path.join(BASE_DIR, "tests", "sample_valid.py")
        res1 = verify_file(sample_path, strict=True)
        self.assertFalse(res1["success"], "Strict mode must fail when only ruff is missing.")
        self.assertEqual(res1["report"]["linter_status"], "not_installed")
        self.assertEqual(res1["report"]["type_check_status"], "pass")

        # 2. Simulate mypy missing only
        def side_effect_mypy_missing(cmd, *args, **kwargs):
            if cmd[0] == "mypy":
                raise FileNotFoundError("mypy not found")
            return subprocess.CompletedProcess(cmd, 0, stdout="All checks passed\n", stderr="")

        mock_run.side_effect = side_effect_mypy_missing
        res2 = verify_file(sample_path, strict=True)
        self.assertFalse(res2["success"], "Strict mode must fail when only mypy is missing.")
        self.assertEqual(res2["report"]["type_check_status"], "not_installed")
        self.assertEqual(res2["report"]["linter_status"], "pass")

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
        # Directly test parse_pytest_xml with structured JUnit XML (tests count matches testcase count)
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_pass_file = os.path.join(tmp_dir, "pass.xml")
            with open(xml_pass_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="1"><testcase name="t1"/></testsuite>')
            passed, msg = parse_pytest_xml(xml_pass_file)
            self.assertTrue(passed, msg)

            xml_fail_file = os.path.join(tmp_dir, "fail.xml")
            with open(xml_fail_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuite name="pytest" errors="0" failures="1" skipped="0" tests="1"><testcase name="t1"><failure message="fail"/></testcase></testsuite>')
            passed_f, msg_f = parse_pytest_xml(xml_fail_file)
            self.assertFalse(passed_f, msg_f)

    def test_pytest_xml_orphan_testcase_fails(self):
        # Counterexample: valid testcase inside suite s1, but an orphan testcase tag exists outside of any suite
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "orphan.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuites>'
                        '<testsuite name="s1" errors="0" failures="0" skipped="0" tests="1">'
                        '<testcase name="valid"/>'
                        '</testsuite>'
                        '<testcase name="orphan"/>'
                        '</testsuites>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "Orphan testcase outside testsuite must fail.")
            self.assertIn("고아", msg)

    def test_pytest_xml_empty_suite_counter_mismatch_fails(self):
        # Counterexample: s1 has 1 testcase (tests=1), but s2 claims tests=1 with 0 testcases
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "empty_mismatch.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuites>'
                        '<testsuite name="s1" errors="0" failures="0" skipped="0" tests="1"><testcase name="t1"/></testsuite>'
                        '<testsuite name="s2" errors="0" failures="0" skipped="0" tests="1"></testsuite>'
                        '</testsuites>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "Multi-suite where second suite is empty but claims tests=1 must fail.")
            self.assertIn("불일치", msg)

    def test_pytest_xml_tests_count_mismatch_fails(self):
        # Counterexample: tests attribute claims 5 tests, but only 1 testcase tag exists
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "mismatch.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="5"><testcase name="t1"/></testsuite>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "Mismatch between tests count and testcase elements must fail.")

    def test_pytest_xml_no_testcase_tags_fails(self):
        # Counterexample: tests="1" but no actual testcase elements exist
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "no_cases.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="1"></testsuite>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "XML with zero testcase elements must fail.")

    def test_pytest_xml_multi_suites_aggregation(self):
        # Multiple testsuites aggregation: if second suite fails, whole result must fail
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "multi.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?><testsuites>'
                        '<testsuite name="s1" errors="0" failures="0" skipped="0" tests="1"><testcase name="t1"/></testsuite>'
                        '<testsuite name="s2" errors="0" failures="1" skipped="0" tests="1"><testcase name="t2"><failure message="err"/></testcase></testsuite>'
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
                f.write('<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="1">'
                        '<testcase name="c1"><failure message="error">crash</failure></testcase>'
                        '</testsuite>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "Stealth failure tag must be detected and rejected.")

    def test_pytest_xml_skipped_count_mismatch_fails(self):
        # Counterexample: skipped attribute claims 2, but only 1 skipped tag exists
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "skip_mismatch.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<testsuite name="pytest" errors="0" failures="0" skipped="2" tests="2">'
                        '<testcase name="a"/>'
                        '<testcase name="b"><skipped/></testcase>'
                        '</testsuite>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "Mismatch between skipped attribute and skipped elements must fail.")

    def test_pytest_xml_all_skipped_fails(self):
        # All tests skipped (pure passed count is 0) must fail
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_file = os.path.join(tmp_dir, "all_skipped.xml")
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<testsuite name="pytest" errors="0" failures="0" skipped="2" tests="2">'
                        '<testcase name="c1"><skipped/></testcase><testcase name="c2"><skipped/></testcase>'
                        '</testsuite>')
            passed, msg = parse_pytest_xml(xml_file)
            self.assertFalse(passed, "All skipped in XML must fail.")

    def test_unittest_parse_duplicate_keys_fails(self):
        # Counterexample: duplicate keys in OK parenthesis
        raw_output = "Ran 1 test in 0.001s\n\nOK (skipped=0, skipped=1)"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, "Duplicate keys in unittest summary must fail.")

    def test_unittest_parse_unknown_key_fails(self):
        # Counterexample: unknown key in OK parenthesis
        raw_output = "Ran 1 test in 0.001s\n\nOK (unknown=1)"
        passed, out = parse_unittest_output(0, raw_output)
        self.assertFalse(passed, "Unknown key in unittest summary must fail.")

    def test_unittest_parse_empty_token_trailing_comma_fails(self):
        # Counterexample: trailing comma or consecutive empty commas in OK parenthesis
        raw_output1 = "Ran 1 test in 0.001s\n\nOK (skipped=0,,)"
        passed1, out1 = parse_unittest_output(0, raw_output1)
        self.assertFalse(passed1, "Consecutive empty commas must fail.")

        raw_output2 = "Ran 1 test in 0.001s\n\nOK (skipped=0,)"
        passed2, out2 = parse_unittest_output(0, raw_output2)
        self.assertFalse(passed2, "Trailing comma must fail.")

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

    def test_pytest_hijacking_mitigated(self):
        # Even if a fake pytest.py exists in the test directory,
        # run_unit_test must not be hijacked to produce a fake PASS without valid JUnit XML
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_pytest = os.path.join(tmp_dir, "pytest.py")
            with open(fake_pytest, "w", encoding="utf-8") as f:
                f.write('print("1 passed in 0.01s")\nimport sys; sys.exit(0)\n')

            test_file = os.path.join(tmp_dir, "test_dummy.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write('import unittest\nclass Dummy(unittest.TestCase):\n    def test_ok(self):\n        pass\n')

            res = run_unit_test(test_file)
            # If pytest is installed, it runs real pytest (ignoring fake pytest.py) and passes via JUnit XML,
            # or if hijacked/broken, it must NOT produce a false pass.
            if res["runner"] == "pytest":
                # Real pytest will produce a valid JUnit XML with 1 testcase
                self.assertTrue(res["pass"])
            else:
                self.assertTrue(res["pass"])

    def test_unit_test_target_dir_import_success(self):
        # Nested directory structure: project/calc.py and project/tests/test_calc.py
        # run_unit_test must safely import calc from target_dir
        with tempfile.TemporaryDirectory() as tmp_dir:
            calc_py = os.path.join(tmp_dir, "calc.py")
            with open(calc_py, "w", encoding="utf-8") as f:
                f.write("def add(a, b):\n    return a + b\n")

            sub_tests = os.path.join(tmp_dir, "tests")
            os.makedirs(sub_tests, exist_ok=True)
            test_calc = os.path.join(sub_tests, "test_calc.py")
            with open(test_calc, "w", encoding="utf-8") as f:
                f.write("import unittest\nfrom calc import add\nclass TestCalc(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n")

            res = run_unit_test(test_calc, target_file=calc_py)
            self.assertTrue(res["pass"], f"Should succeed importing calc from target_dir: {res}")

    def test_unit_test_target_dir_priority_over_cwd(self):
        # Path collision test: target_dir/calc.py vs cwd/calc.py
        # target_dir must take precedence over cwd so the genuine target is tested
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_calc = os.path.join(tmp_dir, "calc.py")
            with open(target_calc, "w", encoding="utf-8") as f:
                f.write("def compute(): return 'genuine'\n")

            sub_tests = os.path.join(tmp_dir, "tests")
            os.makedirs(sub_tests, exist_ok=True)

            shadow_calc = os.path.join(sub_tests, "calc.py")
            with open(shadow_calc, "w", encoding="utf-8") as f:
                f.write("def compute(): return 'shadowed'\n")

            test_calc = os.path.join(sub_tests, "test_calc.py")
            with open(test_calc, "w", encoding="utf-8") as f:
                f.write("import unittest\nfrom calc import compute\nclass TestPriority(unittest.TestCase):\n    def test_val(self):\n        self.assertEqual(compute(), 'genuine')\n")

            # 1. Run specifically under pytest runner
            has_pytest = False
            try:
                import importlib.util
                has_pytest = importlib.util.find_spec("pytest") is not None
            except Exception:
                has_pytest = False

            if has_pytest:
                res_pytest = run_unit_test(test_calc, target_file=target_calc)
                self.assertEqual(res_pytest["runner"], "pytest")
                self.assertTrue(res_pytest["pass"], f"pytest runner must prioritize target_dir: {res_pytest}")

            # 2. Run specifically under unittest runner (by mocking find_spec to return None for pytest)
            with patch("importlib.util.find_spec", return_value=None):
                res_unittest = run_unit_test(test_calc, target_file=target_calc)
                self.assertEqual(res_unittest["runner"], "unittest")
                self.assertTrue(res_unittest["pass"], f"Unittest runner must also prioritize target_dir: {res_unittest}")

    def test_verify_compile_tempdir_oserror_handled(self):
        # OSError during TemporaryDirectory creation in compile step must be caught and reported as structured JSON
        with patch("tempfile.TemporaryDirectory", side_effect=OSError("Disk full / permission denied")):
            sample_path = os.path.join(BASE_DIR, "tests", "sample_valid.py")
            res = verify_file(sample_path)
            self.assertFalse(res["success"], "Compilation TemporaryDirectory OSError must cause failure.")
            self.assertFalse(res["report"]["syntax_pass"])
            self.assertIn("임시 디렉터리 격리 실패", " ".join(res["report"]["details"]))

    def test_json_file_read_oserror_encoding_false(self):
        # OSError when reading JSON file must set encoding_pass and syntax_pass to False (not claiming UTF-8 pass)
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = os.path.join(tmp_dir, "test.json")
            with open(json_file, "w", encoding="utf-8") as f:
                f.write('{"key": "value"}')

            with patch("builtins.open", side_effect=PermissionError("Access denied")):
                res = verify_file(json_file)
                self.assertFalse(res["success"])
                self.assertFalse(res["report"]["encoding_pass"], "OSError must set encoding_pass to False.")
                self.assertFalse(res["report"]["syntax_pass"], "OSError must set syntax_pass to False.")

    def test_smoke_import_target_dir_promoted_from_trailing(self):
        # When collision_dir is prepended in PYTHONPATH and target_dir is trailing,
        # smoke must actively promote target_dir to sys.path[0] so the genuine target helper is imported
        with tempfile.TemporaryDirectory() as root_tmp:
            collision_dir = os.path.join(root_tmp, "collision")
            os.makedirs(collision_dir, exist_ok=True)
            with open(os.path.join(collision_dir, "helper.py"), "w", encoding="utf-8") as f:
                f.write("def val(): return 'collision_bad'\n")

            target_dir = os.path.join(root_tmp, "target")
            os.makedirs(target_dir, exist_ok=True)
            with open(os.path.join(target_dir, "helper.py"), "w", encoding="utf-8") as f:
                f.write("def val(): return 'target_genuine'\n")

            main_py = os.path.join(target_dir, "main.py")
            with open(main_py, "w", encoding="utf-8") as f:
                f.write("import helper\nassert helper.val() == 'target_genuine'\n")

            # Simulate collision_dir preceding target_dir in PYTHONPATH
            env_backup = os.environ.get("PYTHONPATH", "")
            try:
                os.environ["PYTHONPATH"] = f"{collision_dir}{os.pathsep}{target_dir}"
                res = verify_file(main_py, smoke=True)
                self.assertTrue(res["success"], f"Target dir must be promoted over collision_dir in smoke: {res}")
                self.assertEqual(res["report"]["smoke_status"], "pass")
            finally:
                if env_backup:
                    os.environ["PYTHONPATH"] = env_backup
                else:
                    os.environ.pop("PYTHONPATH", None)

    def test_unit_test_pytest_tempdir_oserror_handled(self):
        # TemporaryDirectory creation OSError in run_unit_test pytest branch must be safely handled
        with patch("importlib.util.find_spec", return_value=True):
            with patch("tempfile.TemporaryDirectory", side_effect=OSError("Permission denied")):
                sample_test = os.path.join(BASE_DIR, "tests", "sample_calc_test.py")
                res = run_unit_test(sample_test)
                self.assertFalse(res["pass"])
                self.assertEqual(res["runner"], "pytest")
                self.assertEqual(res["returncode"], -1)
                self.assertIn("pytest 임시 디렉터리 격리 실패(생성/정리 OSError)", res["output"])

    def test_unit_test_pytest_tempdir_cleanup_oserror_handled(self):
        # TemporaryDirectory __exit__ cleanup failure (OSError) must also be cleanly caught
        class FailingCleanupTempDir:
            def __enter__(self):
                self.name = tempfile.mkdtemp()
                return self.name
            def __exit__(self, exc_type, exc_val, exc_tb):
                import shutil
                shutil.rmtree(self.name, ignore_errors=True)
                raise OSError("Cleanup failed (file locked)")

        with patch("importlib.util.find_spec", return_value=True):
            with patch("tempfile.TemporaryDirectory", side_effect=FailingCleanupTempDir):
                sample_test = os.path.join(BASE_DIR, "tests", "sample_calc_test.py")
                res = run_unit_test(sample_test)
                self.assertFalse(res["pass"])
                self.assertEqual(res["runner"], "pytest")
                self.assertEqual(res["returncode"], -1)
                self.assertIn("pytest 임시 디렉터리 격리 실패(생성/정리 OSError)", res["output"])

    def test_parse_pytest_xml_invalid_root_and_missing_tests(self):
        # 1. Invalid root tag (e.g. <unexpected>) must be rejected
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_root_xml = os.path.join(tmp_dir, "bad_root.xml")
            with open(bad_root_xml, "w", encoding="utf-8") as f:
                f.write('<unexpected><testsuite tests="1"><testcase name="t1"/></testsuite></unexpected>')
            ok, msg = parse_pytest_xml(bad_root_xml)
            self.assertFalse(ok)
            self.assertIn("JUnit XML 루트 태그가 유효하지 않습니다", msg)

        # 2. Missing 'tests' attribute in suite must be rejected
        with tempfile.TemporaryDirectory() as tmp_dir:
            no_tests_xml = os.path.join(tmp_dir, "no_tests.xml")
            with open(no_tests_xml, "w", encoding="utf-8") as f:
                f.write('<testsuite name="calc"><testcase name="t1"/></testsuite>')
            ok, msg = parse_pytest_xml(no_tests_xml)
            self.assertFalse(ok)
            self.assertIn("필수 속성 'tests'가 누락되었습니다", msg)

    def test_pytest_xml_oserror_propagates_to_runner(self):
        # 1. Direct parse_pytest_xml check: PermissionError during XML parsing must raise OSError
        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_xml = os.path.join(tmp_dir, "locked.xml")
            with open(dummy_xml, "w", encoding="utf-8") as f:
                f.write('<testsuite tests="0"/>')

            with patch("xml.etree.ElementTree.parse", side_effect=PermissionError("Locked file")):
                with self.assertRaises(OSError):
                    parse_pytest_xml(dummy_xml)

        # 2. Integration check: run_unit_test must catch XML parse PermissionError, preserve returncode & stdout, and report XML access error
        with patch("importlib.util.find_spec", return_value=True):
            with patch("subprocess.run") as mock_run:
                def fake_run(cmd, **kwargs):
                    # Create dummy xml_report so stat succeeds
                    for arg in cmd:
                        if arg.startswith("--junitxml="):
                            report_file = arg.split("=", 1)[1]
                            with open(report_file, "w", encoding="utf-8") as f:
                                f.write('<testsuite tests="0"/>')
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="1 passed\n", stderr="")

                mock_run.side_effect = fake_run
                with patch("verify.parse_pytest_xml", side_effect=PermissionError("XML access denied")):
                    sample_test = os.path.join(BASE_DIR, "tests", "sample_calc_test.py")
                    res = run_unit_test(sample_test)
                    self.assertFalse(res["pass"])
                    self.assertEqual(res["runner"], "pytest")
                    self.assertEqual(res["returncode"], 0)
                    self.assertIn("[JUnit XML 접근 오류 (OSError)]", res["output"])
                    self.assertIn("1 passed", res["output"])

                # 3. TOCTOU scenario: stat succeeds, but FileNotFoundError occurs during parsing -> must classify as XML missing
                with patch("verify.parse_pytest_xml", side_effect=FileNotFoundError("XML vanished")):
                    res2 = run_unit_test(sample_test)
                    self.assertFalse(res2["pass"])
                    self.assertEqual(res2["runner"], "pytest")
                    self.assertEqual(res2["returncode"], 0)
                    self.assertIn("[JUnit XML 누락 FAIL]", res2["output"])

                # 4. stat stage PermissionError -> must classify as XML access error (preserving returncode and output)
                with patch("os.stat", side_effect=PermissionError("stat denied")):
                    res3 = run_unit_test(sample_test)
                    self.assertFalse(res3["pass"])
                    self.assertEqual(res3["runner"], "pytest")
                    self.assertEqual(res3["returncode"], 0)
                    self.assertIn("[JUnit XML 접근 오류 (OSError)]", res3["output"])

                # 5. stat stage FileNotFoundError -> must classify as XML missing
                with patch("os.stat", side_effect=FileNotFoundError("no xml")):
                    res4 = run_unit_test(sample_test)
                    self.assertFalse(res4["pass"])
                    self.assertEqual(res4["runner"], "pytest")
                    self.assertEqual(res4["returncode"], 0)
                    self.assertIn("[JUnit XML 누락 FAIL]", res4["output"])

    def test_unit_test_subprocess_spawn_filenotfound_handled(self):
        # subprocess.run spawn failure (FileNotFoundError) must be cleanly reported without UnboundLocalError
        with patch("importlib.util.find_spec", return_value=True):
            with patch("subprocess.run", side_effect=FileNotFoundError("missing executable or cwd")):
                sample_test = os.path.join(BASE_DIR, "tests", "sample_calc_test.py")
                res = run_unit_test(sample_test)
                self.assertFalse(res["pass"])
                self.assertEqual(res["runner"], "pytest")
                self.assertEqual(res["returncode"], -1)
                self.assertIn("pytest 프로세스 시작 실패", res["output"])

    def test_smoke_import_self_module_in_sys_modules(self):
        # Module accessing sys.modules[__name__] must succeed in smoke import without KeyError
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample_py = os.path.join(tmp_dir, "self_ref.py")
            with open(sample_py, "w", encoding="utf-8") as f:
                f.write("import sys\ncur_mod = sys.modules[__name__]\nassert cur_mod is not None\n")

            res = verify_file(sample_py, smoke=True)
            self.assertTrue(res["success"], f"Module accessing sys.modules[__name__] must succeed: {res}")
            self.assertEqual(res["report"]["smoke_status"], "pass")

    def test_smoke_import_with_sibling_module(self):
        # Sibling import test: main.py imports helper.py in the same directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            helper_py = os.path.join(tmp_dir, "helper.py")
            with open(helper_py, "w", encoding="utf-8") as f:
                f.write("def get_data(): return 42\n")

            main_py = os.path.join(tmp_dir, "main.py")
            with open(main_py, "w", encoding="utf-8") as f:
                f.write("import helper\nres = helper.get_data()\n")

            res = verify_file(main_py, smoke=True)
            self.assertTrue(res["success"], f"Smoke test with sibling import must succeed: {res}")
            self.assertEqual(res["report"]["smoke_status"], "pass")

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
