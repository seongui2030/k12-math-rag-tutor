import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트(.env) 자동 로드 (로컬 실행 시 적용, Colab에서는 환경변수 우선 유지)
_env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_env_path, override=False)

# ==============================================================================
# 3단계 파이프라인: 수학 문제지 & 해설지 VLM 구조화 파싱 및 1~30번 병합·정답 검증
# - 깨지는 PdfReader 텍스트 추출 제거 -> 페이지 PNG 렌더링 + VLM(Structured JSON)
# - 수식(LaTeX) 변환, 도형 묘사, 해설지 1p 정답표 & 풀이 최종답 교차 검증 일괄 처리
# - 28개 세트 대량 처리를 위한 Gemini API(Structured Outputs) 및 T4 경량 Qwen 지원
# ==============================================================================

import gc
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple


def configure_hf_cache_env() -> None:
    is_colab_env = (
        Path("/content").exists()
        and ("COLAB_RELEASE_TAG" in os.environ or "COLAB_GPU" in os.environ or Path("/content/drive").exists())
    )
    if is_colab_env:
        hf_base = Path("/content/hf_cache")
        hf_base.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(hf_base))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_base / "hub"))
    elif os.name == "nt" and Path("D:/").exists():
        hf_base = Path("D:/hf_cache")
        hf_base.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(hf_base))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_base / "hub"))

    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


configure_hf_cache_env()

from PIL import Image
from pydantic import BaseModel, Field
import pypdfium2 as pdfium


# ------------------------------------------------------------------------------
# 1. 출력 JSON 스키마 정의 (Pydantic - Gemini Structured Outputs & 검증 공용)
# ------------------------------------------------------------------------------
class ProblemItem(BaseModel):
    question_no: int = Field(description="문항 번호 (1~30)")
    score: Optional[int] = Field(default=None, description="배점 (2, 3, 4 중 하나, 표기 없으면 null)")
    question_text: str = Field(description="문항 본문 전체. 모든 수식은 표준 LaTeX($...$ 또는 $$...$$)로 표기")
    choices: List[str] = Field(default_factory=list, description="객관식 선택지 ①~⑤ 리스트 (단답형이면 빈 리스트)")
    figure_description: str = Field(default="없음", description="도형, 그래프, 표의 기하학적/수치적 상세 묘사 (없으면 '없음')")


class ProblemPageSchema(BaseModel):
    page: int = Field(description="페이지 번호")
    items: List[ProblemItem] = Field(default_factory=list, description="해당 페이지에 포함된 문항 리스트")


class AnswerTableEntry(BaseModel):
    question_no: int = Field(description="문항 번호 (1~30)")
    answer: str = Field(description="정답표에 기재된 정답 (객관식은 '1'~'5', 단답형은 숫자)")


class SolutionItem(BaseModel):
    question_no: int = Field(description="문항 번호 (1~30)")
    intent: str = Field(default="", description="[출제의도] 내용")
    solution_steps: str = Field(description="단계별 풀이 과정 전체. 모든 수식·분수·행렬·부등식은 표준 LaTeX($...$ 또는 $$...$$)로 표기")
    final_answer: str = Field(description="풀이 마지막 줄에 도출된 최종 정답 값 (예: '3', '11', '4')")


class SolutionPageSchema(BaseModel):
    page: int = Field(description="페이지 번호")
    answer_table: List[AnswerTableEntry] = Field(
        default_factory=list,
        description="페이지 상단에 전체 정답표가 있는 경우 1~30번 정답 목록 (없으면 빈 리스트)",
    )
    items: List[SolutionItem] = Field(default_factory=list, description="해당 페이지에 포함된 문항별 해설 리스트")


# ------------------------------------------------------------------------------
# 2. 프롬프트 생성기 (수식 LaTeX + 정답 매핑 통합)
# ------------------------------------------------------------------------------
def build_structured_prompt(doc_role: Literal["problem", "solution"], page_num: int) -> str:
    common_rules = (
        "당신은 대한민국 고등학교 수학 시험지 및 해설지 정밀 파싱 전문가입니다.\n"
        "이미지에서 시각적으로 보이는 내용만 정확히 읽어 지정된 JSON 형식으로 반환하세요.\n\n"
        "[수식 및 기호 변환 필수 규칙]\n"
        "1. 모든 수학 기호, 변수, 숫자식, 분수, 지수, 로그, 루트, 절댓값, 행렬, 연립방정식, 부등호, 그리스 문자는 "
        "깨짐 없이 반드시 표준 LaTeX($...$ 또는 $$...$$)로 작성하세요.\n"
        "   - 분수: $\\frac{a}{b}$, 제곱근: $\\sqrt{x}$, 부등호: $\\le$, $\\ge$, $\\neq$\n"
        "   - 행렬: $\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$, 연립방정식: $\\begin{cases} ... \\end{cases}$\n"
        "   - 조합/순열: ${}_n\\mathrm{C}_r$, ${}_n\\mathrm{P}_r$\n"
        "2. 페이지 상단 머리말('2026학년도 10월 고1 전국연합학력평가', '제2교시', '수학 영역' 등)과 하단 쪽수 번호는 제외하세요.\n"
        "3. 2단 편집 레이아웃인 경우 왼쪽 단 위에서 아래로 읽은 뒤 오른쪽 단 위에서 아래로 순서대로 추출하세요.\n"
    )

    if doc_role == "problem":
        role_rules = (
            f"\n[현재 문서: 문제지 ({page_num}페이지)]\n"
            "- 각 문항의 번호(question_no), 배점(score), 본문(question_text), 선택지(choices), 도형·그래프 묘사(figure_description)를 추출하세요.\n"
            "- 선택지 ①, ②, ③, ④, ⑤ 안의 수식도 모두 LaTeX로 변환하여 리스트에 순서대로 담으세요.\n"
            "- 도형이나 함수 그래프가 있으면 좌표축, 교점, 점의 이름, 길이·각도 조건을 빠짐없이 서술하세요."
        )
    else:
        role_rules = (
            f"\n[현재 문서: 해설지 ({page_num}페이지)]\n"
            "- 1페이지 상단에 '정답' 표(1~30번)가 있으면 표의 행과 열을 정확히 대조하여 answer_table에 1번부터 30번까지 빠짐없이 기록하세요. "
            "(객관식 원문자 ①,②,③,④,⑤는 각각 '1','2','3','4','5'로 변환)\n"
            "- 정답표가 없는 페이지라면 answer_table은 빈 리스트([])로 두세요.\n"
            "- 각 문항의 출제의도(intent), 단계별 풀이(solution_steps), 그리고 풀이 마지막에 도출된 최종 값(final_answer)을 추출하세요."
        )

    return common_rules + role_rules


# ------------------------------------------------------------------------------
# 3. PDF -> PNG 렌더링
# ------------------------------------------------------------------------------
def render_pdf_to_pngs(
    pdf_path: Path,
    img_root: Path,
    scale: float = 2.0,
    overwrite: bool = False,
) -> List[Path]:
    save_dir = img_root / pdf_path.stem
    save_dir.mkdir(parents=True, exist_ok=True)

    pdf_doc = pdfium.PdfDocument(str(pdf_path))
    rendered_paths: List[Path] = []
    try:
        for page_idx in range(len(pdf_doc)):
            out_png = save_dir / f"page_{page_idx + 1:02d}.png"
            if overwrite or not out_png.exists():
                page = pdf_doc[page_idx]
                bitmap = page.render(scale=scale)
                pil_img = bitmap.to_pil()
                pil_img.save(str(out_png), format="PNG")
            rendered_paths.append(out_png)
    finally:
        pdf_doc.close()

    return rendered_paths


# ------------------------------------------------------------------------------
# 4-A. 백엔드 1: Gemini API (Structured Outputs - 28개 세트 일괄 처리 추천)
# ------------------------------------------------------------------------------
def extract_page_with_gemini(
    image_path: Path,
    doc_role: Literal["problem", "solution"],
    page_num: int,
    model_name: str = "gemini-2.5-flash",
    max_retries: int = 3,
) -> Dict[str, Any]:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("환경변수 GEMINI_API_KEY가 설정되어 있지 않습니다.")

    client = genai.Client(api_key=api_key)
    schema_cls = ProblemPageSchema if doc_role == "problem" else SolutionPageSchema
    prompt_text = build_structured_prompt(doc_role, page_num)

    with Image.open(image_path) as img:
        pil_img = img.convert("RGB")

    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[pil_img, prompt_text],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema_cls,
                    temperature=0.0,
                ),
            )
            parsed = json.loads(response.text)
            parsed["page"] = page_num
            return parsed
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                time.sleep(2.0 * attempt)

    raise RuntimeError(f"Gemini API 추출 실패 ({image_path.name}): {last_err}")


# ------------------------------------------------------------------------------
# 4-B. 백엔드 2: 로컬/Colab Qwen2.5-VL (T4 15GB OOM 방지 경량 설정)
# ------------------------------------------------------------------------------
def load_qwen_vlm(
    model_id: str = "Qwen/Qwen2.5-VL-7B-Instruct",
    min_pixels: int = 256 * 28 * 28,
    max_pixels: int = 384 * 28 * 28,  # T4 OOM 방지를 위해 768 -> 384로 축소
):
    import torch
    import transformers
    from transformers import AutoProcessor, BitsAndBytesConfig

    has_cuda = torch.cuda.is_available()
    processor = AutoProcessor.from_pretrained(
        model_id,
        min_pixels=min_pixels,
        max_pixels=max_pixels,
        trust_remote_code=True,
    )

    model_cls = None
    for name in ("AutoModelForImageTextToText", "Qwen2_5_VLForConditionalGeneration", "AutoModel"):
        if hasattr(transformers, name):
            model_cls = getattr(transformers, name)
            break

    if has_cuda:
        compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )
        model = model_cls.from_pretrained(
            model_id,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
    else:
        model = model_cls.from_pretrained(
            model_id,
            dtype=torch.float32,
            device_map="cpu",
            trust_remote_code=True,
        )

    model.eval()
    return processor, model


def extract_page_with_qwen(
    processor,
    model,
    image_path: Path,
    doc_role: Literal["problem", "solution"],
    page_num: int,
    max_new_tokens: int = 1024,  # T4 OOM 방지를 위해 1536 -> 1024로 축소
) -> Dict[str, Any]:
    import torch

    schema_cls = ProblemPageSchema if doc_role == "problem" else SolutionPageSchema
    schema_hint = json.dumps(schema_cls.model_json_schema(), ensure_ascii=False)
    prompt_text = (
        f"{build_structured_prompt(doc_role, page_num)}\n\n"
        f"반드시 아래 JSON Schema를 준수하는 순수 JSON 객체만 출력하세요(마크다운 코드블록 금지):\n{schema_hint}"
    )

    inputs = None
    generated_ids = None
    try:
        with Image.open(image_path) as img:
            image = img.convert("RGB")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        chat_text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = processor(
            text=[chat_text],
            images=[image],
            padding=True,
            return_tensors="pt",
        )

        target_device = next(model.parameters()).device
        inputs = {k: (v.to(target_device) if hasattr(v, "to") else v) for k, v in inputs.items()}

        with torch.inference_mode():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )

        input_len = inputs["input_ids"].shape[1]
        trimmed_ids = [out_ids[input_len:] for out_ids in generated_ids]
        raw_out = processor.batch_decode(trimmed_ids, skip_special_tokens=True)[0].strip()

        # 코드블록 제거 후 JSON 파싱
        raw_out = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_out).strip()
        parsed = json.loads(raw_out)
        parsed["page"] = page_num
        return parsed
    finally:
        del inputs, generated_ids
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


# ------------------------------------------------------------------------------
# 5. 문제지 + 해설지 병합 및 정답표-풀이 최종답 교차 검증
# ------------------------------------------------------------------------------
def _normalize_answer_str(val: str) -> str:
    """원문자(①~⑤) 및 공백/$ 기호를 정규화하여 비교 가능하게 만듭니다."""
    circle_map = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}
    s = str(val or "").strip().replace("$", "").strip()
    for k, v in circle_map.items():
        s = s.replace(k, v)
    return s


def merge_problem_and_solution(
    exam_id: str,
    prob_pages_data: Dict[str, Any],
    sol_pages_data: Dict[str, Any],
    out_path: Path,
) -> Dict[str, Any]:
    problems_by_no: Dict[int, Dict[str, Any]] = {}
    for p_info in prob_pages_data.get("pages", {}).values():
        if p_info.get("status") != "ok":
            continue
        for item in p_info.get("data", {}).get("items", []):
            q_no = int(item["question_no"])
            problems_by_no[q_no] = item

    answer_table_map: Dict[int, str] = {}
    solutions_by_no: Dict[int, Dict[str, Any]] = {}
    for p_info in sol_pages_data.get("pages", {}).values():
        if p_info.get("status") != "ok":
            continue
        page_data = p_info.get("data", {})
        for entry in page_data.get("answer_table", []):
            q_no = int(entry["question_no"])
            if 1 <= q_no <= 30 and entry.get("answer"):
                answer_table_map[q_no] = _normalize_answer_str(entry["answer"])
        for item in page_data.get("items", []):
            q_no = int(item["question_no"])
            # 여러 페이지에 걸친 문항일 경우 풀이 텍스트를 이어 붙임
            if q_no in solutions_by_no:
                solutions_by_no[q_no]["solution_steps"] += "\n" + item.get("solution_steps", "")
                if item.get("final_answer"):
                    solutions_by_no[q_no]["final_answer"] = item["final_answer"]
            else:
                solutions_by_no[q_no] = item

    merged_questions: Dict[str, Any] = {}
    mismatch_nos: List[int] = []

    for q_no in range(1, 31):
        p_item = problems_by_no.get(q_no, {})
        s_item = solutions_by_no.get(q_no, {})

        table_ans = answer_table_map.get(q_no, "")
        sol_final_ans = _normalize_answer_str(s_item.get("final_answer", ""))
        final_ans = table_ans or sol_final_ans

        is_verified = bool(table_ans and sol_final_ans and (table_ans == sol_final_ans))
        if table_ans and sol_final_ans and not is_verified:
            mismatch_nos.append(q_no)

        merged_questions[str(q_no)] = {
            "exam_id": exam_id,
            "question_no": q_no,
            "score": p_item.get("score"),
            "question_text": p_item.get("question_text", ""),
            "choices": p_item.get("choices", []),
            "figure_description": p_item.get("figure_description", "없음"),
            "answer": final_ans,
            "answer_from_table": table_ans,
            "answer_from_solution": sol_final_ans,
            "answer_verified": is_verified,
            "intent": s_item.get("intent", ""),
            "solution": s_item.get("solution_steps", ""),
        }

    result = {
        "exam_id": exam_id,
        "total_questions": 30,
        "parsed_problem_count": len(problems_by_no),
        "parsed_solution_count": len(solutions_by_no),
        "parsed_answer_table_count": len(answer_table_map),
        "answer_mismatch_nos": mismatch_nos,
        "questions": merged_questions,
    }

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[통합 완료] {out_path}")
    print(f"  - 문제 추출: {len(problems_by_no)}/30 | 해설 추출: {len(solutions_by_no)}/30 | 정답표: {len(answer_table_map)}/30")
    print(f"  - 정답 불일치 의심 문항: {mismatch_nos}")
    return result


# ------------------------------------------------------------------------------
# 6. 단일 시험 세트(문제지 + 해설지) 실행 파이프라인 (28개 배치 루프에서 호출)
# ------------------------------------------------------------------------------
def process_exam_pair(
    exam_id: str,
    prob_pdf: Path,
    sol_pdf: Path,
    out_dir: Path,
    backend: Literal["gemini", "qwen_local"] = "gemini",
    gemini_model: str = "gemini-3.8-flash",
    qwen_bundle: Optional[Tuple[Any, Any]] = None,
    render_scale: float = 2.0,
) -> Path:
    exam_out_dir = out_dir / exam_id
    img_root = exam_out_dir / "page_images"
    vlm_root = exam_out_dir / "vlm_parsed"
    vlm_root.mkdir(parents=True, exist_ok=True)

    role_results: Dict[str, Any] = {}

    for role, pdf_path in [("problem", prob_pdf), ("solution", sol_pdf)]:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

        rendered_imgs = render_pdf_to_pngs(pdf_path, img_root=img_root, scale=render_scale, overwrite=False)
        out_json_path = vlm_root / f"{pdf_path.stem}_structured.json"

        if out_json_path.exists():
            existing_data = json.loads(out_json_path.read_text(encoding="utf-8"))
        else:
            existing_data = {
                "exam_id": exam_id,
                "source_file": pdf_path.name,
                "role": role,
                "total_pages": len(rendered_imgs),
                "pages": {},
            }

        print(f"[{exam_id} | {role.upper()}] 총 {len(rendered_imgs)}페이지 파싱 시작 (backend={backend})")

        for img_path in rendered_imgs:
            page_num = int(re.search(r"page_(\d+)\.png", img_path.name).group(1))
            page_key = str(page_num)

            prev = existing_data["pages"].get(page_key, {})
            if prev.get("status") == "ok" and prev.get("data"):
                print(f"  - {page_num}페이지: 기존 정상 결과 있음 (스킵)")
                continue

            try:
                if backend == "gemini":
                    structured_page = extract_page_with_gemini(
                        image_path=img_path,
                        doc_role=role,  # type: ignore
                        page_num=page_num,
                        model_name=gemini_model,
                    )
                else:
                    if qwen_bundle is None:
                        raise ValueError("qwen_local 모드에서는 load_qwen_vlm() 결과를 전달해야 합니다.")
                    processor, model = qwen_bundle
                    structured_page = extract_page_with_qwen(
                        processor=processor,
                        model=model,
                        image_path=img_path,
                        doc_role=role,  # type: ignore
                        page_num=page_num,
                    )

                existing_data["pages"][page_key] = {
                    "page": page_num,
                    "image_path": str(img_path),
                    "status": "ok",
                    "data": structured_page,
                }
                print(f"  - {page_num}페이지: 구조화 완료 (문항 {len(structured_page.get('items', []))}개)")
            except Exception as exc:
                existing_data["pages"][page_key] = {
                    "page": page_num,
                    "image_path": str(img_path),
                    "status": f"error: {type(exc).__name__}: {exc}",
                    "data": {},
                }
                print(f"  - {page_num}페이지: 오류 발생 -> {exc}")

            out_json_path.write_text(
                json.dumps(existing_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        role_results[role] = existing_data

    merged_path = exam_out_dir / f"{exam_id}_merged.json"
    merge_problem_and_solution(
        exam_id=exam_id,
        prob_pages_data=role_results["problem"],
        sol_pages_data=role_results["solution"],
        out_path=merged_path,
    )
    return merged_path


# ------------------------------------------------------------------------------
# 7. 28개 세트 일괄 배치 실행 예시
# ------------------------------------------------------------------------------
def run_batch_all_exams(
    raw_dir: Path,
    out_dir: Path,
    backend: Literal["gemini", "qwen_local"] = "gemini",
) -> None:
    """
    raw_dir 내의 *_problem.pdf 와 *_solution.pdf 쌍을 자동으로 찾아 일괄 처리합니다.
    """
    prob_files = sorted(raw_dir.glob("*_problem.pdf"))
    print(f"탐색된 시험지 세트 수: {len(prob_files)}개")

    qwen_bundle = load_qwen_vlm() if backend == "qwen_local" else None

    for prob_pdf in prob_files:
        exam_id = prob_pdf.name.replace("_problem.pdf", "")
        sol_pdf = raw_dir / f"{exam_id}_solution.pdf"
        if not sol_pdf.exists():
            print(f"[건너뜀] 해설지 없음: {sol_pdf.name}")
            continue

        process_exam_pair(
            exam_id=exam_id,
            prob_pdf=prob_pdf,
            sol_pdf=sol_pdf,
            out_dir=out_dir,
            backend=backend,
            qwen_bundle=qwen_bundle,
        )


if __name__ == "__main__":
    project_root = Path("/content/k12-math-rag-tutor") if Path("/content/k12-math-rag-tutor").exists() else Path.cwd()
    raw_ebsi_dir = project_root / "data/raw/ebsi/h1"
    out_base_dir = (
        Path("/content/drive/MyDrive/k12_math_rag_data/structured_exams")
        if Path("/content/drive/MyDrive").exists()
        else project_root / "data/processed/structured_exams"
    )
    out_base_dir.mkdir(parents=True, exist_ok=True)

    # 1) Colab에서 실행 전 패키지 설치 및 API 키 설정:
    #    !pip install -q google-genai pydantic pypdfium2 pillow
    #    os.environ["GEMINI_API_KEY"] = "여기에_API_키_입력"
    # 2) raw_ebsi_dir 안의 28개(*_problem.pdf, *_solution.pdf) 전체 일괄 실행:
    run_batch_all_exams(
        raw_dir=raw_ebsi_dir,
        out_dir=out_base_dir,
        backend="gemini",  # 로컬 GPU로 1개씩 테스트할 때만 "qwen_local" 사용
    )