
# ==============================================================================
# 3단계 테스트: 2026_10_hs1_problem.pdf & 2026_10_hs1_solution.pdf
# - 해설지 1페이지 정답표 추출 및 1~30번 문항별 해설 분할
# - 문제지/해설지 페이지 PNG 렌더링 및 VLM 기반 수식(LaTeX)·도형 묘사 추출
# ==============================================================================

import gc
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def configure_hf_cache_env() -> None:
    """
    실행 환경(Google Colab vs Windows D: 드라이브 vs 기타 로컬)에 맞춰
    transformers / huggingface_hub 임포트 전에 캐시 경로를 설정합니다.
    """
    is_colab_env = (
        Path("/content").exists()
        and ("COLAB_RELEASE_TAG" in os.environ or "COLAB_GPU" in os.environ or Path("/content/drive").exists())
    )

    if is_colab_env:
        # 코랩 환경에서는 /content/hf_cache를 기본으로 사용(필요 시 Drive 여유 공간 활용 가능)
        hf_base = Path("/content/hf_cache")
        hf_base.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(hf_base))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_base / "hub"))
    elif os.name == "nt" and Path("D:/").exists():
        # Windows 로컬 환경에서 C: 드라이브 용량 부족을 피하기 위해 D: 드라이브 사용
        hf_base = Path("D:/hf_cache")
        hf_base.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(hf_base))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_base / "hub"))

    # CUDA 메모리 단편화 완화 옵션
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


configure_hf_cache_env()

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
def render_pdf_to_pngs(
    pdf_path: Path,
    img_root: Path,
    scale: float = 1.6,
    overwrite: bool = False,
) -> List[Path]:
    """PDF 페이지를 PNG 이미지로 변환하고 저장 경로 리스트를 반환합니다."""
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
# 3. VLM 로드 및 수식(LaTeX) + 도형 상세 묘사 추출
# ------------------------------------------------------------------------------
def _resolve_vlm_model_class():
    """설치된 transformers 버전에 맞는 비전-언어 모델 클래스를 안전하게 찾습니다."""
    for candidate_name in (
        "AutoModelForImageTextToText",
        "Qwen2_5_VLForConditionalGeneration",
        "AutoModel",
    ):
        if hasattr(transformers, candidate_name):
            cls = getattr(transformers, candidate_name)
            print(f"[VLM 클래스 선택] transformers.{candidate_name}")
            return cls

    raise RuntimeError(
        f"지원되는 VLM 모델 클래스를 찾지 못했습니다. (transformers 버전: {transformers.__version__})"
    )


def load_vlm_model(
    model_id: str = "Qwen/Qwen2.5-VL-7B-Instruct",
    min_pixels: int = 256 * 28 * 28,
    max_pixels: int = 768 * 28 * 28,
):
    """VRAM 사용량을 제어하며 VLM 프로세서와 모델을 로드합니다."""
    has_cuda = torch.cuda.is_available()
    print(f"[VLM 초기화] 모델: {model_id} | CUDA 사용 가능: {has_cuda}")
    if has_cuda:
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        print(
            f"  - GPU: {torch.cuda.get_device_name(0)} | "
            f"여유 VRAM: {free_bytes / (1024**3):.2f} GiB / 전체: {total_bytes / (1024**3):.2f} GiB"
        )

    processor = AutoProcessor.from_pretrained(
        model_id,
        min_pixels=min_pixels,
        max_pixels=max_pixels,
        trust_remote_code=True,
    )
    model_cls = _resolve_vlm_model_class()

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
        print("[안내] 현재 CUDA GPU가 감지되지 않았습니다. CPU 모드로 실행됩니다.")
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
    max_new_tokens: int = 1536,
) -> str:
    """단일 페이지 이미지에서 수식(LaTeX) 및 도형 묘사를 추출하고 GPU 메모리를 정리합니다."""
    inputs = None
    generated_ids = None
    try:
        with Image.open(image_path) as img:
            image = img.convert("RGB")

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
        inputs = {
            k: (v.to(target_device) if hasattr(v, "to") else v)
            for k, v in inputs.items()
        }

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
    finally:
        del inputs, generated_ids
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def run_two_file_vlm_test(
    prob_pdf: Path,
    sol_pdf: Path,
    out_dir: Path,
    project_root: Path,
    vlm_model_id: str = "Qwen/Qwen2.5-VL-7B-Instruct",
    max_pages_per_file: Optional[int] = None,
    specific_pages: Optional[Dict[str, List[int]]] = None,
    render_scale: float = 1.6,
    overwrite_pngs: bool = True,
    max_new_tokens: int = 1536,
) -> Dict[str, Any]:
    """
    두 PDF 파일을 대상으로 렌더링 및 VLM 파싱을 수행하고 페이지마다 즉시 저장합니다.
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

        rendered_imgs = render_pdf_to_pngs(
            pdf_path,
            img_root=img_root,
            scale=render_scale,
            overwrite=overwrite_pngs,
        )
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
            page_num = int(re.search(r"page_(\d+)\.png", img_path.name).group(1))
            page_key = str(page_num)

            prev_entry = existing_data["pages"].get(page_key, {})
            if prev_entry.get("status") == "ok" and prev_entry.get("vlm_text"):
                print(f"  - {page_num}페이지: 기존 정상 결과 있음 (스킵)")
                continue

            try:
                vlm_text = extract_math_from_image(
                    processor=processor,
                    model=model,
                    image_path=img_path,
                    prompt_text=prompt_text,
                    max_new_tokens=max_new_tokens,
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

    if sol_pdf.exists():
        sol_parsed = run_solution_parsing(sol_pdf, out_dir)
        print("\n[샘플 확인 - 1페이지 정답 1~10번]:")
        for i in range(1, 11):
            print(f"  {i}번: {sol_parsed['parsed_page1_answers'].get(str(i), '(미추출)')}")
    else:
        print("\n[안내] 해설지 PDF가 아직 없습니다. 경로를 확인해 주세요.")

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
            render_scale=1.6,
            overwrite_pngs=True,
            max_new_tokens=1536,
        )
        print("\n[VLM 테스트 저장 파일 목록]:", vlm_outputs)

        for role, json_p in vlm_outputs.items():
            data = json.loads(Path(json_p).read_text(encoding="utf-8"))
            for p_key, p_info in sorted(data.get("pages", {}).items(), key=lambda x: int(x[0])):
                print(f"\n=== [{role.upper()}] {p_key}페이지 미리보기 ({p_info.get('status')}) ===")
                print(p_info.get("vlm_text", "")[:700])