# setup_project_structure.py
from pathlib import Path


def create_file_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content.lstrip("\n"), encoding="utf-8")
        print(f"[생성] {path}")
    else:
        print(f"[유지] 이미 존재함: {path}")


def scaffold_k12_math_rag_tutor(root_dir: str = ".") -> None:
    root = Path(root_dir).resolve()
    print(f"프로젝트 루트: {root}\n")

    # 1. 확장성을 고려한 폴더 목록 생성
    dirs = [
        "configs/prompts",
        "notebooks",
        "data/raw/ebsi/h1",
        "data/raw/ebsi/h2",
        "data/raw/ebsi/h3",
        "data/raw/aihub/e3_to_e6",
        "data/raw/aihub/m1_to_m3",
        "data/raw/aihub/h1",
        "data/raw/benchmarks/matharena_aime2026",
        "data/interim/page_images",
        "data/interim/vlm_parsed",
        "data/processed",
        "data/indexes",
        "pipelines",
        "src",
        "app",
    ]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
        print(f"[폴더] {d}")

    print("-" * 50)

    # 2. .gitignore (대용량 산출물·인덱스·캐시·로컬 테스트 파일 제외)
    gitignore_content = """
# Python & VSCode
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.venv/
venv/
.env
.vscode/*
!.vscode/settings.json
!.vscode/extensions.json

# Data, Images, Vector Indexes & Temp Test Files
data/interim/
data/indexes/
*.faiss
*.pkl
*.png
*.jpg
*.jpeg
*.pdf
!data/raw/**/.gitkeep
"""
    create_file_if_missing(root / ".gitignore", gitignore_content)

    # 3. requirements.txt
    requirements_content = """
pypdf
pypdfium2
pillow
torch
transformers
accelerate
bitsandbytes
qwen-vl-utils
sentence-transformers
faiss-cpu
langchain-core
langchain-community
langchain-text-splitters
gradio
pyyaml
"""
    create_file_if_missing(root / "requirements.txt", requirements_content)

    # 4. configs/grades.yaml
    grades_yaml_content = """
grades:
  e3: "초등학교 3학년"
  e4: "초등학교 4학년"
  e5: "초등학교 5학년"
  e6: "초등학교 6학년"
  m1: "중학교 1학년"
  m2: "중학교 2학년"
  m3: "중학교 3학년"
  h1: "고등학교 1학년"
  h2: "고등학교 2학년"
  h3: "고등학교 3학년"

sources:
  - ebsi
  - aihub
  - matharena
"""
    create_file_if_missing(root / "configs/grades.yaml", grades_yaml_content)

    # 5. configs/prompts/vlm_extract.txt
    vlm_prompt_content = """
이 수학 시험/해설 페이지 이미지의 내용을 빠짐없이 구조화해서 추출하세요.
규칙:
1. 모든 수식, 분수, 지수, 로그, 적분, 행렬, 부등호, 그리스 문자(α, β, θ 등)는 깨짐 없이 정확한 LaTeX($...$ 또는 $$...$$)로 표기하세요.
2. 머리말(제2교시, 수학 영역 등)과 쪽수 번호는 제외하세요.
3. 각 문항별로 아래 형식을 따르세요:
   - 문항 번호: [번호]
   - 문제/해설 본문: (수식 포함 원문 충실히 기록)
   - 도형/그래프 상세 묘사: (도형이나 그래프가 있는 경우 도형 종류, 점/꼭짓점/직선/곡선 이름, 표시된 길이·각도·좌표·점선 위치 등을 누락 없이 서술. 없으면 '없음')
"""
    create_file_if_missing(root / "configs/prompts/vlm_extract.txt", vlm_prompt_content)

    # 6. configs/prompts/rag_solver.txt
    rag_prompt_content = """
당신은 초3~고3 교육과정 및 수학 경시대회 문제를 다루는 수학 전문가입니다.
제공된 참고 자료(문제, 정답, 해설, 도형 묘사)의 개념과 풀이 전략을 바탕으로 문제를 단계별로 정확히 풀이하세요.
수식과 계산 과정을 빠짐없이 적고 마지막 줄에 최종 정답을 명확히 제시하세요.
"""
    create_file_if_missing(root / "configs/prompts/rag_solver.txt", rag_prompt_content)

    # 7. VSCode에서 코랩 연결 시 공통으로 부르는 환경/경로 헬퍼 (src/colab_env.py)
    colab_env_content = """
import os
import subprocess
from pathlib import Path


def is_colab() -> bool:
    try:
        import google.colab  # type: ignore
        return True
    except ImportError:
        return False


def get_project_root(
    repo_url: str = "https://github.com/seongui2030/k12-math-rag-tutor.git",
    colab_clone_dir: str = "/content/k12-math-rag-tutor",
    mount_drive: bool = True,
) -> Path:
    \"\"\"
    VSCode 로컬 환경과 Google Colab 환경(VSCode Colab 확장 또는 Colab 노트북) 양쪽에서
    동일한 프로젝트 루트 경로를 반환합니다.
    \"\"\"
    if is_colab():
        if mount_drive:
            from google.colab import drive  # type: ignore
            drive_path = "/content/drive"
            if not os.path.exists(drive_path):
                drive.mount(drive_path)

        repo_path = Path(colab_clone_dir)
        if not repo_path.exists():
            subprocess.run(["git", "clone", repo_url, str(repo_path)], check=True)
        os.chdir(repo_path)
        return repo_path

    # 로컬 VSCode 실행 시 현재 파일 또는 작업 디렉터리 기준 루트 반환
    return Path(__file__).resolve().parent.parent


def get_storage_dirs(project_root: Path, drive_base: str = "/content/drive/MyDrive/k12_math_rag_data") -> dict:
    \"\"\"
    무거운 중간 산출물/인덱스는 코랩일 때 Google Drive에, 로컬일 때 data/ 하위에 저장합니다.
    \"\"\"
    if is_colab() and os.path.exists("/content/drive/MyDrive"):
        base = Path(drive_base)
    else:
        base = project_root / "data"

    dirs = {
        "raw": project_root / "data/raw",
        "page_images": base / "interim/page_images",
        "vlm_parsed": base / "interim/vlm_parsed",
        "processed": base / "processed",
        "indexes": base / "indexes",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs
"""
    create_file_if_missing(root / "src/colab_env.py", colab_env_content)

    # 8. 파이프라인 스켈레톤 파일들 (pipelines/01 ~ 05)
    pipeline_files = {
        "pipelines/01_fetch_sources.py": """
from src.colab_env import get_project_root, get_storage_dirs

if __name__ == "__main__":
    root = get_project_root()
    dirs = get_storage_dirs(root)
    print("소스 경로 확인 완료:", dirs["raw"])
""",
        "pipelines/02_parse_answers_and_q.py": """
from src.colab_env import get_project_root, get_storage_dirs

def parse_answer_table_page1(page1_text: str) -> dict:
    # 1페이지 정답표(1~30번) 파싱 로직 구현 위치
    return {}

def split_questions_1_to_30(body_text: str) -> dict:
    # 1~30번 문항별 분할 로직 구현 위치
    return {}

if __name__ == "__main__":
    root = get_project_root()
    dirs = get_storage_dirs(root)
    print("정답표 및 문항 분할 파이프라인 준비 완료:", dirs["processed"])
""",
        "pipelines/03_vlm_math_figure.py": """
from src.colab_env import get_project_root, get_storage_dirs

def render_pdf_pages(pdf_path: str, out_dir: str, scale: float = 2.5) -> list:
    # PDF 페이지를 고해상도 PNG로 렌더링하는 로직 구현 위치
    return []

def extract_math_and_figure(image_path: str) -> str:
    # VLM 기반 LaTeX 수식 및 도형 묘사 추출 로직 구현 위치
    return ""

if __name__ == "__main__":
    root = get_project_root()
    dirs = get_storage_dirs(root)
    print("VLM 수식/도형 추출 파이프라인 준비 완료:", dirs["vlm_parsed"])
""",
        "pipelines/04_normalize_aihub.py": """
from src.colab_env import get_project_root, get_storage_dirs

def normalize_aihub_dataset(aihub_dir: str) -> list:
    # 초3~고1 AI Hub 수학 데이터셋 스키마 정규화 로직 구현 위치
    return []

if __name__ == "__main__":
    root = get_project_root()
    dirs = get_storage_dirs(root)
    print("AI Hub 정규화 파이프라인 준비 완료:", dirs["raw"] / "aihub")
""",
        "pipelines/05_build_faiss_index.py": """
from src.colab_env import get_project_root, get_storage_dirs

def build_faiss_index(docs: list, index_dir: str, embedding_model_name: str = "BAAI/bge-m3") -> None:
    # FAISS 벡터 인덱스 생성 및 저장 로직 구현 위치
    pass

if __name__ == "__main__":
    root = get_project_root()
    dirs = get_storage_dirs(root)
    print("FAISS 인덱싱 파이프라인 준비 완료:", dirs["indexes"])
""",
    }
    for rel_path, code in pipeline_files.items():
        create_file_if_missing(root / rel_path, code)

    # 9. src 모듈 스켈레톤 및 app/app.py
    create_file_if_missing(
        root / "src/__init__.py",
        "\"\"\"Core modules for k12-math-rag-tutor.\"\"\"\n",
    )
    create_file_if_missing(
        root / "src/retriever.py",
        """
from pathlib import Path

def load_retriever(index_dir: Path, k: int = 4):
    # 저장된 FAISS 인덱스를 불러와 retriever 반환
    return None
""",
    )
    create_file_if_missing(
        root / "src/generator.py",
        """
def generate_solution(prompt: str, model_id: str, temperature: float = 0.2) -> str:
    # 수학 추론 모델(양자화 모델 또는 외부 엔드포인트) 호출
    return ""
""",
    )
    create_file_if_missing(
        root / "src/verifier.py",
        """
def verify_answer(pred_answer: str, gold_answer: str) -> bool:
    return pred_answer.strip() == gold_answer.strip()
""",
    )
    create_file_if_missing(
        root / "app/app.py",
        """
import gradio as gr

def respond(question: str, grade: str):
    return f"[{grade}] 입력된 문제:\\n{question}\\n\\n(RAG 및 추론 모델 연결 예정)"

with gr.Blocks(title="K-12 Math RAG Tutor") as demo:
    gr.Markdown("# 초3~고3 수학 RAG 풀이 도우미")
    grade_dd = gr.Dropdown(
        choices=["e3", "e4", "e5", "e6", "m1", "m2", "m3", "h1", "h2", "h3"],
        value="h1",
        label="학년 선택",
    )
    q_box = gr.Textbox(label="수학 문제 입력", lines=6)
    btn = gr.Button("풀이 생성", variant="primary")
    out_box = gr.Textbox(label="풀이 결과", lines=12)
    btn.click(respond, inputs=[q_box, grade_dd], outputs=out_box)

if __name__ == "__main__":
    demo.launch()
""",
    )

    # 10. VSCode에서 코랩 연결 시 바로 쓸 수 있는 진입 스크립트 (notebooks/run_in_colab.py)
    colab_entry_content = """
\"\"\"
VSCode에서 Google Colab 커널/런타임에 연결해 실행하기 위한 진입 스크립트입니다.
셀 마커(# %%)를 지원하므로 VSCode에서 'Run Cell'로 바로 실행할 수 있습니다.
\"\"\"

# %%
from src.colab_env import is_colab, get_project_root, get_storage_dirs

print("코랩 환경 여부:", is_colab())
PROJECT_ROOT = get_project_root(
    repo_url="https://github.com/seongui2030/k12-math-rag-tutor.git",
    colab_clone_dir="/content/k12-math-rag-tutor",
    mount_drive=True,
)
STORAGE = get_storage_dirs(PROJECT_ROOT)
print("PROJECT_ROOT:", PROJECT_ROOT)
print("STORAGE:", STORAGE)

# %%
# 테스트용 2개 파일 확인 경로 예시:
# STORAGE["raw"] / "ebsi/h1/2026_10_hs1_problem.pdf"
# STORAGE["raw"] / "ebsi/h1/2026_10_hs1_solution.pdf"
"""
    create_file_if_missing(root / "notebooks/run_in_colab.py", colab_entry_content)

    # 11. .vscode/settings.json (VSCode Python & Jupyter/Colab 환경 통일)
    vscode_settings = """
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "jupyter.askForKernelRestart": false,
  "files.encoding": "utf8"
}
"""
    create_file_if_missing(root / ".vscode/settings.json", vscode_settings)

    print("\n전체 폴더 및 파일 생성이 완료되었습니다.")


if __name__ == "__main__":
    scaffold_k12_math_rag_tutor(".")