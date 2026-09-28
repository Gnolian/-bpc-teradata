import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _env_file_from_args(args=None):
    args = list(sys.argv[1:] if args is None else args)
    for idx, arg in enumerate(args):
        if arg == "--env-file" and idx + 1 < len(args):
            return args[idx + 1]
        if arg.startswith("--env-file="):
            return arg.split("=", 1)[1]
    return ""


def load_app_env(base_dir: Path, args=None):
    """
    Carrega o .env principal e, opcionalmente, um arquivo complementar.

    Uso:
        python -m scripts.atualizar_base_sqlite --env-file .env.carga_202605

    O arquivo complementar sobrescreve apenas as variáveis daquela execução.
    """
    base_dir = Path(base_dir)
    load_dotenv(base_dir / ".env", override=False)

    env_file = os.getenv("SCB_ENV_FILE") or _env_file_from_args(args)
    if not env_file:
        return None

    env_path = Path(env_file)
    if not env_path.is_absolute():
        env_path = base_dir / env_path

    if not env_path.exists():
        raise FileNotFoundError(f"Arquivo de ambiente não encontrado: {env_path}")

    os.environ["SCB_ENV_FILE"] = str(env_path)
    load_dotenv(env_path, override=True)
    return env_path
