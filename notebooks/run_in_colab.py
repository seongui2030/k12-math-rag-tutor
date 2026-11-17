"""
VSCode에서 Google Colab 커널/런타임에 연결해 실행하기 위한 진입 스크립트입니다.
셀 마커(# %%)를 지원하므로 VSCode에서 'Run Cell'로 바로 실행할 수 있습니다.
"""

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
