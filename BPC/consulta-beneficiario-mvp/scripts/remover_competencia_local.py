import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.sqlite_service import (
    contar_indices_estrutura_api,
    contar_registros_competencia,
    criar_indices,
    criar_tabela_controle_carga_buckets,
    criar_tabela_controle_cargas,
    excluir_competencia,
    get_connection,
    limpar_controle_competencia,
)


def contar_linhas_controle(competencia: int) -> tuple[int, int]:
    with get_connection() as conn:
        row_cargas = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM controle_cargas
            WHERE competencia = ?
            """,
            (competencia,),
        ).fetchone()
        row_buckets = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM controle_carga_buckets
            WHERE competencia = ?
            """,
            (competencia,),
        ).fetchone()

    total_cargas = int(row_cargas["total"]) if row_cargas and row_cargas["total"] is not None else 0
    total_buckets = int(row_buckets["total"]) if row_buckets and row_buckets["total"] is not None else 0
    return total_cargas, total_buckets


def main():
    parser = argparse.ArgumentParser(
        description="Remove uma competência local do SQLite e recria os índices da TABELA_EXEMPLO_001."
    )
    parser.add_argument(
        "--competencia",
        required=True,
        type=int,
        help="Competência no formato AAAAMM. Exemplo: 202603",
    )
    args = parser.parse_args()

    competencia = args.competencia

    criar_tabela_controle_cargas()
    criar_tabela_controle_carga_buckets()

    total_registros_antes = contar_registros_competencia(competencia)
    total_cargas_antes, total_buckets_antes = contar_linhas_controle(competencia)
    total_indices_antes = contar_indices_estrutura_api()

    print(f"Competência alvo: {competencia}", flush=True)
    print(f"Registros encontrados em TABELA_EXEMPLO_001: {total_registros_antes}", flush=True)
    print(f"Linhas encontradas em controle_cargas: {total_cargas_antes}", flush=True)
    print(f"Linhas encontradas em controle_carga_buckets: {total_buckets_antes}", flush=True)
    print(f"Índices atuais em TABELA_EXEMPLO_001: {total_indices_antes}", flush=True)

    excluir_competencia(competencia)
    limpar_controle_competencia(competencia)
    criar_indices()

    total_registros_depois = contar_registros_competencia(competencia)
    total_cargas_depois, total_buckets_depois = contar_linhas_controle(competencia)
    total_indices_depois = contar_indices_estrutura_api()

    print("", flush=True)
    print("Limpeza concluída.", flush=True)
    print(f"Registros restantes em TABELA_EXEMPLO_001 para {competencia}: {total_registros_depois}", flush=True)
    print(f"Linhas restantes em controle_cargas para {competencia}: {total_cargas_depois}", flush=True)
    print(f"Linhas restantes em controle_carga_buckets para {competencia}: {total_buckets_depois}", flush=True)
    print(f"Índices disponíveis após recriação: {total_indices_depois}", flush=True)


if __name__ == "__main__":
    main()
