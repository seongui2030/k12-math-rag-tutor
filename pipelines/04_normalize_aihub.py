import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.colab_env import get_project_root, get_storage_dirs

def normalize_aihub_dataset(aihub_dir: str) -> list:
    # 초3~고1 AI Hub 수학 데이터셋 스키마 정규화 로직 구현 위치
    return []

if __name__ == "__main__":
    root = get_project_root()
    dirs = get_storage_dirs(root)
    print("AI Hub 정규화 파이프라인 준비 완료:", dirs["raw"] / "aihub")
