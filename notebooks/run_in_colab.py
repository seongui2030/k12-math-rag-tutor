"""
VSCode에서 Google Colab 커널/런타임에 연결해 실행하기 위한 진입 스크립트입니다.
셀 마커(# %%)를 지원하므로 VSCode에서 'Run Cell'로 바로 실행할 수 있습니다.
"""

# %%
# Resolve the repository before importing ``src``. In Colab, notebooks often
# start in /content (or another directory outside the cloned repository).
import os
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/seongui2030/k12-math-rag-tutor.git"
COLAB_CLONE_DIR = Path("/content/k12-math-rag-tutor")

if "google.colab" in sys.modules:
    from google.colab import drive

    drive.mount("/content/drive")
    if not COLAB_CLONE_DIR.exists():
        subprocess.run(["git", "clone", REPO_URL, str(COLAB_CLONE_DIR)], check=True)
    os.chdir(COLAB_CLONE_DIR)

# Also works when this file is run as a notebook from a local VS Code session.
_here = Path.cwd().resolve()
for _candidate in (_here, *_here.parents, Path(__file__).resolve().parents[1]):
    if (_candidate / "src" / "colab_env.py").is_file():
        sys.path.insert(0, str(_candidate))
        break
else:
    raise ModuleNotFoundError(
        "Could not find src/colab_env.py. Open/run this notebook from the "
        "repository, or check that the Colab clone completed."
    )

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
