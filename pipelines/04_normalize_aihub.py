from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.colab_env import get_project_root, get_storage_dirs
except Exception:
    def get_project_root() -> Path:
        return PROJECT_ROOT

    def get_storage_dirs(root: Path | None = None) -> dict[str, Path]:
        base = Path("/content/drive/MyDrive/k12_math_rag_data")
        return {
            "root": base,
            "structured": base / "structured_exams",
            "normalized": base / "normalized_exams",
        }


DEFAULT_DRIVE_ROOT = Path("/content/drive/MyDrive/k12_math_rag_data")


def clean_text(text: Any) -> str:
    if text is None:
        return ""
    s = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def split_problem_vlm_pages(vlm_json: dict[str, Any], exam_id: str) -> dict[int, dict[str, Any]]:
    """
    2026_10_hs1_problem_vlm.json 의 pages[*].vlm_text 에서 문항별 본문/선택지/도형 묘사를 분리합니다.
    """
    extracted: dict[int, dict[str, Any]] = {}
    pages = vlm_json.get("pages") or {}

    q_header_pattern = re.compile(r"(?:^|\n)#{2,4}\s*\[?문제\s*(\d{1,2})\]?|(?:^|\n)#{2,4}\s*(\d{1,2})\.\s+", re.MULTILINE)

    for page_key, page_obj in sorted(pages.items(), key=lambda x: int(str(x[0])) if str(x[0]).isdigit() else 0):
        if not isinstance(page_obj, dict):
            continue
        if page_obj.get("status") not in (None, "ok"):
            continue
        vlm_text = clean_text(page_obj.get("vlm_text"))
        if not vlm_text:
            continue

        matches = list(q_header_pattern.finditer(vlm_text))
        for idx, match in enumerate(matches):
            q_no_str = match.group(1) or match.group(2)
            if not q_no_str or not q_no_str.isdigit():
                continue
            q_no = int(q_no_str)
            start_pos = match.start()
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(vlm_text)
            block = vlm_text[start_pos:end_pos].strip()

            fig_match = re.search(r"(?:도형(?:/그래프)?\s*상세\s*묘사|도형\s*묘사)\s*[:：]?\s*(.+)", block, re.DOTALL)
            figure_desc = clean_text(fig_match.group(1)) if fig_match else "없음"
            if not figure_desc:
                figure_desc = "없음"

            choices: list[str] = []
            for line in block.splitlines():
                line_s = line.strip()
                if re.match(r"^(?:\\item|[①②③④⑤]|\([1-5]\)|[1-5]\))\s*", line_s):
                    cleaned_choice = re.sub(r"^\\item\s*", "", line_s).strip()
                    if cleaned_choice:
                        choices.append(cleaned_choice)

            existing = extracted.get(q_no, {})
            extracted[q_no] = {
                "exam_id": exam_id,
                "question_no": q_no,
                "page": int(page_obj.get("page") or (int(page_key) if str(page_key).isdigit() else 0)),
                "question_text": existing.get("question_text") or block,
                "choices": existing.get("choices") or choices,
                "figure_description": figure_desc if figure_desc != "없음" else existing.get("figure_description", "없음"),
                "source_type": "problem_vlm_json",
            }

    return extracted


def split_solution_vlm_pages(vlm_json: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """
    2026_10_hs1_solution_vlm.json 의 pages[*].vlm_text 에서 문항별 해설/출제의도를 분리합니다.
    """
    extracted: dict[int, dict[str, Any]] = {}
    pages = vlm_json.get("pages") or {}
    q_pattern = re.compile(r"(?:^|\n)#{2,4}\s*\[?문제\s*(\d{1,2})\]?|(?:^|\n)#{2,4}\s*(\d{1,2})\.\s+", re.MULTILINE)

    for _, page_obj in sorted(pages.items(), key=lambda x: int(str(x[0])) if str(x[0]).isdigit() else 0):
        if not isinstance(page_obj, dict):
            continue
        if page_obj.get("status") not in (None, "ok"):
            continue
        vlm_text = clean_text(page_obj.get("vlm_text"))
        if not vlm_text:
            continue

        matches = list(q_pattern.finditer(vlm_text))
        for idx, match in enumerate(matches):
            q_no_str = match.group(1) or match.group(2)
            if not q_no_str or not q_no_str.isdigit():
                continue
            q_no = int(q_no_str)
            start_pos = match.start()
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(vlm_text)
            block = vlm_text[start_pos:end_pos].strip()

            intent_match = re.search(r"출제의도\s*[:：]?\s*(.+?)(?:\n#{2,4}|\n\*\*|$)", block, re.DOTALL)
            intent_text = clean_text(intent_match.group(1)) if intent_match else ""

            extracted[q_no] = {
                "intent": intent_text,
                "solution": block,
                "source_type": "solution_vlm_json",
            }

    return extracted


def parse_solution_parsed_test(parsed_obj: Any) -> dict[int, dict[str, Any]]:
    """
    solution_paserd_test.json (또는 solution_parsed_test.json) 에서 문항별 정답/해설 정보를 추출합니다.
    """
    result: dict[int, dict[str, Any]] = {}
    if parsed_obj is None:
        return result

    items: list[tuple[int, dict[str, Any]]] = []
    if isinstance(parsed_obj, dict):
        q_map = parsed_obj.get("questions") if isinstance(parsed_obj.get("questions"), dict) else parsed_obj
        for k, v in q_map.items():
            if isinstance(v, dict) and str(k).isdigit():
                items.append((int(k), v))
    elif isinstance(parsed_obj, list):
        for idx, v in enumerate(parsed_obj, start=1):
            if isinstance(v, dict):
                q_no = v.get("question_no") or v.get("no") or idx
                if str(q_no).isdigit():
                    items.append((int(q_no), v))

    for q_no, entry in items:
        ans = clean_text(entry.get("answer") or entry.get("correct_answer") or "")
        sol = clean_text(entry.get("solution") or entry.get("explanation") or entry.get("vlm_text") or "")
        intent = clean_text(entry.get("intent") or entry.get("purpose") or "")
        result[q_no] = {
            "answer": ans,
            "solution": sol,
            "intent": intent,
            "source_type": "solution_parsed_test_json",
        }

    return result


def discover_exam_inputs(search_roots: list[Path], exam_id: str) -> dict[str, list[Path]]:
    """
    Google Drive 내 다양한 경로(vlm_parser, test2026_10_hs1, test_2026_10_hs1, structured_exams 등)에서
    대상 exam_id 관련 문제/해설/병합 JSON 파일들을 수집합니다.
    """
    found: dict[str, list[Path]] = {
        "problem_vlm": [],
        "solution_vlm": [],
        "solution_parsed": [],
        "merged": [],
    }

    seen: set[Path] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for p in root.rglob("*.json"):
            rp = p.resolve()
            if rp in seen:
                continue
            name_lower = p.name.lower()
            path_str = str(p).lower()
            if exam_id.lower() not in path_str and "2026_10_hs1" not in path_str:
                continue

            seen.add(rp)
            if f"{exam_id.lower()}_problem_vlm.json" in name_lower or "problem_vlm.json" in name_lower:
                found["problem_vlm"].append(p)
            elif f"{exam_id.lower()}_solution_vlm.json" in name_lower or "solution_vlm.json" in name_lower:
                found["solution_vlm"].append(p)
            elif "paserd" in name_lower or "parsed" in name_lower or "solution_paserd" in name_lower:
                found["solution_parsed"].append(p)
            elif f"{exam_id.lower()}_merged.json" in name_lower or name_lower.endswith("_merged.json"):
                found["merged"].append(p)

    return found


def normalize_exam_records(
    exam_id: str,
    search_roots: list[Path],
    total_questions: int = 30,
) -> dict[str, Any]:
    """
    발견된 VLM/파싱 JSON들을 문항(1~N) 단위 공통 정규화 스키마로 통합합니다.
    """
    inputs = discover_exam_inputs(search_roots=search_roots, exam_id=exam_id)

    problem_by_q: dict[int, dict[str, Any]] = {}
    solution_by_q: dict[int, dict[str, Any]] = {}
    parsed_sol_by_q: dict[int, dict[str, Any]] = {}
    merged_by_q: dict[int, dict[str, Any]] = {}

    for p in inputs["merged"]:
        try:
            m_data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(m_data.get("questions"), dict):
                for k, v in m_data["questions"].items():
                    if str(k).isdigit() and isinstance(v, dict):
                        merged_by_q[int(k)] = v
        except Exception:
            continue

    for p in inputs["problem_vlm"]:
        try:
            p_data = json.loads(p.read_text(encoding="utf-8"))
            problem_by_q.update(split_problem_vlm_pages(p_data, exam_id=exam_id))
        except Exception:
            continue

    for p in inputs["solution_vlm"]:
        try:
            s_data = json.loads(p.read_text(encoding="utf-8"))
            solution_by_q.update(split_solution_vlm_pages(s_data))
        except Exception:
            continue

    for p in inputs["solution_parsed"]:
        try:
            pt_data = json.loads(p.read_text(encoding="utf-8"))
            parsed_sol_by_q.update(parse_solution_parsed_test(pt_data))
        except Exception:
            continue

    all_q_nos = sorted(
        set(range(1, total_questions + 1))
        | set(problem_by_q.keys())
        | set(solution_by_q.keys())
        | set(parsed_sol_by_q.keys())
        | set(merged_by_q.keys())
    )

    normalized_items: list[dict[str, Any]] = []
    for q_no in all_q_nos:
        m_item = merged_by_q.get(q_no, {})
        p_item = problem_by_q.get(q_no, {})
        s_item = solution_by_q.get(q_no, {})
        pt_item = parsed_sol_by_q.get(q_no, {})

        question_text = clean_text(m_item.get("question_text")) or clean_text(p_item.get("question_text"))
        choices = m_item.get("choices") or p_item.get("choices") or []
        figure_desc = clean_text(m_item.get("figure_description")) or clean_text(p_item.get("figure_description")) or "없음"
        answer = clean_text(m_item.get("answer")) or clean_text(pt_item.get("answer"))
        intent = clean_text(m_item.get("intent")) or clean_text(s_item.get("intent")) or clean_text(pt_item.get("intent"))
        solution = clean_text(m_item.get("solution")) or clean_text(s_item.get("solution")) or clean_text(pt_item.get("solution"))

        sources_used = [
            src
            for src, present in [
                ("merged_json", bool(m_item)),
                ("problem_vlm_json", bool(p_item)),
                ("solution_vlm_json", bool(s_item)),
                ("solution_parsed_test_json", bool(pt_item)),
            ]
            if present
        ]

        normalized_items.append(
            {
                "id": f"{exam_id}_q{q_no:02d}",
                "exam_id": exam_id,
                "dataset_source": "ebsi_exam",
                "question_no": q_no,
                "score": m_item.get("score"),
                "question_text": question_text,
                "choices": choices,
                "figure_description": figure_desc,
                "answer": answer,
                "intent": intent,
                "solution": solution,
                "has_problem": bool(question_text),
                "has_solution": bool(solution),
                "has_answer": bool(answer),
                "sources_used": sources_used,
            }
        )

    return {
        "exam_id": exam_id,
        "dataset_source": "ebsi_exam",
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "total_items": len(normalized_items),
        "problem_count": sum(1 for x in normalized_items if x["has_problem"]),
        "solution_count": sum(1 for x in normalized_items if x["has_solution"]),
        "answer_count": sum(1 for x in normalized_items if x["has_answer"]),
        "discovered_files": {k: [str(x) for x in v] for k, v in inputs.items()},
        "items": normalized_items,
    }


def normalize_aihub_dataset(aihub_dir: Path | None = None) -> list[dict[str, Any]]:
    """
    기존 04_normalize_aihub.py 시그니처를 유지하면서 AI Hub 데이터셋 정규화 확장 포인트를 제공합니다.
    """
    if aihub_dir is None or not aihub_dir.exists():
        return []
    return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VLM/파싱 결과 정규화 파이프라인 (04_normalize_aihub.py)")
    parser.add_argument("--exam-id", type=str, default="2026_10_hs1", help="정규화할 시험지 ID")
    parser.add_argument("--total-questions", type=int, default=30, help="총 문항 수")
    parser.add_argument(
        "--drive-root",
        type=Path,
        default=DEFAULT_DRIVE_ROOT,
        help="Google Drive 루트 데이터 폴더",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="정규화 결과 저장 폴더 (기본값: <drive_root>/normalized_exams/<exam_id>)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = get_project_root()
    dirs = get_storage_dirs(root)

    search_roots = [
        args.drive_root,
        dirs.get("structured", args.drive_root / "structured_exams"),
        root / "data",
    ]

    result = normalize_exam_records(
        exam_id=args.exam_id,
        search_roots=search_roots,
        total_questions=args.total_questions,
    )

    out_dir = args.output_dir or (args.drive_root / "normalized_exams" / args.exam_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{args.exam_id}_normalized.json"
    jsonl_path = out_dir / f"{args.exam_id}_normalized.jsonl"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as f:
        for item in result["items"]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[정규화 완료] exam_id={args.exam_id}")
    print(
        f"총 문항: {result['total_items']} | "
        f"문제 보유: {result['problem_count']} | "
        f"해설 보유: {result['solution_count']} | "
        f"정답 보유: {result['answer_count']}"
    )
    print(f"저장 파일(JSON):  {json_path}")
    print(f"저장 파일(JSONL): {jsonl_path}")


if __name__ == "__main__":
    main()
