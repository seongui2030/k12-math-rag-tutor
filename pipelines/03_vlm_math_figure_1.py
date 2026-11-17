# ==============================================================================
# 3단계 테스트: 2026_10_hs1_problem.pdf & 2026_10_hs1_solution.pdf
# - 해설지 1페이지 정답표 추출 및 1~30번 문항별 해설 분할
# - 문제지/해설지 페이지 PNG 렌더링 및 VLM 기반 수식(LaTeX)·도형 묘사 추출
# ==============================================================================

# 방법 A: Hugging Face 캐시 경로를 D: 드라이브로 변경 (추천)
# Python 코드 상단(import torch, import transformers 이전)에 환경변수를 지정하면, C:\Users\WJ\.cache\huggingface 대신 D: 드라이브에 모델 캐시를 저장합니다.

import os

# 반드시 transformers / huggingface_hub 임포트 전에 설정해야 합니다.
os.environ["HF_HOME"] = "D:/hf_cache"
os.environ["HUGGINGFACE_HUB_CACHE"] = "D:/hf_cache/hub"

# [선택] 코랩 최초 실행 시 주석 해제 후 설치
# !pip install -q pypdf pypdfium2 pillow torch transformers accelerate bitsandbytes qwen-vl-utils

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from pypdf import PdfReader
import pypdfium2 as pdfium
import torch
import transformers
from transformers import AutoProcessor, BitsAndBytesConfig


# ------------------------------------------------------------------------------
# 0. 환경 및 파일 경로 자동 탐색
# ------------------------------------------------------------------------------
def resolve_paths() -> Tuple[Path, Path, Path, Path]:
    """로컬/코랩/Drive 환경에서 프로젝트 루트와 두 테스트 PDF 경로를 찾습니다."""
    candidates_root = [
        Path.cwd(),
        Path("/content/k12-math-rag-tutor"),
        Path("/content/drive/MyDrive/k12-math-rag-tutor"),
        Path("/content"),
    ]

    project_root = Path.cwd()
    for cand in candidates_root:
        if (cand / "src/colab_env.py").exists() or (cand / "data/raw/ebsi/h1").exists():
            project_root = cand
            break

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # 가능한 PDF 위치 후보들
    prob_candidates = [
        project_root / "data/raw/ebsi/h1/2026_10_hs1_problem.pdf",
        Path("/content/2026_10_hs1_problem.pdf"),
        Path("/content/test_ebsi/2026_10_hs1_problem.pdf"),
        Path("/content/drive/MyDrive/2026_10_hs1_problem.pdf"),
    ]
    sol_candidates = [
        project_root / "data/raw/ebsi/h1/2026_10_hs1_solution.pdf",
        Path("/content/2026_10_hs1_solution.pdf"),
        Path("/content/test_ebsi/2026_10_hs1_solution.pdf"),
        Path("/content/drive/MyDrive/2026_10_hs1_solution.pdf"),
    ]

    prob_pdf = next((p for p in prob_candidates if p.exists()), prob_candidates[0])
    sol_pdf = next((p for p in sol_candidates if p.exists()), sol_candidates[0])

    # 출력 디렉터리 (Drive가 마운트되어 있으면 Drive에 저장, 아니면 로컬/코랩 data/interim 하위에 저장)
    if Path("/content/drive/MyDrive").exists():
        out_base = Path("/content/drive/MyDrive/k12_math_rag_data/test_2026_10_hs1")
    else:
        out_base = project_root / "data/interim/test_2026_10_hs1"

    out_base.mkdir(parents=True, exist_ok=True)
    return project_root, prob_pdf, sol_pdf, out_base


# ------------------------------------------------------------------------------
# 1. 해설지 1페이지 정답표 파싱 및 1~30번 문항별 분할
# ------------------------------------------------------------------------------
def extract_pdf_pages_text(pdf_path: Path) -> List[str]:
    reader = PdfReader(str(pdf_path))
    return [(page.extract_text() or "") for page in reader.pages]


def parse_page1_answers(page1_text: str) -> Dict[int, str]:
    """
    해설지 1페이지에서 1~30번 정답을 추출합니다.
    표 레이아웃 특성상 번호와 정답이 붙어 있거나 줄바꿈으로 나뉜 경우를 함께 처리합니다.
    """
    answers: Dict[int, str] = {}
    if not page1_text.strip():
        return answers

    # 1) '1 3', '1. 3', '1) 3', '1: 3' 형태 매칭
    joined = re.sub(r"[ \t]+", " ", page1_text)
    for m in re.finditer(
        r"(?<!\d)([1-9]|[12]\d|30)\s*[:\.\)]?\s*([1-5]|\d{1,3})\b",
        joined,
    ):
        q_no = int(m.group(1))
        ans_val = m.group(2).strip()
        if 1 <= q_no <= 30 and q_no not in answers:
            answers[q_no] = ans_val

    return answers


def split_solution_questions_1_to_30(pages_text: List[str]) -> Dict[int, str]:
    """
    해설지 전체 텍스트에서 '1. [출제의도]' ~ '30. [출제의도]' 단위로 문항별 풀이를 나눕니다.
    """
    full_text = "\n".join(
        f"[PAGE {idx + 1}]\n{txt}" for idx, txt in enumerate(pages_text)
    )
    pattern = re.compile(r"(?m)^([1-9]|[12]\d|30)\.\s*\[출제의도\]")
    matches = list(pattern.finditer(full_text))

    q_map: Dict[int, str] = {}
    for idx, match in enumerate(matches):
        q_no = int(match.group(1))
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        chunk = full_text[start:end].strip()
        if 1 <= q_no <= 30:
            if q_no not in q_map or len(chunk) > len(q_map[q_no]):
                q_map[q_no] = chunk

    return q_map


def run_solution_parsing(sol_pdf: Path, out_dir: Path) -> Dict[str, Any]:
    pages_text = extract_pdf_pages_text(sol_pdf)
    p1_answers = parse_page1_answers(pages_text[0] if pages_text else "")
    q_solutions = split_solution_questions_1_to_30(pages_text)

    structured = {
        "source_file": sol_pdf.name,
        "num_pages": len(pages_text),
        "parsed_page1_answers": {str(k): v for k, v in sorted(p1_answers.items())},
        "missing_answer_nos": [i for i in range(1, 31) if i not in p1_answers],
        "missing_solution_nos": [i for i in range(1, 31) if i not in q_solutions],
        "questions": {},
    }

    for q_no in range(1, 31):
        structured["questions"][str(q_no)] = {
            "question_no": q_no,
            "answer": p1_answers.get(q_no, ""),
            "solution": q_solutions.get(q_no, ""),
        }

    out_json = out_dir / "solution_parsed_test.json"
    out_json.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[해설 파싱 완료] {out_json}")
    print(f"  - 1페이지 추출 정답 수: {len(p1_answers)}/30 (미추출 번호: {structured['missing_answer_nos']})")
    print(f"  - 분할된 문항 해설 수: {len(q_solutions)}/30 (미추출 번호: {structured['missing_solution_nos']})")
    return structured


# ------------------------------------------------------------------------------
# 2. PDF 페이지 PNG 렌더링
# ------------------------------------------------------------------------------
def render_pdf_to_pngs(pdf_path: Path, img_root: Path, scale: float = 2.2) -> List[Path]:
    """PDF 페이지를 PNG 이미지로 변환하고 저장 경로 리스트를 반환합니다."""
    save_dir = img_root / pdf_path.stem
    save_dir.mkdir(parents=True, exist_ok=True)

    pdf_doc = pdfium.PdfDocument(str(pdf_path))
    rendered_paths: List[Path] = []
    try:
        for page_idx in range(len(pdf_doc)):
            out_png = save_dir / f"page_{page_idx + 1:02d}.png"
            if not out_png.exists():
                page = pdf_doc[page_idx]
                bitmap = page.render(scale=scale)
                pil_img = bitmap.to_pil()
                pil_img.save(str(out_png), format="PNG")
            rendered_paths.append(out_png)
    finally:
        pdf_doc.close()

    return rendered_paths


# ------------------------------------------------------------------------------
# 3. VLM 로드 및 수식(LaTeX) + 도형 상세 묘사 추출
# ------------------------------------------------------------------------------
def load_vlm_model(model_id: str = "Qwen/Qwen2.5-VL-7B-Instruct"):
    """현재 설치된 transformers 버전에 맞춰 VLM 클래스를 안전하게 선택해 로드합니다."""
    has_cuda = torch.cuda.is_available()
    print(f"[VLM 초기화] 모델: {model_id} | CUDA 사용 가능: {has_cuda}")

    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

    # 현재 transformers 버전에 존재하는 모델 클래스를 순서대로 탐색
    model_cls = None
    for candidate_name in (
        "AutoModelForImageTextToText",
        "Qwen2_5_VLForConditionalGeneration",
        "AutoModel",
    ):
        if hasattr(transformers, candidate_name):
            model_cls = getattr(transformers, candidate_name)
            print(f"[VLM 클래스 선택] transformers.{candidate_name}")
            break

    if model_cls is None:
        raise RuntimeError(
            f"지원되는 VLM 클래스를 찾지 못했습니다. (transformers 버전: {transformers.__version__})"
        )

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
        print("[안내] 현재 GPU(CUDA)가 비활성화되어 있습니다. CPU 실행은 느릴 수 있으므로 코랩 GPU 연결을 권장합니다.")
        model = model_cls.from_pretrained(
            model_id,
            dtype=torch.float32,
            device_map="cpu",
            trust_remote_code=True,
        )

    model.eval()
    return processor, model


def build_vlm_prompt(project_root: Path, doc_role: str) -> str:
    """configs/prompts/vlm_extract.txt가 있으면 읽고, 없으면 기본 프롬프트를 사용합니다."""
    prompt_file = project_root / "configs/prompts/vlm_extract.txt"
    if prompt_file.exists():
        base_prompt = prompt_file.read_text(encoding="utf-8").strip()
    else:
        base_prompt = (
            "이 수학 시험/해설 페이지 이미지의 내용을 빠짐없이 구조화해서 추출하세요.\n"
            "1. 모든 수식, 분수, 지수, 로그, 적분, 행렬, 부등호, 그리스 문자(α, β, θ 등)는 "
            "깨짐 없이 정확한 LaTeX($...$ 또는 $$...$$)로 표기하세요.\n"
            "2. 머리말(제2교시, 수학 영역 등)과 쪽수 번호는 제외하세요.\n"
            "3. 각 문항별로 문항 번호, 본문(수식 포함), 도형/그래프 상세 묘사(없으면 '없음')를 정리하세요."
        )

    role_hint = (
        "현재 문서는 [문제지]입니다. 각 문항의 문제 본문, 선택지/조건, 도형·그래프의 기하학적 구조를 정확히 적으세요."
        if doc_role == "problem"
        else "현재 문서는 [해설지]입니다. 상단 정답표(있다면)와 각 문항의 출제의도, 단계별 풀이 수식, 최종 답을 정확히 적으세요."
    )
    return f"{role_hint}\n\n{base_prompt}"


def extract_math_from_image(
    processor,
    model,
    image_path: Path,
    prompt_text: str,
    max_new_tokens: int = 2048,
) -> str:
    """단일 페이지 이미지에서 수식(LaTeX) 및 도형 묘사를 추출합니다."""
    with Image.open(image_path) as img:
        image = img.convert("RGB")

    # qwen_vl_utils가 설치되어 있으면 공식 메시지 포맷 사용, 아니면 표준 이미지 메시지 포맷 사용
    try:
        from qwen_vl_utils import process_vision_info  # type: ignore

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(image_path)},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        chat_text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[chat_text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
    except ImportError:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        if hasattr(processor, "apply_chat_template"):
            chat_text = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            chat_text = prompt_text

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
    decoded = processor.batch_decode(trimmed_ids, skip_special_tokens=True)[0]
    return decoded.strip()


def run_two_file_vlm_test(
    prob_pdf: Path,
    sol_pdf: Path,
    out_dir: Path,
    project_root: Path,
    vlm_model_id: str = "Qwen/Qwen2.5-VL-7B-Instruct",
    max_pages_per_file: Optional[int] = None,
    specific_pages: Optional[Dict[str, List[int]]] = None,
) -> Dict[str, Any]:
    """
    두 PDF 파일을 대상으로 렌더링 및 VLM 파싱을 수행하고 페이지마다 즉시 저장합니다.
    - max_pages_per_file: 예) 2를 넣으면 각 파일 앞 2페이지만 빠르게 테스트
    - specific_pages: 예) {"problem": [1, 8], "solution": [1, 2]} 처럼 특정 페이지만 지정 가능
    """
    img_root = out_dir / "page_images"
    vlm_root = out_dir / "vlm_parsed"
    vlm_root.mkdir(parents=True, exist_ok=True)

    targets = [
        ("problem", prob_pdf),
        ("solution", sol_pdf),
    ]

    processor, model = load_vlm_model(vlm_model_id)
    summary: Dict[str, Any] = {}

    for role, pdf_path in targets:
        if not pdf_path.exists():
            print(f"[경고] 파일이 없어 건너뜁니다: {pdf_path}")
            continue

        rendered_imgs = render_pdf_to_pngs(pdf_path, img_root=img_root, scale=2.2)
        selected_imgs = rendered_imgs

        if specific_pages and role in specific_pages:
            wanted_set = set(specific_pages[role])
            selected_imgs = [
                p for idx, p in enumerate(rendered_imgs, start=1) if idx in wanted_set
            ]
        elif max_pages_per_file is not None:
            selected_imgs = rendered_imgs[:max_pages_per_file]

        out_json_path = vlm_root / f"{pdf_path.stem}_vlm.json"
        if out_json_path.exists():
            existing_data = json.loads(out_json_path.read_text(encoding="utf-8"))
        else:
            existing_data = {
                "source_file": pdf_path.name,
                "role": role,
                "total_pages": len(rendered_imgs),
                "pages": {},
            }

        prompt_text = build_vlm_prompt(project_root, role)
        print(f"\n[{role.upper()}] {pdf_path.name} -> 대상 {len(selected_imgs)}페이지 VLM 추출 시작")

        for img_path in selected_imgs:
            # 파일명 page_08.png -> 8
            page_num = int(re.search(r"page_(\d+)\.png", img_path.name).group(1))
            page_key = str(page_num)

            if page_key in existing_data["pages"] and existing_data["pages"][page_key].get("vlm_text"):
                print(f"  - {page_num}페이지: 기존 결과 있음 (스킵)")
                continue

            try:
                vlm_text = extract_math_from_image(
                    processor=processor,
                    model=model,
                    image_path=img_path,
                    prompt_text=prompt_text,
                    max_new_tokens=2048,
                )
                existing_data["pages"][page_key] = {
                    "page": page_num,
                    "image_path": str(img_path),
                    "vlm_text": vlm_text,
                    "status": "ok",
                }
                print(f"  - {page_num}페이지: 추출 완료 ({len(vlm_text)}자)")
            except Exception as exc:
                existing_data["pages"][page_key] = {
                    "page": page_num,
                    "image_path": str(img_path),
                    "vlm_text": "",
                    "status": f"error: {type(exc).__name__}: {exc}",
                }
                print(f"  - {page_num}페이지: 오류 발생 -> {exc}")

            # 페이지마다 즉시 저장해 중간 중단 시에도 결과 보존
            out_json_path.write_text(
                json.dumps(existing_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        summary[role] = str(out_json_path)

    return summary


# ------------------------------------------------------------------------------
# 4. 실행 진입점
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    project_root, prob_pdf, sol_pdf, out_dir = resolve_paths()
    print("프로젝트 루트:", project_root)
    print("문제지 경로:", prob_pdf, "| 존재:", prob_pdf.exists())
    print("해설지 경로:", sol_pdf, "| 존재:", sol_pdf.exists())
    print("결과 저장 폴더:", out_dir)

    # (A) 먼저 해설지 1페이지 정답표 및 1~30번 문항 분할 테스트
    if sol_pdf.exists():
        sol_parsed = run_solution_parsing(sol_pdf, out_dir)
        print("\n[샘플 확인 - 1페이지 정답 1~10번]:")
        for i in range(1, 11):
            print(f"  {i}번: {sol_parsed['parsed_page1_answers'].get(str(i), '(미추출)')}")
    else:
        print("\n[안내] 해설지 PDF가 아직 없습니다. 경로를 확인해 주세요.")

    # (B) VLM 수식·도형 추출 테스트
    # 처음엔 핵심 페이지(문제지 1p, 8p 도형문항 / 해설지 1p 정답표, 3p 도형해설)만 먼저 테스트해 보시는 것을 추천합니다.
    # 전체 페이지를 다 돌리려면 specific_pages=None, max_pages_per_file=None 으로 변경하세요.
    if prob_pdf.exists() or sol_pdf.exists():
        vlm_outputs = run_two_file_vlm_test(
            prob_pdf=prob_pdf,
            sol_pdf=sol_pdf,
            out_dir=out_dir,
            project_root=project_root,
            vlm_model_id="Qwen/Qwen2.5-VL-7B-Instruct",
            max_pages_per_file=None,
            specific_pages={
                "problem": [1, 8],
                "solution": [1, 3],
            },
        )
        print("\n[VLM 테스트 저장 파일 목록]:", vlm_outputs)

        # 추출 결과 일부 미리보기
        for role, json_p in vlm_outputs.items():
            data = json.loads(Path(json_p).read_text(encoding="utf-8"))
            for p_key, p_info in sorted(data.get("pages", {}).items(), key=lambda x: int(x[0])):
                print(f"\n=== [{role.upper()}] {p_key}페이지 미리보기 ({p_info.get('status')}) ===")
                print(p_info.get("vlm_text", "")[:700])