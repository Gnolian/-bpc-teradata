import os
import time
from pathlib import Path

import pandas as pd
import teradatasql

from app.config.env_loader import load_app_env

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE_USADO = load_app_env(BASE_DIR)

from app.services.sqlite_service import (  # noqa: E402
    atualizar_metricas_carga,
    calcular_metricas_competencia,
    criar_tabela_controle_cargas,
    criar_tabela_estrutura_api,
    excluir_competencia,
    get_connection,
    inserir_lote,
    registrar_fim_carga,
    registrar_inicio_carga,
)


def str_para_bool(valor: str | None, padrao: bool = False) -> bool:
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "sim", "yes", "y")


def get_td_connection():
    host = os.getenv("TD_HOST")
    user = os.getenv("TD_USER")
    password = os.getenv("TD_PASSWORD")
    logmech = os.getenv("TD_LOGMECH", "LDAP")

    if not host:
        raise RuntimeError("TD_HOST nao configurado no .env.")
    if not user:
        raise RuntimeError("TD_USER nao configurado no .env.")
    if password is None:
        raise RuntimeError("TD_PASSWORD nao configurado no .env.")

    return teradatasql.connect(host=host, user=user, password=password, logmech=logmech)


def referencia_configurada() -> int:
    valor = (
        os.getenv("TD_REF_MACICA_SOMENTE", "").strip()
        or os.getenv("TD_COMPETENCIA", "").strip()
        or os.getenv("TD_COMPETENCIAS", "").split(",")[0].strip()
    )
    if not valor:
        raise RuntimeError("Informe TD_REF_MACICA_SOMENTE=AAAAMM ou TD_COMPETENCIA=AAAAMM.")
    return int(valor)


def mes_anterior(ref: int) -> int:
    ano = ref // 100
    mes = ref % 100
    if mes == 1:
        return (ano - 1) * 100 + 12
    return ano * 100 + (mes - 1)


def montar_sql_lote(referencia: int, ref_anterior: int, fetch_size: int) -> str:
    return f"""
        SELECT TOP {fetch_size}
            'NAO_CADASTRADO' AS TIPO_REGISTRO,
            CAST(A.NU_NB AS VARCHAR(20)) AS NU_NB,
            CAST(NULL AS VARCHAR(30)) AS CO_FAMILIAR_FAM,
            CAST(A.NU_CPF_T AS VARCHAR(20)) AS NU_CPF_T,
            CAST(NULL AS VARCHAR(20)) AS NUM_CPF_PESSOA,
            CAST(NULL AS VARCHAR(30)) AS CO_CHV_NATURAL_PESSOA,
            CAST(A.ID_NIT_T AS VARCHAR(30)) AS NU_NIS_T,
            CAST(NULL AS VARCHAR(30)) AS NUM_NIS_PESSOA_ATUAL,
            A.NM_TIT_BENEF_T,
            CAST(NULL AS VARCHAR(255)) AS NOM_PESSOA,
            CAST(NULL AS VARCHAR(255)) AS DESC_PARENTESCO,
            'PENDENTE_CADUNICO' AS FLAG_CADUNICO,
            CASE WHEN ANT.NU_NB IS NOT NULL THEN '1' ELSE '0' END AS FLAG_REF_MACICA_ANTERIOR,
            A.NM_UF_MUN_T AS UF_MACICA,
            A.NM_MUN_T AS MUNICIPIO_MACICA,
            CAST(NULL AS VARCHAR(2)) AS UF_CAD,
            CAST(NULL AS VARCHAR(255)) AS MUNICIPIO_CAD,
            CAST(NULL AS VARCHAR(2)) AS UF_AG_PGD,
            CAST(NULL AS VARCHAR(255)) AS MUNICIPIO_AG_PGD,
            A.DT_NASC_T,
            CAST(NULL AS DATE) AS DTA_NASC_PESSOA,
            CAST
            (
                MONTHS_BETWEEN
                (
                    LAST_DAY(CAST(CAST(A.NU_MES_REF AS CHAR(6)) || '01' AS DATE FORMAT 'YYYYMMDD')),
                    A.DT_NASC_T
                ) / 12 AS INTEGER
            ) AS IDADE_T,
            CAST(NULL AS INTEGER) AS IDADE_PESSOA,
            A.NM_MAE_T,
            CAST(NULL AS VARCHAR(255)) AS NOM_COMPLETO_MAE_PESSOA,
            CASE
                WHEN A.CS_SEXO_T = 1 THEN 'MASCULINO'
                WHEN A.CS_SEXO_T = 3 THEN 'FEMININO'
                ELSE 'NAO INFORMADO'
            END AS GENERO,
            'NAO INFORMADO' AS RACA_COR,
            CAST(NULL AS VARCHAR(20)) AS IND_DORMIR_RUA_MEMB,
            CAST(NULL AS VARCHAR(20)) AS FAMILIA_INDIGENA,
            CAST(NULL AS VARCHAR(20)) AS FAMILIA_QUILOMBOLA,
            CAST(A.CS_ESPECIE AS VARCHAR(20)) AS CS_ESPECIE,
            CAST(A.CS_DIAG_1 AS VARCHAR(20)) AS CID,
            CASE
                WHEN D.DS_DESCRICAO IS NOT NULL THEN D.DS_DESCRICAO
                WHEN D.DS_DESCRICAO IS NULL AND A.CS_ESPECIE <> 87 THEN 'NAO SE APLICA'
                ELSE 'NAO ENCONTRADO'
            END AS DESCRICAO_CID,
            CASE
                WHEN A.CS_DESPACHO <> 4 THEN 'ADMINISTRATIVA'
                WHEN A.CS_DESPACHO = 4 THEN 'JUDICIAL'
                ELSE 'NAO INFORMADO'
            END AS TIPO_DESPACHO,
            A.D2_DDB AS DT_DESPACHO,
            A.D2_DER AS DT_ENTRADA_REQUERIMENTO,
            A.D2_DIB AS DT_INICIO_BENEFICIO,
            'MACICA_PROVISORIA_CADUNICO_PENDENTE' AS SITUACAO_CAD_UNICO,
            'NAO' AS PARTICIPACAO_CAMPANHA,
            CAST(NULL AS DATE) AS DTA_ATUAL_MEMB,
            {referencia} AS NU_MES_REF
        FROM
        (
            SELECT
                M.NU_NB,
                M.NU_CPF_T,
                M.ID_NIT_T,
                M.NM_TIT_BENEF_T,
                M.NM_UF_MUN_T,
                M.NM_MUN_T,
                M.DT_NASC_T,
                M.NM_MAE_T,
                M.CS_SEXO_T,
                M.CS_ESPECIE,
                M.CS_DIAG_1,
                M.CS_DESPACHO,
                M.D2_DDB,
                M.D2_DER,
                M.D2_DIB,
                M.NU_MES_REF,
                ROW_NUMBER() OVER (PARTITION BY M.NU_NB ORDER BY M.NU_NB) AS RN
            FROM BASE_EXEMPLO_06.TABELA_EXEMPLO_073 M
            WHERE M.CS_SIT_BENEF = 0
              AND M.CS_ESPECIE IN (11,12,18,30,40,60,87,88)
              AND M.CS_PA <> 3
              AND M.NU_MES_REF = {referencia}
              AND CAST(M.NU_NB AS BIGINT) > ?
        ) A
        LEFT JOIN
        (
            SELECT DISTINCT NU_NB
            FROM BASE_EXEMPLO_06.TABELA_EXEMPLO_073
            WHERE CS_SIT_BENEF = 0
              AND CS_ESPECIE IN (11,12,18,30,40,60,87,88)
              AND CS_PA <> 3
              AND NU_MES_REF = {ref_anterior}
        ) ANT
            ON A.NU_NB = ANT.NU_NB
        LEFT JOIN
        (
            SELECT CO_CID, MAX(DS_DESCRICAO) AS DS_DESCRICAO
            FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_069
            GROUP BY 1
        ) D
            ON A.CS_DIAG_1 = D.CO_CID
        WHERE A.RN = 1
        ORDER BY CAST(A.NU_NB AS BIGINT)
    """


def buscar_lote(cursor, sql: str, ultima_chave: int) -> tuple[pd.DataFrame, int | None]:
    cursor.execute(sql, (ultima_chave,))
    rows = cursor.fetchall()
    colunas = [desc[0] for desc in cursor.description]
    df = pd.DataFrame(rows, columns=colunas)

    if df.empty:
        return df, None

    chaves = pd.to_numeric(df["NU_NB"], errors="coerce")
    maior_chave = chaves.max()
    if pd.isna(maior_chave):
        return df, None

    return df, int(maior_chave)


def obter_ultima_carga_macica(referencia: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, status, total_registros, observacao
            FROM controle_cargas
            WHERE competencia = ?
              AND nome_origem = 'BASE_EXEMPLO_06.TABELA_EXEMPLO_073'
            ORDER BY id DESC
            LIMIT 1
            """,
            (referencia,),
        ).fetchone()
    return dict(row) if row else None


def obter_progresso_local(referencia: int) -> tuple[int, int]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                MAX(CAST(NU_NB AS INTEGER)) AS ultima_chave
            FROM TABELA_EXEMPLO_001
            WHERE NU_MES_REF = ?
              AND TIPO_REGISTRO = 'NAO_CADASTRADO'
              AND (
                    FLAG_CADUNICO = 'PENDENTE_CADUNICO'
                 OR SITUACAO_CAD_UNICO = 'MACICA_PROVISORIA_CADUNICO_PENDENTE'
              )
            """,
            (referencia,),
        ).fetchone()

    total = int(row["total"] or 0) if row else 0
    ultima_chave = int(row["ultima_chave"] or -1) if row else -1
    return total, ultima_chave


def main():
    if ENV_FILE_USADO:
        print(f"Arquivo de ambiente complementar: {ENV_FILE_USADO}", flush=True)

    referencia = referencia_configurada()
    ref_anterior = mes_anterior(referencia)
    fetch_size = int(os.getenv("TD_FETCH_SIZE", "75000"))
    apagar_antes = str_para_bool(os.getenv("MACICA_DIRETA_APAGAR_SQLITE_ANTES", "true"), True)
    calcular_metricas = str_para_bool(os.getenv("MACICA_DIRETA_CALCULAR_METRICAS", "true"), True)
    retomar = str_para_bool(os.getenv("MACICA_DIRETA_RETOMAR", "true"), True)
    forcar_recarga = str_para_bool(os.getenv("MACICA_DIRETA_FORCAR_RECARGA", "false"), False)

    print("=" * 80, flush=True)
    print(f"Carga Macica direta para SQLite: {referencia}", flush=True)
    print("Este modo nao grava na BASE_EXEMPLO_01 e nao usa tabela intermediaria no Teradata.", flush=True)
    print(f"Lote de leitura: {fetch_size}", flush=True)
    print("=" * 80, flush=True)

    criar_tabela_estrutura_api()
    criar_tabela_controle_cargas()

    ultima_carga = obter_ultima_carga_macica(referencia)
    status_anterior = str((ultima_carga or {}).get("status") or "").upper()

    if status_anterior == "SUCESSO" and not forcar_recarga:
        print(
            f"A Macica {referencia} ja possui carga concluida. "
            "Use MACICA_DIRETA_FORCAR_RECARGA=true somente para recarregar.",
            flush=True,
        )
        return

    pode_retomar = (
        retomar
        and not forcar_recarga
        and status_anterior in {"EM_ANDAMENTO", "ERRO"}
    )

    total = 0
    ultima_chave = -1
    if pode_retomar:
        total, ultima_chave = obter_progresso_local(referencia)
        pode_retomar = total > 0 and ultima_chave >= 0

    if pode_retomar:
        print(
            f"Retomando Macica {referencia}: {total} registros preservados | "
            f"NU_NB > {ultima_chave}.",
            flush=True,
        )
    elif apagar_antes or forcar_recarga:
        print(f"Removendo registros locais existentes da competencia {referencia}...", flush=True)
        excluir_competencia(referencia)
        total = 0
        ultima_chave = -1

    carga_id = registrar_inicio_carga(
        competencia=referencia,
        nome_origem="BASE_EXEMPLO_06.TABELA_EXEMPLO_073",
        data_arquivo=None,
        observacao=(
            "Retomada da carga provisoria direta da Macica para SQLite."
            if pode_retomar
            else "Carga provisoria direta da Macica para SQLite."
        ),
    )

    total_inicial = total
    inicio = time.time()
    sql = montar_sql_lote(referencia, ref_anterior, fetch_size)

    try:
        conn = get_td_connection()
        try:
            cursor = conn.cursor()
            lote = 0
            while True:
                lote += 1
                print(
                    f"Consultando lote {lote} da referencia {referencia} | NU_NB > {ultima_chave}...",
                    flush=True,
                )
                df, nova_chave = buscar_lote(cursor, sql, ultima_chave)
                if df.empty:
                    break

                qtd = inserir_lote(df)
                total += qtd
                ultima_chave = nova_chave if nova_chave is not None else ultima_chave
                decorrido = time.time() - inicio
                inseridos_execucao = total - total_inicial
                taxa = inseridos_execucao / decorrido if decorrido > 0 else 0
                print(
                    f"Lote {lote} gravado: {qtd} registros | total {total} | "
                    f"ultima chave {ultima_chave} | {taxa:.2f} reg/s",
                    flush=True,
                )

                if qtd < fetch_size:
                    break
        finally:
            conn.close()

        registrar_fim_carga(
            carga_id=carga_id,
            total_registros=total,
            status="SUCESSO",
            observacao=f"Carga provisoria Macica direta concluida. Inseridos {total} registros.",
        )

        if calcular_metricas:
            try:
                print(f"Calculando metricas da competencia {referencia} para o painel inicial...", flush=True)
                metricas = calcular_metricas_competencia(referencia)
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
                print(f"Metricas gravadas: {metricas}", flush=True)
            except Exception as exc:
                print(
                    "Carga concluida, mas nao foi possivel gravar as metricas do painel. "
                    f"Execute scripts.atualizar_metricas_competencia depois. Erro: {exc}",
                    flush=True,
                )

        print(f"Carga direta concluida. Total inserido: {total}", flush=True)
    except Exception as exc:
        registrar_fim_carga(
            carga_id=carga_id,
            total_registros=total,
            status="ERRO",
            observacao=f"Erro na carga provisoria Macica direta: {exc}",
        )
        raise


if __name__ == "__main__":
    main()
