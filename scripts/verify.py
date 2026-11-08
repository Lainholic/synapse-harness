import os
import sys
import json
import tempfile
import py_compile
import subprocess
import argparse

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

def run_unit_test(test_file):
    """동일한 Python 인터프리터의 pytest 또는 unittest로 테스트 파일을 격리 실행합니다."""
    test_dir = os.path.dirname(os.path.abspath(test_file))
    test_name = os.path.basename(test_file)
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{test_dir}{os.pathsep}{existing_pythonpath}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # 1. pytest 가용 여부 사전 검사
    has_pytest = False
    try:
        import importlib.util
        has_pytest = importlib.util.find_spec("pytest") is not None
    except Exception:
        has_pytest = False

    if has_pytest:
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", test_name],
                cwd=test_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=15
            )
            out = (res.stdout.strip() + "\n" + res.stderr.strip()).strip()
            return {
                "runner": "pytest",
                "pass": res.returncode == 0,
                "output": out,
                "returncode": res.returncode
            }
        except subprocess.TimeoutExpired:
            return {"runner": "pytest", "pass": False, "output": "pytest 실행 시간 초과 (15초)", "returncode": -1}
        except Exception as e:
            return {"runner": "pytest", "pass": False, "output": f"pytest 실행 실패: {e}", "returncode": -1}

    # 2. pytest 미설치 시 파이썬 내장 unittest로 실행
    try:
        res = subprocess.run(
            [sys.executable, "-m", "unittest", test_name],
            cwd=test_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=15
        )
        out = (res.stdout.strip() + "\n" + res.stderr.strip()).strip()
        # Ran 0 tests 방어: 실제 테스트가 0개 실행된 경우 성공으로 오인하지 않음
        if "Ran 0 tests" in out:
            return {
                "runner": "unittest",
                "pass": False,
                "output": f"실행된 테스트 케이스가 0개입니다:\n{out}",
                "returncode": -1
            }
        return {
            "runner": "unittest",
            "pass": res.returncode == 0,
            "output": out,
            "returncode": res.returncode
        }
    except subprocess.TimeoutExpired:
        return {"runner": "unittest", "pass": False, "output": "unittest 실행 시간 초과 (15초)", "returncode": -1}
    except Exception as e:
        return {"runner": "unittest", "pass": False, "output": f"unittest 실행 실패: {e}", "returncode": -1}

def run_smoke_import(file_path):
    """모듈을 서브프로세스에서 안전하게 임포트하여 즉각적인 초기화 런타임 크래시를 검증합니다."""
    # 경로를 문자열에 직접 삽입하지 않고 sys.argv[1]로 안전하게 전달
    code = (
        "import sys, importlib.util;"
        "sys.dont_write_bytecode = True;"
        "target = sys.argv[1];"
        "spec = importlib.util.spec_from_file_location('__harness_smoke__', target);"
        "mod = importlib.util.module_from_spec(spec);"
        "spec.loader.exec_module(mod);"
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

def verify_file(file_path, run_tests=False, smoke=False):
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
        "linter_details": "",
        "details": []
    }
    
    overall_success = True

    # 1. 파이썬 문법, 린터, 타입, 옵션별 런타임 검사
    if ext == ".py":
        report["encoding_pass"] = True
        # __pycache__ 잔여 방지를 위해 임시 디렉터리에서 컴파일 수행
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_cfile = os.path.join(tmp_dir, "temp_check.pyc")
            try:
                py_compile.compile(file_path, cfile=temp_cfile, doraise=True)
                report["syntax_pass"] = True
                report["details"].append("py_compile 구문 검사 PASS (오염 없는 격리 컴파일)")
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
                report["details"].append("ruff 정적 린터 PASS (코드 무결)")
            else:
                report["linter_status"] = "failed"
                overall_success = False
                err_output = (res.stdout.strip() + "\n" + res.stderr.strip()).strip()
                report["linter_details"] = err_output
                report["details"].append(f"ruff 지적 사항 (ExitCode {res.returncode}):\n{err_output}")
        except FileNotFoundError:
            report["linter_status"] = "not_installed"
            report["details"].append("ruff 미설치 (내장 py_compile 검사로 갈음)")
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
                report["details"].append("스모크 임포트 실행 검증 PASS (런타임 초기화 크래시 없음)")
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
                test_res = run_unit_test(target_test)
                if test_res["pass"]:
                    report["test_status"] = "pass"
                    report["details"].append(f"단위 테스트 실행 PASS ({test_res['runner']}: {os.path.basename(target_test)})")
                else:
                    report["test_status"] = "failed"
                    overall_success = False
                    report["details"].append(f"[단위 테스트 FAIL] ({test_res['runner']}):\n{test_res['output']}")
            else:
                report["test_status"] = "not_found"
                report["details"].append("대응하는 단위 테스트 파일(test_*.py)을 찾지 못했습니다.")

    # 2. JSON 파싱 검사 (문법 파싱)
    elif ext == ".json":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
            report["encoding_pass"] = True
            report["syntax_pass"] = True
            report["linter_status"] = "pass"
            report["details"].append("JSON 구문 파싱 PASS")
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

    # 3. 기타 텍스트/마크다운 파일 (LICENSE 등 확장자 없는 일반 텍스트 포함)
    elif ext in ("", ".md", ".txt", ".cs", ".html", ".css", ".js", ".ts") or os.path.basename(file_path).lower() in ("license", "dockerfile", "makefile"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.read()
            report["encoding_pass"] = True
            report["syntax_pass"] = True
            report["linter_status"] = "unsupported"
            report["details"].append("UTF-8 텍스트 인코딩 및 읽기 무결성 PASS")
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

    # 4. 공통 구형 모델명 기계적 린터 검사 (검사기 자체의 도구 파일은 제외)
    canon_target = os.path.realpath(file_path)
    is_self_tool = (
        canon_target == os.path.realpath(__file__) or
        canon_target == os.path.realpath(os.path.join(script_dir, "model_sanitizer.py")) or
        canon_target == os.path.realpath(os.path.join(script_dir, "..", "SKILL.md")) or
        os.path.basename(canon_target).startswith("test_")
    )
    
    if scan_text and not is_self_tool and ext in (".py", ".md", ".txt", ".cs", ".html", ".css", ".js", ".ts", ".json"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content_to_check = f.read()
            legacy_findings = scan_text(content_to_check)
            if legacy_findings:
                overall_success = False
                report["linter_status"] = "failed"
                report["details"].append(
                    f"[구형 모델명 감지 FAIL] 레거시 모델명이 감지되었습니다: {legacy_findings}. "
                    f"python scripts/model_sanitizer.py --fix \"{file_path}\" 로 최신 규격(Gemini 3.8/4 Argon, Claude 5.5, GPT-5.2)으로 치환하십시오."
                )
            else:
                report["details"].append("구형 모델명 기계 검사 PASS (0개 확인)")
        except Exception as e:
            overall_success = False
            report["linter_status"] = "error"
            report["details"].append(f"구형 모델명 검사 중 예외 발생: {str(e)}")

    return {"success": overall_success, "report": report}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synapse Harness 결정론적 기계 검증 엔진")
    parser.add_argument("target", help="검증할 대상 파일 경로")
    parser.add_argument("--test", action="store_true", help="명시적 옵션: 대응하는 단위 테스트(test_*.py)를 탐색하여 안전하게 실행합니다.")
    parser.add_argument("--smoke", action="store_true", help="명시적 옵션: 격리된 서브프로세스에서 모듈 임포트를 시험하여 초기화 크래시를 검증합니다.")
    args = parser.parse_args()

    result = verify_file(args.target, run_tests=args.test, smoke=args.smoke)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if not result.get("success"):
        sys.exit(1)
    sys.exit(0)
