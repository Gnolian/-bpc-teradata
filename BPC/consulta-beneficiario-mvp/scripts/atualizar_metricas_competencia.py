import argparse
from pathlib import Path

from app.config.env_loader import load_app_env

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE_USADO = load_app_env(BASE_DIR)

from app.services.sqlite_service import (  # noqa: E402
    atualizar_metricas_carga,
    calcular_metricas_competencia,
    get_connection,
)


def obter_carga_id(competencia: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM controle_cargas
            WHERE competencia = ?
              AND status = 'SUCESSO'
            ORDER BY id DESC
            LIMIT 1
            """,
            (competencia,),
        ).fetchone()

    if not row:
        raise RuntimeError(
            f"Nenhuma carga com status SUCESSO encontrada para a competencia {competencia}."
        )

    return int(row["id"])


def main():
    parser = argparse.ArgumentParser(
        description="Recalcula e grava metricas de uma competencia ja carregada no SQLite."
    )
    parser.add_argument("--competencia", type=int, required=True)
    args, _ = parser.parse_known_args()

    if ENV_FILE_USADO:
        print(f"Arquivo de ambiente complementar: {ENV_FILE_USADO}", flush=True)

    competencia = args.competencia
    print(f"Calculando metricas da competencia {competencia}...", flush=True)
    metricas = calcular_metricas_competencia(competencia)
    carga_id = obter_carga_id(competencia)

    atualizar_metricas_carga(
        carga_id=carga_id,
        competencia_referencia=metricas["competencia_referencia"],
        qtd_bpc_pcd=metricas["qtd_bpc_pcd"],
        qtd_bpc_idoso=metricas["qtd_bpc_idoso"],
        qtd_auxilio_inclusao=metricas["qtd_auxilio_inclusao"],
        qtd_rmv_total=metricas["qtd_rmv_total"],
        qtd_zika_virus=metricas["qtd_zika_virus"],
        total_beneficios=metricas["total_beneficios"],
        total_registros=metricas["total_registros"],
    )

    print(f"Metricas gravadas na carga id {carga_id}.", flush=True)
    print(metricas, flush=True)


if __name__ == "__main__":
    main()
