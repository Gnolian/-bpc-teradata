from app.services.teradata_service import (
    obter_resumo_competencia_teradata,
)

MAPA_CHAVE_TIPO = {
    "BENEFICIARIO_CADUNICO": "NU_NB",
    "MEMBRO_FAMILIAR": "CO_CHV_NATURAL_PESSOA",
    "NAO_CADASTRADO": "NU_NB",
}


def montar_tarefas_competencia_buckets(
    competencia_atual: int,
    total_buckets: int = 200,
    fase_inicial: str = None,
    bucket_inicial: int = 0
):
    print(
        f"Consultando resumo da competência {competencia_atual} no Teradata...",
        flush=True
    )
    resumo = obter_resumo_competencia_teradata(competencia_atual)
    total = resumo["total"]
    print(
        f"Total encontrado para a competência {competencia_atual}: {total}",
        flush=True
    )

    if total == 0:
        print(
            f"Nenhum registro encontrado para a competência {competencia_atual}.",
            flush=True
        )
        return []

    fases_carga = resumo["tipos"]
    totais_por_tipo = resumo["totais_por_tipo"]
    print(
        f"Tipos de registro identificados para a competência {competencia_atual}: {fases_carga}",
        flush=True
    )

    tarefas = []
    iniciou = fase_inicial is None

    for fase in fases_carga:
        if fase not in MAPA_CHAVE_TIPO:
            print(
                f"Fase {fase} ignorada por não possuir chave de bucket configurada.",
                flush=True
            )
            continue

        if not iniciou:
            if fase == fase_inicial:
                iniciou = True
            else:
                continue

        chave_sql = MAPA_CHAVE_TIPO[fase]
        inicio_bucket = bucket_inicial if fase == fase_inicial else 0

        for bucket in range(inicio_bucket, total_buckets):
            tarefas.append({
                "competencia": competencia_atual,
                "fase": fase,
                "bucket": bucket,
                "total_buckets": total_buckets,
                "chave_sql": chave_sql,
                "total_registros_fase": totais_por_tipo.get(fase, 0),
                "total_competencia": total,
            })

    print(
        f"Total de tarefas geradas para a competência {competencia_atual}: {len(tarefas)}",
        flush=True
    )
    return tarefas
