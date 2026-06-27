from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"


def load_runtime_env() -> None:
    load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    llm_model: str = "deepseek:deepseek-v4-flash"
    sandbox_container_name: str = "agent_sandbox"
    sandbox_workdir: str = "/workspace"
    sandbox_shell: str = "bash"
    sandbox_exec_timeout: int = 120
    sandbox_max_output_bytes: int = 100_000
    sandbox_skills_dir: str = "/input/skills"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_runtime_env()
    return Settings()
