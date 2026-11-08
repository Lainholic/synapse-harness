"""
model_sanitizer.py - 구형 LLM 모델명(2024년 레거시 모델) 기계적 린터 및 자동 치환기
과거 구형 모델명(Gemini 1.5, GPT-4o, Claude 3.5 등)의 관성적 날조를 기계적으로 차단하고 최신 세대 모델명으로 정규화합니다.
"""

import os
import sys
import re
import argparse
import tempfile

# __pycache__ 잔여 생성을 원천 차단
sys.dont_write_bytecode = True

# 디렉터리 순회 시 제외할 디렉터리 및 파일 목록
IGNORED_DIRS = {
    ".git", ".svn", ".hg",
    ".venv", "venv", "env",
    "node_modules",
    "__pycache__",
    ".idea", ".vscode",
    "dist", "build", "target"
}

IGNORED_FILES = {
    "model_sanitizer.py",
    "verify.py"
}

# (구형 패턴 정규식, 최신 세대 치환 문자열)
MODEL_REPLACEMENTS = [
    # Gemini 계열
    (re.compile(r"\bGemini[\s\-_]*1\.5[\s\-_]*Pro\b", re.IGNORECASE), "Gemini 3.8 Flash"),
    (re.compile(r"\bgemini[\s\-_]*1\.5[\s\-_]*pro\b", re.IGNORECASE), "gemini-3.8-flash"),
    (re.compile(r"\bGemini[\s\-_]*1\.5[\s\-_]*Flash\b", re.IGNORECASE), "Gemini 3.8 Flash"),
    (re.compile(r"\bgemini[\s\-_]*1\.5[\s\-_]*flash\b", re.IGNORECASE), "gemini-3.8-flash"),
    (re.compile(r"\bGemini[\s\-_]*1\.5\b", re.IGNORECASE), "Gemini 3.8"),
    (re.compile(r"\bgemini[\s\-_]*1\.5\b", re.IGNORECASE), "gemini-3.8"),

    # Claude 계열
    (re.compile(r"\bClaude[\s\-_]*3\.5[\s\-_]*Sonnet\b", re.IGNORECASE), "Claude 5.5 Sonnet"),
    (re.compile(r"\bclaude[\s\-_]*3[\-_]5[\-_]sonnet\b", re.IGNORECASE), "claude-5-5-sonnet"),
    (re.compile(r"\bClaude[\s\-_]*3\.5[\s\-_]*Haiku\b", re.IGNORECASE), "Claude 5.5 Haiku"),
    (re.compile(r"\bClaude[\s\-_]*3\.5\b", re.IGNORECASE), "Claude 5.5"),
    (re.compile(r"\bclaude[\s\-_]*3[\-_]5\b", re.IGNORECASE), "claude-5-5"),
    (re.compile(r"\bClaude[\s\-_]*3\b", re.IGNORECASE), "Claude 5.5"),

    # OpenAI GPT 계열
    (re.compile(r"\bGPT[\s\-_]*4o[\s\-_]*mini\b", re.IGNORECASE), "GPT-5.2-mini"),
    (re.compile(r"\bGPT[\s\-_]*4o\b", re.IGNORECASE), "GPT-5.2"),
    (re.compile(r"\bgpt[\s\-_]*4o\b", re.IGNORECASE), "gpt-5.2"),
    (re.compile(r"\bGPT[\s\-_]*4\.5\b", re.IGNORECASE), "GPT-5.2"),
    (re.compile(r"\bGPT[\s\-_]*4\b(?!\w)", re.IGNORECASE), "GPT-5"),

    # Llama 계열
    (re.compile(r"\bLlama[\s\-_]*3\.1\b", re.IGNORECASE), "Llama 4"),
    (re.compile(r"\bllama[\s\-_]*3\.1\b", re.IGNORECASE), "llama-4"),
    (re.compile(r"\bLlama[\s\-_]*3\b(?!\w)", re.IGNORECASE), "Llama 4"),
]

def scan_text(text):
    """텍스트에서 구형 모델명 출현을 탐지하여 목록을 반환합니다."""
    findings = []
    seen = set()
    for pattern, target in MODEL_REPLACEMENTS:
        matches = pattern.findall(text)
        for m in matches:
            if m.lower() not in seen:
                seen.add(m.lower())
                findings.append({"found": m, "suggested": target})
    return findings

def sanitize_text(text):
    """텍스트 내 구형 모델명을 최신 규격으로 자동 치환합니다."""
    sanitized = text
    replaced_count = 0
    for pattern, target in MODEL_REPLACEMENTS:
        new_text, count = pattern.subn(target, sanitized)
        if count > 0:
            sanitized = new_text
            replaced_count += count
    return sanitized, replaced_count

def process_file(file_path, fix=False):
    if not os.path.isfile(file_path):
        return {"file": file_path, "success": False, "error": "파일을 찾을 수 없습니다."}
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return {"file": file_path, "success": False, "error": f"파일 읽기 오류: {e}"}

    findings = scan_text(content)

    if not findings:
        return {"file": file_path, "success": True, "legacy_models_found": 0, "findings": []}

    if fix:
        sanitized_content, count = sanitize_text(content)
        try:
            # 원본 손상 방지를 위한 원자적 임시 저장 및 교체 (atomic replace)
            file_dir = os.path.dirname(os.path.abspath(file_path))
            with tempfile.NamedTemporaryFile("w", dir=file_dir, delete=False, encoding="utf-8") as tf:
                tf.write(sanitized_content)
                temp_name = tf.name
            os.replace(temp_name, file_path)
            return {
                "file": file_path,
                "success": True,
                "legacy_models_found": len(findings),
                "replaced_count": count,
                "status": "FIXED_AUTO",
                "findings": findings
            }
        except Exception as e:
            return {"file": file_path, "success": False, "error": f"파일 안전 저장 오류: {e}"}
    else:
        return {
            "file": file_path,
            "success": False,
            "legacy_models_found": len(findings),
            "status": "LEGACY_MODEL_DETECTED",
            "findings": findings
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 구형 모델명 린터 및 치환기")
    parser.add_argument("target", help="검사할 파일 또는 디렉터리 경로")
    parser.add_argument("--fix", action="store_true", help="감지된 구형 모델명을 최신 규격으로 자동 치환합니다.")
    args = parser.parse_args()

    target_path = os.path.abspath(args.target)
    if os.path.isfile(target_path):
        res = process_file(target_path, fix=args.fix)
        print(f"[{'PASS' if res['success'] else 'FAIL'}] {target_path}")
        if not res["success"] or res.get("status") == "FIXED_AUTO":
            print(f"  Findings: {res.get('findings')}")
        sys.exit(0 if res["success"] else 1)
    elif os.path.isdir(target_path):
        failed_count = 0
        fixed_count = 0
        for root, dirs, files in os.walk(target_path):
            # .git, .venv 등 제외 디렉터리 필터링
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            for file in files:
                if file.lower() in IGNORED_FILES:
                    continue
                if file.endswith((".py", ".md", ".txt", ".json", ".js", ".ts", ".html")):
                    fpath = os.path.join(root, file)
                    res = process_file(fpath, fix=args.fix)
                    if not res["success"]:
                        failed_count += 1
                        print(f"[FAIL] {fpath}: {res.get('findings')}")
                    elif res.get("status") == "FIXED_AUTO":
                        fixed_count += 1
                        print(f"[FIXED] {fpath}: {res.get('findings')}")
        print(f"검사 완료. 결함: {failed_count}건, 자동 치환: {fixed_count}건")
        sys.exit(1 if failed_count > 0 else 0)
    else:
        print(f"유효하지 않은 경로: {target_path}")
        sys.exit(1)
