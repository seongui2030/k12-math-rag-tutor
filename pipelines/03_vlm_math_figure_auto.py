from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


QUOTA_ERROR_MARKERS = (
    "429 RESOURCE_EXHAUSTED",
    "Generate content requests per day limit exceeded",
    "Quota exceeded for metric",
)


def resolve_project_root() -> Path:
    if "__file__" in globals():
        return Path(__file__).resolve().parents[1]
    cwd = Path.cwd()
    return cwd.parent if cwd.name == "pipelines" else cwd


def load_env_files(project_root: Path) -> None:
    env_candidates = [
        project_root / ".env",
        Path("/content/drive/MyDrive/k12_math_rag_data/.env"),
    ]
    for env_path in env_candidates:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)


def discover_exam_ids(raw_dir: Path) -> list[str]:
    if not raw_dir.exists():
        return []
    exam_ids: list[str] = []
    for problem_pdf in sorted(raw_dir.glob("*_problem.pdf")):
        exam_id = problem_pdf.name.removesuffix("_problem.pdf")
        solution_pdf = raw_dir / f"{exam_id}_solution.pdf"
        if solution_pdf.exists():
            exam_ids.append(exam_id)
    return exam_ids


def inspect_merged_status(merged_path: Path) -> dict[str, Any]:
    if not merged_path.exists():
        return {
            "merged_exists": False,
            "is_complete": False,
            "total_questions": 0,
            "parsed_problem_count": 0,
            "parsed_solution_count": 0,
            "parsed_answer_table_count": 0,
            "missing_solution_nos": [],
        }

    try:
        data = json.loads(merged_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "merged_exists": True,
            "is_complete": False,
            "json_error": str(exc),
            "total_questions": 0,
            "parsed_problem_count": 0,
            "parsed_solution_count": 0,
            "parsed_answer_table_count": 0,
            "missing_solution_nos": [],
        }

    total_q = int(data.get("total_questions") or 30)
    prob_cnt = int(data.get("parsed_problem_count") or 0)
    sol_cnt = int(data.get("parsed_solution_count") or 0)
    ans_cnt = int(data.get("parsed_answer_table_count") or 0)

    questions = data.get("questions") or {}
    missing_solution_nos: list[int] = []
    for q_no in range(1, total_q + 1):
        q_obj = questions.get(str(q_no)) or questions.get(q_no) or {}
        if not (q_obj.get("solution") or "").strip():
            missing_solution_nos.append(q_no)

    is_complete = (
        prob_cnt >= total_q
        and sol_cnt >= total_q
        and ans_cnt >= total_q
        and len(missing_solution_nos) == 0
    )

    return {
        "merged_exists": True,
        "is_complete": is_complete,
        "total_questions": total_q,
        "parsed_problem_count": prob_cnt,
        "parsed_solution_count": sol_cnt,
        "parsed_answer_table_count": ans_cnt,
        "missing_solution_nos": missing_solution_nos,
    }


def is_quota_exhausted(text: str) -> bool:
    return any(marker in text for marker in QUOTA_ERROR_MARKERS)


def build_base_runner_command(
    project_root: Path,
    exam_id: str,
    model_name: str,
    retry_backoff_sec: float,
    max_retries: int,
) -> list[str]:
    """
    기존 pipelines/03_vlm_math_figure.py 를 수정하지 않고 서브프로세스로 호출합니다.
    03_vlm_math_figure.py 가 --exam-id 옵션을 지원하지 않는 경우를 대비해
    실행 직전 raw_dir 을 임시 격리 디렉터리로 구성해 해당 세트만 실행하도록 보장합니다.
    """
    inline_runner = f"""
import importlib, os, sys, time, shutil
from pathlib import Path

project_root = Path({str(project_root)!r})
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

base_mod = importlib.import_module("pipelines.03_vlm_math_figure")  
# import pipelines.03_vlm_math_figure as base_mod

# 모델명 상수/기본값이 있으면 반영
for attr in ("DEFAULT_GEMINI_MODEL", "GEMINI_MODEL", "MODEL_NAME"):
    if hasattr(base_mod, attr):
        setattr(base_mod, attr, {model_name!r})

# 단일 exam_id 만 보이도록 임시 raw 폴더 구성 (기존 raw PDF 는 원본 유지)
orig_raw_dir = project_root / "data/raw/ebsi/h1"
stage_raw_dir = Path("/content/k12_auto_stage_raw/ebsi/h1")
if stage_raw_dir.exists():
    shutil.rmtree(stage_raw_dir.parent)
stage_raw_dir.mkdir(parents=True, exist_ok=True)

for suffix in ("_problem.pdf", "_solution.pdf", "_answer.pdf"):
    src = orig_raw_dir / f"{exam_id}{{suffix}}"
    if src.exists():
        os.symlink(src, stage_raw_dir / src.name)

# base_mod 내부 경로 상수 오버라이드 시도
for attr in ("RAW_DIR", "DATA_RAW_DIR", "EBSI_H1_DIR"):
    if hasattr(base_mod, attr):
        setattr(base_mod, attr, stage_raw_dir)

# API 호출 함수 래핑 (429 일시 오류 재시도 + 일일 쿼터 초과 즉시 전파)
orig_call = None
for fn_name in ("call_gemini_vlm", "extract_page_with_gemini", "gemini_extract"):
    if hasattr(base_mod, fn_name) and callable(getattr(base_mod, fn_name)):
        orig_call = getattr(base_mod, fn_name)

        def wrapped_call(*args, **kwargs):
            last_exc = None
            for attempt in range({max_retries} + 1):
                try:
                    return orig_call(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc)
                    if "Generate content requests per day limit exceeded" in msg:
                        raise
                    if "429" in msg and attempt < {max_retries}:
                        wait_sec = {retry_backoff_sec} * (2 ** attempt)
                        print(f"[재시도 {{attempt + 1}}/{max_retries}] 429 감지 -> {{wait_sec:.1f}}초 대기")
                        time.sleep(wait_sec)
                        continue
                    raise
            raise last_exc

        setattr(base_mod, fn_name, wrapped_call)
        break

import importlib
import runpy

sys.argv = ["03_vlm_math_figure.py"]
base_mod = importlib.import_module("pipelines.03_vlm_math_figure")

if hasattr(base_mod, "main") and callable(base_mod.main):
    base_mod.main()
else:
    # 03_vlm_math_figure.py 에 main() 이 없는 경우 모듈 파일을 __main__ 으로 실행
    runpy.run_path(str(project_root / "pipelines/03_vlm_math_figure.py"), run_name="__main__")
"""
    return [sys.executable, "-c", inline_runner]


def run_single_exam_isolated(
    project_root: Path,
    exam_id: str,
    model_name: str,
    retry_backoff_sec: float,
    max_retries: int,
) -> tuple[bool, str]:
    cmd = build_base_runner_command(
        project_root=project_root,
        exam_id=exam_id,
        model_name=model_name,
        retry_backoff_sec=retry_backoff_sec,
        max_retries=max_retries,
    )
    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True)
    combined_output = f"{proc.stdout}\n{proc.stderr}"

    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())

    if proc.returncode == 0 and not is_quota_exhausted(combined_output):
        return True, ""

    error_detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
    return False, error_detail


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="수학 시험지 세트 일괄 자동 파싱 러너 (03_vlm_math_figure.py 무수정 확장)"
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help="원본 PDF 폴더 경로 (기본값: <project_root>/data/raw/ebsi/h1)",
    )
    parser.add_argument(
        "--structured-dir",
        type=Path,
        default=Path("/content/drive/MyDrive/k12_math_rag_data/structured_exams"),
        help="통합 JSON 저장 폴더 경로",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("/content/drive/MyDrive/k12_math_rag_data/batch_auto_report.json"),
        help="배치 실행 요약 리포트 저장 경로",
    )
    parser.add_argument(
        "--exam-ids",
        nargs="*",
        default=None,
        help="특정 exam_id 목록만 실행 (예: --exam-ids 2026_10_hs1)",
    )
    parser.add_argument("--start", type=int, default=0, help="시작 인덱스 (0부터 시작)")
    parser.add_argument("--limit", type=int, default=None, help="이번 실행에서 처리할 최대 세트 수")
    parser.add_argument(
        "--retry-incomplete",
        action="store_true",
        help="이미 완료된 세트는 건너뛰고 미완료/누락 문항이 있는 세트만 실행",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-3.8-flash",
        help="사용할 Gemini 모델명 (기본값: gemini-3.8-flash)",
    )
    parser.add_argument(
        "--sleep-sec",
        type=float,
        default=1.5,
        help="세트 간 대기 시간(초)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="일시적 429 오류 발생 시 페이지당 최대 재시도 횟수",
    )
    parser.add_argument(
        "--retry-backoff-sec",
        type=float,
        default=5.0,
        help="재시도 초기 대기 시간(초, 지수 백오프 적용)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = resolve_project_root()
    load_env_files(project_root)

    if not os.environ.get("GEMINI_API_KEY"):
        print("[오류] GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    raw_dir = args.raw_dir or (project_root / "data/raw/ebsi/h1")
    all_exam_ids = discover_exam_ids(raw_dir)
    if not all_exam_ids:
        print(f"[경고] 탐색된 시험지 세트가 없습니다: {raw_dir}")
        return

    if args.exam_ids:
        selected = [eid for eid in args.exam_ids if eid in all_exam_ids]
        skipped_ids = [eid for eid in args.exam_ids if eid not in all_exam_ids]
        if skipped_ids:
            print(f"[알림] 문제지/해설지 쌍이 없는 exam_id 제외됨: {skipped_ids}")
    else:
        end_idx = args.start + args.limit if args.limit is not None else len(all_exam_ids)
        selected = all_exam_ids[args.start : end_idx]

    if args.retry_incomplete:
        incomplete_list: list[str] = []
        for eid in selected:
            info = inspect_merged_status(args.structured_dir / eid / f"{eid}_merged.json")
            if not info["is_complete"]:
                incomplete_list.append(eid)
        print(f"[필터 적용] 선택 {len(selected)}개 중 미완료 세트 {len(incomplete_list)}개 실행")
        selected = incomplete_list

    print(f"전체 탐색 세트: {len(all_exam_ids)}개 | 이번 실행 대상: {len(selected)}개")
    if not selected:
        print("[완료] 실행할 대상 세트가 없습니다.")
        return

    report_records: list[dict[str, Any]] = []
    if args.report_path.exists():
        try:
            loaded = json.loads(args.report_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                report_records = loaded
        except Exception:
            report_records = []

    quota_stopped = False

    for idx, exam_id in enumerate(selected, start=1):
        print(f"\n==================== [{idx}/{len(selected)}] {exam_id} ====================")
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.time()

        ok, err_text = run_single_exam_isolated(
            project_root=project_root,
            exam_id=exam_id,
            model_name=args.model,
            retry_backoff_sec=args.retry_backoff_sec,
            max_retries=args.max_retries,
        )

        merged_path = args.structured_dir / exam_id / f"{exam_id}_merged.json"
        merged_info = inspect_merged_status(merged_path)

        if ok and merged_info["is_complete"]:
            status = "ok"
        elif ok:
            status = "partial"
        elif is_quota_exhausted(err_text):
            status = "quota_exceeded"
            quota_stopped = True
        else:
            status = "error"

        record = {
            "exam_id": exam_id,
            "status": status,
            "started_at": started_at,
            "elapsed_sec": round(time.time() - t0, 1),
            "error": err_text[:500] if err_text else "",
            **merged_info,
        }
        report_records.append(record)

        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(
            json.dumps(report_records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(
            f"[요약] {exam_id} -> status={status} | "
            f"문제 {merged_info['parsed_problem_count']}/{merged_info['total_questions']} | "
            f"해설 {merged_info['parsed_solution_count']}/{merged_info['total_questions']} | "
            f"정답표 {merged_info['parsed_answer_table_count']}/{merged_info['total_questions']}"
        )

        if quota_stopped:
            print(
                "[중단] 일일 API 할당량(429 RESOURCE_EXHAUSTED)에 도달해 안전 종료했습니다. "
                "할당량 초기화 또는 결제/키 전환 후 --retry-incomplete 옵션으로 이어서 실행하세요."
            )
            break

        if idx < len(selected) and args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    print(f"\n[완료] 자동화 리포트 저장됨: {args.report_path}")


if __name__ == "__main__":
    main()