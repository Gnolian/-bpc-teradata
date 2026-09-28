from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

from app.services.sqlite_service import (
    checkpoint_wal,
    contar_indices_estrutura_api,
    criar_indices,
    criar_tabela_controle_carga_buckets,
    criar_tabela_controle_cargas,
    criar_tabela_estrutura_api,
    criar_tabela_log_consultas,
    criar_tabela_usuarios,
    verificar_espaco_sqlite,
)


def main():
    espaco = verificar_espaco_sqlite()
    print(
        "SQLite: "
        f"{espaco['path']} | espaco livre: {espaco['free_gb']:.1f} GB "
        f"de {espaco['total_gb']:.1f} GB.",
        flush=True,
    )

    print("Inicializando estruturas locais antes dos indices...", flush=True)
    criar_tabela_usuarios()
    criar_tabela_log_consultas()
    criar_tabela_controle_cargas()
    criar_tabela_controle_carga_buckets()
    criar_tabela_estrutura_api()

    antes = contar_indices_estrutura_api()
    print(f"Indices existentes na TABELA_EXEMPLO_001 antes da finalizacao: {antes}", flush=True)

    criar_indices()

    depois = contar_indices_estrutura_api()
    print(f"Indices existentes na TABELA_EXEMPLO_001 apos a finalizacao: {depois}", flush=True)

    try:
        checkpoint_wal(truncate=True)
    except Exception as exc:
        print(f"AVISO: nao foi possivel compactar o WAL apos os indices: {exc}", flush=True)

    print("Finalizacao de indices concluida.", flush=True)


if __name__ == "__main__":
    main()
