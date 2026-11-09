import os
import sys
import json
import re
import tempfile
import py_compile
import subprocess
import argparse
import xml.etree.ElementTree as ET

# __pycache__ 잔여 생성을 원천 차단
sys.dont_write_bytecode = True

# 같은 디렉터리의 model_sanitizer 모듈 동적 로드
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    from model_sanitizer import scan_text
except ImportError:
    scan_text = None

def find_paired_test(file_path):
    """대상 파이썬 파일에 대응하는 단위 테스트 파일을 탐색합니다."""
    file_dir = os.path.dirname(file_path)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    
    candidates = [
        os.path.join(file_dir, f"test_{base_name}.py"),
        os.path.join(file_dir, "tests", f"test_{base_name}.py"),
        os.path.join(os.path.dirname(file_dir), "tests", f"test_{base_name}.py"),
        os.path.join(file_dir, f"{base_name}_test.py"),
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    return None

def parse_pytest_xml(xml_path):
    """JUnit XML 결과 파일을 전수 파싱하여 텍스트 출력 의존성 없는 구조화된 판정을 내립니다.
    모든 <testsuite>의 속성값과 실제 하위 태그(<testcase>, <skipped>, <failure>, <error>)의 일치성을 엄격히 검증합니다.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # 1. 루트가 testsuite인 경우와 하위 testsuite 요소를 모두 안전하게 포괄
        suites = []
        if root.tag == "testsuite":
            suites.append(root)
        suites.extend(root.findall(".//testsuite"))
            
        if not suites:
            return False, "JUnit XML 내에서 유효한 <testsuite> 요소를 찾을 수 없습니다."
            
        total_tests = 0
        total_failures = 0
        total_errors = 0
        total_skipped = 0
        
        for s in suites:
            try:
                t = int(s.attrib.get("tests", 0))
                f = int(s.attrib.get("failures", 0))
                e = int(s.attrib.get("errors", 0))
                sk = int(s.attrib.get("skipped", 0))
            except ValueError:
                return False, f"속성 카운터 정수 변환 실패: {s.attrib}"
                
            if t < 0 or f < 0 or e < 0 or sk < 0:
                return False, f"음수 카운터 속성 검출: {s.attrib}"
                
            total_tests += t
            total_failures += f
            total_errors += e
            total_skipped += sk

            # suite별 testcase 및 태그 개수 대조 (suite에 직접 속한 testcase, 0개라도 속성과 엄격 대조)
            suite_cases = s.findall("./testcase")
            if t != len(suite_cases):
                return False, f"suite '{s.attrib.get('name', '')}'의 tests 속성({t})과 실제 testcase 태그 수({len(suite_cases)})가 불일치합니다."
            suite_skipped = len([c for c in suite_cases if c.find("skipped") is not None])
            if sk != suite_skipped:
                return False, f"suite '{s.attrib.get('name', '')}'의 skipped 속성({sk})과 실제 skipped 태그 수({suite_skipped})가 불일치합니다."

        # 2. XML 전체 실제 태그 전수 수집 및 고아 태그 거부
        all_suite_cases = [c for s in suites for c in s.findall("./testcase")]
        direct_all_cases = root.findall(".//testcase")
        if root.tag == "testcase":
            direct_all_cases.append(root)
            
        if len(all_suite_cases) != len(direct_all_cases):
            return False, "testsuite 외부에 위치한 비정상 고아 <testcase> 태그가 검출되었습니다."

        all_cases = all_suite_cases
        direct_failures = len(root.findall(".//failure"))
        direct_errors = len(root.findall(".//error"))
        direct_skipped = len(root.findall(".//skipped"))
        
        # 실제 testcase 요소가 없거나 속성값과 불일치하는 가짜 XML 거부
        if len(all_cases) == 0:
            return False, f"XML 내에 실제 <testcase> 태그가 존재하지 않습니다 (tests 속성={total_tests})"
            
        if total_tests != len(all_cases):
            return False, f"전체 tests 속성값({total_tests})과 실제 <testcase> 태그 수({len(all_cases)})가 불일치합니다."

        if total_skipped != direct_skipped:
            return False, f"전체 skipped 속성값({total_skipped})과 실제 <skipped> 태그 수({direct_skipped})가 불일치합니다."

        if total_failures > 0 or total_errors > 0 or direct_failures > 0 or direct_errors > 0:
            return False, f"테스트 실패 또는 오류 발생 (failures={total_failures}, errors={total_errors}, direct_fail={direct_failures}, direct_err={direct_errors})"

        # 3. 실제 순수 성공(passed) testcase 추출 (failure, error, skipped가 없는 testcase)
        pure_passed_cases = [
            c for c in all_cases 
            if c.find("failure") is None and c.find("error") is None and c.find("skipped") is None
        ]
        
        if len(pure_passed_cases) == 0:
            return False, f"실행된 테스트 중 순수 통과한 <testcase>가 0개입니다 (전체={len(all_cases)}, skipped={direct_skipped})"
            
        return True, f"JUnit XML 구조 판정 성공 (tests={total_tests}, passed={len(pure_passed_cases)}, skipped={total_skipped}, failures={total_failures}, errors={total_errors})"
    except Exception as e:
        return False, f"XML 파싱 또는 검증 예외: {e}"

def parse_pytest_output(returncode, out):
    """pytest 터미널 출력에서 공식 요약 라인(summary line)만을 역순 탐색하여 엄격히 판정합니다."""
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not lines:
        return False, "[테스트 미실행] 출력이 비어 있습니다."
        
    kw = r"(?:passed|skipped|failed|errors?|xfailed|xpassed|warnings?)"
    item = rf"\d+\s+{kw}"
    summary_pattern = re.compile(
        rf"^(?:=+\s*(?:{item}(?:,\s*)?)+\s+in\s+[\d\.]+s\s*=+"
        rf"|(?:{item}(?:,\s*)?)+\s+in\s+[\d\.]+s"
        rf"|no tests ran in\s+[\d\.]+s)$"
    )
    
    summary_line = None
    for ln in reversed(lines):
        if summary_pattern.match(ln):
            summary_line = ln
            break
            
    if not summary_line:
        return False, f"[요약 누락] 유효한 pytest 실행 요약 라인을 찾을 수 없습니다:\n{out}"
        
    # 공식 요약 라인 내에서 판정 (실패/오류 카운터 존재 시 즉시 실패)
    m_pass = re.search(r"\b([1-9]\d*)\s+passed\b", summary_line)
    m_fail = re.search(r"\b([1-9]\d*)\s+(?:failed|errors?)\b", summary_line)
    m_zero_pass = re.search(r"\b0\s+passed\b", summary_line)
    has_no_tests = "no tests ran" in summary_line
    
    # 모순되거나 실패 카운터가 있는 경우 배제
    if m_fail:
        return False, f"[테스트 실패] 요약 라인에 실패/오류가 보고되었습니다: {summary_line}"
        
    passed = (returncode == 0) and bool(m_pass) and not bool(m_zero_pass) and not has_no_tests
    return passed, out if passed else f"[테스트 미실행 또는 실패]\n{out}"

def parse_unittest_output(returncode, out):
    """unittest 출력의 엄격한 요약 블록을 파싱하여 상태 및 카운터 모순을 정밀 검증합니다."""
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not lines:
        return False, "[테스트 미실행] 출력이 비어 있습니다."

    # 줄 시작(^)과 줄 끝($)을 엄격히 강제하며 요약 블록 파싱
    pattern = re.compile(
        r"^Ran\s+(\d+)\s+tests?\s+in\s+[\d\.]+s\s*$\n"
        r"^(OK(?:\s*\((?P<detail>[a-zA-Z0-9_=\s,]+)\))?|FAILED(?:\s*\(.*?\))?)\s*$",
        re.MULTILINE
    )
    summary_blocks = pattern.finditer(out)
    matches = list(summary_blocks)
    if not matches:
        return False, f"[요약 누락] 유효한 unittest 실행 요약 블록(^Ran N tests...$ + ^OK/FAILED$)이 없습니다:\n{out}"
        
    last_match = matches[-1]
    ran_count = int(last_match.group(1))
    full_status = last_match.group(2)
    detail = last_match.group("detail") or ""
    
    if ran_count == 0:
        return False, f"실행된 테스트 케이스가 0개입니다:\n{out}"

    if not full_status.startswith("OK"):
        return False, f"[테스트 실패]\n{out}"

    # OK 괄호 상세 내용 검증 (엄격한 화이트리스트 토큰 파서)
    if detail:
        # 연속 쉼표, 선행/후행 쉼표 등 빈 토큰 존재 시 즉각 거부
        raw_tokens = detail.split(",")
        if any(not t.strip() for t in raw_tokens):
            return False, f"[형식 오류] unittest 요약 괄호 내에 빈 토큰 또는 연속 쉼표가 포함되어 있습니다: '{detail}'"

        tokens = [t.strip() for t in raw_tokens]
        if not tokens:
            return False, f"[형식 오류] OK 상태 괄호 내용이 올바르지 않습니다: '{detail}'"

        counters = {}
        token_pattern = re.compile(r"^(skipped|expected failures|unexpected successes)=(\d+)$")
        
        for t in tokens:
            m = token_pattern.match(t)
            if not m:
                return False, f"[허용되지 않은 토큰] unittest 요약 괄호 내에 비표준 또는 모순된 항목이 포함되어 있습니다: '{t}' in '{detail}'"
            key = m.group(1)
            val = int(m.group(2))
            
            if key in counters:
                return False, f"[중복 키 검출] unittest 요약 괄호 내에 중복된 카운터 키가 존재합니다: '{key}' in '{detail}'"
            counters[key] = val

        skipped_count = counters.get("skipped", 0)
        expected_count = counters.get("expected failures", 0)
        unexpected_count = counters.get("unexpected successes", 0)

        if unexpected_count > 0:
            return False, f"예상치 못한 성공(unexpected successes={unexpected_count})이 발생하였습니다:\n{out}"

        # 유효 순수 성공 테스트 검증 (전부 skip 또는 expected failures만 있는 경우 거부)
        pure_passed = ran_count - skipped_count - expected_count
        if pure_passed <= 0:
            return False, f"실행된 테스트 중 순수 통과(passed)한 테스트가 0개입니다 (ran={ran_count}, skipped={skipped_count}, expected={expected_count}):\n{out}"

    passed = (returncode == 0)
    return passed, out if passed else f"[테스트 실패 (종료코드={returncode})]\n{out}"

def run_unit_test(test_file, target_file=None):
    """동일한 Python 인터프리터의 pytest(JUnit XML 필수) 또는 unittest로 테스트 파일을 격리 실행합니다.
    로컬 디렉터리의 모듈 하이재킹을 방어하면서도, 대상 모듈(target_file)의 상위 디렉터리를 러너 로드 후 안전하게 경로에 주입합니다.
    """
    test_dir = os.path.dirname(os.path.abspath(test_file))
    test_name = os.path.basename(test_file)
    target_dir = os.path.dirname(os.path.abspath(target_file)) if target_file else ""
    
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONSAFEPATH"] = "1"

    # 1. pytest 가용 여부 사전 검사
    has_pytest = False
    try:
        import importlib.util
        has_pytest = importlib.util.find_spec("pytest") is not None
    except Exception:
        has_pytest = False

    # Python 3.11+ 격리 플래그 (-P: sys.path[0]에 현재 디렉터리 자동 삽입 방지)
    safe_path_args = ["-P"] if sys.version_info >= (3, 11) else []

    if has_pytest:
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_report = os.path.join(tmp_dir, "junit_report.xml")
            try:
                # 러너 스크립트: sys.path에서 작업 디렉터리를 사전 제거하여 정품 pytest를 우선 로드한 뒤 대상 모듈 경로를 주입
                runner_code = (
                    "import sys, os\n"
                    "cwd = os.getcwd()\n"
                    f"target_dir = {repr(target_dir)}\n"
                    "sys.path = [p for p in sys.path if p not in ('', '.', cwd, target_dir)]\n"
                    "import pytest\n"
                    "if cwd not in sys.path: sys.path.insert(0, cwd)\n"
                    "if target_dir and target_dir not in sys.path: sys.path.insert(0, target_dir)\n"
                    "sys.exit(pytest.main(sys.argv[1:]))\n"
                )
                cmd = [sys.executable] + safe_path_args + ["-c", runner_code, "-q", f"--junitxml={xml_report}", test_name]
                res = subprocess.run(
                    cmd,
                    cwd=test_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                out = (res.stdout.strip() + "\n" + res.stderr.strip()).strip()
                
                # JUnit XML 필수 판정 (XML 미생성 또는 파싱 실패 시 텍스트 파서 폴백 금지)
                if not os.path.isfile(xml_report) or os.path.getsize(xml_report) == 0:
                    return {
                        "runner": "pytest",
                        "pass": False,
                        "output": f"[JUnit XML 누락 FAIL] pytest 보고서 XML이 생성되지 않았습니다:\n{out}",
                        "returncode": res.returncode
                    }

                xml_pass, xml_msg = parse_pytest_xml(xml_report)
                return {
                    "runner": "pytest",
                    "pass": (res.returncode == 0) and bool(xml_pass),
                    "output": out if (xml_pass and res.returncode == 0) else f"[JUnit XML 검증 실패]\n{xml_msg}\n{out}",
                    "returncode": res.returncode
                }
            except subprocess.TimeoutExpired:
                return {"runner": "pytest", "pass": False, "output": "pytest 실행 시간 초과 (15초)", "returncode": -1}
            except Exception as e:
                return {"runner": "pytest", "pass": False, "output": f"pytest 실행 실패: {e}", "returncode": -1}

    # 2. pytest 미설치 시 파이썬 내장 unittest로 실행
    try:
        runner_code = (
            "import sys, os\n"
            "cwd = os.getcwd()\n"
            f"target_dir = {repr(target_dir)}\n"
            "sys.path = [p for p in sys.path if p not in ('', '.', cwd, target_dir)]\n"
            "import unittest\n"
            "if cwd not in sys.path: sys.path.insert(0, cwd)\n"
            "if target_dir and target_dir not in sys.path: sys.path.insert(0, target_dir)\n"
            "unittest.main(module=None, argv=[sys.argv[0]] + sys.argv[1:])\n"
        )
        cmd = [sys.executable] + safe_path_args + ["-c", runner_code, test_name]
        res = subprocess.run(
            cmd,
            cwd=test_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=15
        )
        out = (res.stdout.strip() + "\n" + res.stderr.strip()).strip()
        passed, formatted_output = parse_unittest_output(res.returncode, out)
        return {
            "runner": "unittest",
            "pass": passed,
            "output": formatted_output,
            "returncode": res.returncode
        }
    except subprocess.TimeoutExpired:
        return {"runner": "unittest", "pass": False, "output": "unittest 실행 시간 초과 (15초)", "returncode": -1}
    except Exception as e:
        return {"runner": "unittest", "pass": False, "output": f"unittest 실행 실패: {e}", "returncode": -1}

def run_smoke_import(file_path):
    """모듈을 서브프로세스에서 임포트하여 즉각적인 초기화 런타임 크래시를 검증합니다.
    대상 모듈이 속한 디렉터리를 sys.path에 안전하게 주입하여 형제 모듈 임포트를 보장합니다.
    """
    code = (
        "import sys, os, importlib.util\n"
        "sys.dont_write_bytecode = True\n"
        "target = sys.argv[1]\n"
        "target_dir = os.path.dirname(os.path.abspath(target))\n"
        "if target_dir not in sys.path: sys.path.insert(0, target_dir)\n"
        "spec = importlib.util.spec_from_file_location('__harness_smoke__', target)\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
    )
    try:
        res = subprocess.run(
            [sys.executable, "-c", code, file_path],
            capture_output=True,
            text=True,
            timeout=5
        )
        return {
            "pass": res.returncode == 0,
            "output": (res.stdout.strip() + "\n" + res.stderr.strip()).strip(),
            "returncode": res.returncode
        }
    except subprocess.TimeoutExpired:
        return {"pass": False, "output": "스모크 임포트 시간 초과 (5초)", "returncode": -1}
    except Exception as e:
        return {"pass": False, "output": f"스모크 임포트 실패: {e}", "returncode": -1}

def verify_file(file_path, run_tests=False, smoke=False, strict=False):
    if not isinstance(file_path, str) or not file_path.strip():
        return {"success": False, "error": "유효한 파일 경로가 필요합니다."}

    file_path = os.path.abspath(file_path.strip())
    
    if not os.path.exists(file_path):
        return {"success": False, "error": f"파일을 찾을 수 없습니다: {file_path}"}
    
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"일반 파일이 아닙니다(디렉터리 등): {file_path}"}
    
    ext = os.path.splitext(file_path)[1].lower()
    
    report = {
        "file": file_path,
        "extension": ext,
        "encoding_pass": False,
        "syntax_pass": False,
        "linter_status": "unsupported",  # pass, failed, not_installed, timeout, error, unsupported
        "type_check_status": "unsupported",
        "smoke_status": "skipped",
        "test_status": "skipped",
        "model_scan_status": "skipped",
        "linter_details": "",
        "details": []
    }
    
    overall_success = True

    # [핵심 검증] 비 Python 파일에 --test 또는 --smoke 플래그가 요청된 경우 즉각 실패 처리
    if ext != ".py" and (run_tests or smoke):
        overall_success = False
        if run_tests:
            report["test_status"] = "unsupported"
            report["details"].append(f"[옵션 오류] --test 옵션은 Python(.py) 대상에서만 지원됩니다. ({ext} 파일 미지원)")
        if smoke:
            report["smoke_status"] = "unsupported"
            report["details"].append(f"[옵션 오류] --smoke 옵션은 Python(.py) 대상에서만 지원됩니다. ({ext} 파일 미지원)")
        return {"success": False, "report": report}

    # 1. 파이썬 문법, 린터, 타입, 옵션별 런타임 검사
    if ext == ".py":
        # 인코딩 검사
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.read()
            report["encoding_pass"] = True
        except UnicodeDecodeError as e:
            report["encoding_pass"] = False
            report["syntax_pass"] = False
            report["details"].append(f"UTF-8 디코딩 오류: {str(e)}")
            return {"success": False, "report": report}

        # 자체 바이트코드 잔여 방지를 위해 임시 디렉터리에서 컴파일 수행
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_cfile = os.path.join(tmp_dir, "temp_check.pyc")
            try:
                py_compile.compile(file_path, cfile=temp_cfile, doraise=True)
                report["syntax_pass"] = True
                report["details"].append("py_compile 구문 검사 PASS (격리 컴파일 완료)")
            except py_compile.PyCompileError as e:
                report["syntax_pass"] = False
                report["details"].append(f"구문 오류(SyntaxError): {str(e)}")
                return {"success": False, "report": report}

        # ruff 린터 정적 분석 (--no-fix 명시하여 검수 시 원본 불변 보장)
        try:
            res = subprocess.run(
                ["ruff", "check", "--no-fix", file_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0:
                report["linter_status"] = "pass"
                report["details"].append("ruff 정적 린터 PASS")
            else:
                report["linter_status"] = "failed"
                overall_success = False
                err_output = (res.stdout.strip() + "\n" + res.stderr.strip()).strip()
                report["linter_details"] = err_output
                report["details"].append(f"ruff 지적 사항 (ExitCode {res.returncode}):\n{err_output}")
        except FileNotFoundError:
            report["linter_status"] = "not_installed"
            report["details"].append("ruff 미설치 (내장 py_compile 검사로 진행)")
            if strict:
                overall_success = False
                report["details"].append("[엄격 모드 FAIL] ruff 린터가 설치되지 않았습니다.")
        except subprocess.TimeoutExpired:
            report["linter_status"] = "timeout"
            overall_success = False
            report["details"].append("ruff 검사 시간 초과(5초)")
        except Exception as e:
            report["linter_status"] = "error"
            overall_success = False
            report["details"].append(f"ruff 실행 중 예외 발생: {str(e)}")

        # mypy 정적 타입 검사 (설치된 경우 실행, 악성 플러그인 로드 방지를 위해 config-file 빈 파일 지정)
        try:
            m_res = subprocess.run(
                ["mypy", "--ignore-missing-imports", "--config-file", os.devnull, file_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            if m_res.returncode == 0:
                report["type_check_status"] = "pass"
                report["details"].append("mypy 정적 타입 검사 PASS")
            else:
                report["type_check_status"] = "failed"
                overall_success = False
                m_err = (m_res.stdout.strip() + "\n" + m_res.stderr.strip()).strip()
                report["details"].append(f"mypy 타입 검사 지적:\n{m_err}")
        except FileNotFoundError:
            report["type_check_status"] = "not_installed"
            if strict:
                overall_success = False
                report["details"].append("[엄격 모드 FAIL] mypy 타입 검사기가 설치되지 않았습니다.")
        except subprocess.TimeoutExpired:
            report["type_check_status"] = "timeout"
            overall_success = False
            report["details"].append("mypy 검사 시간 초과(10초)")
        except Exception as e:
            report["type_check_status"] = "error"
            overall_success = False
            report["details"].append(f"mypy 실행 중 예외 발생: {str(e)}")

        # 스모크 테스트 (사용자가 명시적으로 --smoke를 요청한 경우에만 실행)
        if smoke:
            smoke_res = run_smoke_import(file_path)
            if smoke_res["pass"]:
                report["smoke_status"] = "pass"
                report["details"].append("스모크 임포트 실행 검증 PASS (런타임 크래시 없음)")
            else:
                report["smoke_status"] = "failed"
                overall_success = False
                report["details"].append(f"[스모크 테스트 FAIL] 임포트 시 런타임 크래시 발생:\n{smoke_res['output']}")

        # 단위 테스트 (사용자가 명시적으로 --test를 요청한 경우에만 실행)
        if run_tests:
            paired_test = find_paired_test(file_path)
            target_test = paired_test if paired_test else file_path
            
            # 대상 파일이 test_ 로 시작하거나 대응 테스트가 존재하는 경우에만 실행
            base = os.path.basename(target_test).lower()
            if base.startswith("test_") or base.endswith("_test.py"):
                test_res = run_unit_test(target_test, target_file=file_path)
                if test_res["pass"]:
                    report["test_status"] = "pass"
                    report["details"].append(f"단위 테스트 실행 PASS ({test_res['runner']}: {os.path.basename(target_test)})")
                else:
                    report["test_status"] = "failed"
                    overall_success = False
                    report["details"].append(f"[단위 테스트 FAIL] ({test_res['runner']}):\n{test_res['output']}")
            else:
                report["test_status"] = "not_found"
                overall_success = False
                report["details"].append("[단위 테스트 FAIL] 대응하는 단위 테스트 파일(test_*.py)을 찾지 못하여 테스트를 수행할 수 없습니다.")

    # 2. JSON 파싱 검사 (엄격한 RFC 8259 표준 준수: 비표준 상수 NaN, Infinity 거부)
    elif ext == ".json":
        def reject_constant(c):
            raise ValueError(f"비표준 JSON 상수 '{c}' 검출 (RFC 8259 위반)")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f, parse_constant=reject_constant)
            report["encoding_pass"] = True
            report["syntax_pass"] = True
            report["linter_status"] = "pass"
            report["details"].append("JSON 구문 파싱 PASS (표준 규격 준수)")
        except UnicodeDecodeError as e:
            report["encoding_pass"] = False
            report["syntax_pass"] = False
            report["linter_status"] = "failed"
            report["details"].append(f"UTF-8 디코딩 오류: {str(e)}")
            return {"success": False, "report": report}
        except Exception as e:
            report["encoding_pass"] = True
            report["syntax_pass"] = False
            report["linter_status"] = "failed"
            report["details"].append(f"JSON 파싱 실패: {str(e)}")
            return {"success": False, "report": report}

    # 3. 기타 텍스트/마크다운 파일
    elif ext in ("", ".md", ".txt", ".cs", ".html", ".css", ".js", ".ts") or os.path.basename(file_path).lower() in ("license", "dockerfile", "makefile"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.read()
            report["encoding_pass"] = True
            report["syntax_pass"] = None  # 언어별 전용 AST 구문 분석기는 미실행 (not_checked)
            report["linter_status"] = "unsupported"
            report["details"].append("UTF-8 텍스트 인코딩 및 읽기 무결성 PASS (언어별 전용 AST 구문 분석기는 미실행)")
        except UnicodeDecodeError as e:
            report["encoding_pass"] = False
            report["syntax_pass"] = False
            report["details"].append(f"UTF-8 인코딩 디코딩 오류: {str(e)}")
            return {"success": False, "report": report}
        except Exception as e:
            report["encoding_pass"] = False
            report["syntax_pass"] = False
            report["details"].append(f"파일 읽기 오류: {str(e)}")
            return {"success": False, "report": report}

    else:
        report["details"].append(f"지원되지 않는 확장자({ext})입니다.")
        overall_success = False

    # 4. 공통 구형 모델명 기계적 린터 검사
    harness_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    canon_target = os.path.realpath(file_path)
    is_inside_harness = canon_target.startswith(harness_root + os.sep) or canon_target == harness_root
    
    is_self_tool = (
        canon_target == os.path.realpath(__file__) or
        canon_target == os.path.realpath(os.path.join(script_dir, "model_sanitizer.py")) or
        canon_target == os.path.realpath(os.path.join(script_dir, "..", "SKILL.md")) or
        (is_inside_harness and os.path.basename(canon_target).startswith("test_"))
    )
    
    if not is_self_tool and ext in (".py", ".md", ".txt", ".cs", ".html", ".css", ".js", ".ts", ".json"):
        if scan_text:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content_to_check = f.read()
                legacy_findings = scan_text(content_to_check)
                if legacy_findings:
                    overall_success = False
                    report["model_scan_status"] = "failed"
                    report["details"].append(
                        f"[구형 모델명 감지 FAIL] 레거시 모델명이 감지되었습니다: {legacy_findings}. "
                        f"python scripts/model_sanitizer.py --fix \"{file_path}\" 로 최신 규격(Gemini 3.8/4 Argon, Claude 5.5, GPT-5.2)으로 치환하십시오."
                    )
                else:
                    report["model_scan_status"] = "pass"
                    report["details"].append("구형 모델명 기계 검사 PASS (0개 확인)")
            except Exception as e:
                overall_success = False
                report["model_scan_status"] = "error"
                report["details"].append(f"구형 모델명 검사 중 예외 발생: {str(e)}")
        else:
            report["model_scan_status"] = "unavailable"
            report["details"].append("model_sanitizer 모듈을 찾을 수 없어 구형 모델명 검사를 건너뛰었습니다.")
            if strict:
                overall_success = False
    elif is_self_tool:
        report["model_scan_status"] = "skipped"
        report["details"].append("자체 도구/테스트 파일은 구형 모델명 검사에서 명시적으로 제외되었습니다.")

    return {"success": overall_success, "report": report}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synapse Harness 결정론적 기계 검증 엔진")
    parser.add_argument("target", help="검증할 대상 파일 경로")
    parser.add_argument("--test", action="store_true", help="명시적 옵션: 대응하는 단위 테스트(test_*.py)를 탐색하여 안전하게 실행합니다. (파이썬 전용)")
    parser.add_argument("--smoke", action="store_true", help="명시적 옵션: 격리된 서브프로세스에서 모듈 임포트를 시험하여 초기화 크래시를 검증합니다. (파이썬 전용)")
    parser.add_argument("--strict", action="store_true", help="엄격 모드: ruff, mypy 등 외부 분석 도구 미설치 시 실패로 처리합니다.")
    args = parser.parse_args()

    result = verify_file(args.target, run_tests=args.test, smoke=args.smoke, strict=args.strict)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if not result.get("success"):
        sys.exit(1)
    sys.exit(0)
