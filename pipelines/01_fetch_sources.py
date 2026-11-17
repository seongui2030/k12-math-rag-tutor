import sys
from pathlib import Path

# Direct execution (``python pipelines/01_fetch_sources.py``) puts only the
# pipelines directory on sys.path. Add the repository root so ``src`` resolves.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.colab_env import get_project_root, get_storage_dirs

if __name__ == "__main__":
    root = get_project_root()
    dirs = get_storage_dirs(root)
    print("소스 경로 확인 완료:", dirs["raw"])
