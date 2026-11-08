import os
import sys
import json
import tempfile
import py_compile
import subprocess

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

def verify_file(file_path):
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
        "linter_details": "",
        "details": []
    }
    
    overall_success = True

    # 1. 파이썬 문법 및 린터 검사
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
                overall_success = False  # 린터 실패 시 전체 성공도 False로 전파
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

    # 2. JSON 파싱 검사
    elif ext == ".json":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
            report["encoding_pass"] = True
            report["syntax_pass"] = True
            report["linter_status"] = "pass"
            report["details"].append("JSON 파싱 및 구문 검사 PASS")
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
        canon_target == os.path.realpath(os.path.join(script_dir, "..", "SKILL.md"))
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
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "파일 경로를 입력해주세요."}, ensure_ascii=False))
        sys.exit(1)
        
    target = sys.argv[1]
    result = verify_file(target)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 린터나 구문 검사가 실패하면 명확하게 프로세스 종료 코드 1 반환
    if not result.get("success"):
        sys.exit(1)
    sys.exit(0)
