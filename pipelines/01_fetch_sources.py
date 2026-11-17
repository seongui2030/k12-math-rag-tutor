from src.colab_env import get_project_root, get_storage_dirs

if __name__ == "__main__":
    root = get_project_root()
    dirs = get_storage_dirs(root)
    print("소스 경로 확인 완료:", dirs["raw"])
