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
    """
    VSCode 로컬 환경과 Google Colab 환경(VSCode Colab 확장 또는 Colab 노트북) 양쪽에서
    동일한 프로젝트 루트 경로를 반환합니다.
    """
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
    """
    무거운 중간 산출물/인덱스는 코랩일 때 Google Drive에, 로컬일 때 data/ 하위에 저장합니다.
    """
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
