from huggingface_hub import snapshot_download
#from specbot.embedding.config import EMBEDDING_MODEL_CONFIGS

def download_model(model_name: str, local_dir: str) -> None:
    snapshot_download(
        repo_id=model_name,
        local_dir=local_dir,
        local_dir_use_symlinks=False
    )

if __name__ == "__main__":
    download_model("Qwen/Qwen3-Embedding-0.6B", local_dir="./Qwen3-Embedding-0.6B")