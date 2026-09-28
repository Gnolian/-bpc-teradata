import os
import time
from datetime import datetime
from pathlib import Path

import teradatasql

from app.config.env_loader import load_app_env

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE_USADO = load_app_env(BASE_DIR)


def str_para_bool(valor: str, padrao: bool = False) -> bool:
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "sim", "yes", "y")


def parse_lista_refs(nome_variavel: str) -> list[int]:
    valor = os.getenv(nome_variavel, "").strip()
    if not valor:
        return []
    return [int(item.strip()) for item in valor.split(",") if item.strip()]


def yyyymm_to_datetime(ref: int) -> datetime:
    return datetime.strptime(str(ref), "%Y%m")


def mes_anterior(ref: int) -> int:
    dt = yyyymm_to_datetime(ref)
    if dt.month == 1:
        return int(f"{dt.year - 1}12")
    return int(f"{dt.year}{dt.month - 1:02d}")


def mes_posterior(ref: int) -> int:
    dt = yyyymm_to_datetime(ref)
    if dt.month == 12:
        return int(f"{dt.year + 1}01")
    return int(f"{dt.year}{dt.month + 1:02d}")


def obter_ref_cadunico(ref_principal: int) -> int:
    excecoes = {
        int(item)
        for item in os.getenv("TD_REF_CADUNICO_MESMO_MES", "202201,202202").split(",")
        if item.strip()
    }
    if ref_principal in excecoes:
        return ref_principal
    return mes_posterior(ref_principal)


def tabela_destino() -> str:
    database = os.getenv("TD_DATABASE", "BASE_EXEMPLO_01")
    tabela = os.getenv("TD_TABLE", "TABELA_EXEMPLO_002")
    return f"{database}.{tabela}"


def caminho_sql_modelo_completo() -> Path:
    caminho_env = os.getenv("TD_REF_SQL_MODELO_COMPLETO", "").strip()
    if caminho_env:
        caminho = Path(caminho_env)
        return caminho if caminho.is_absolute() else BASE_DIR / caminho
    return BASE_DIR / "sql" / "consulta_modelo_referencias.sql"


def get_td_connection():
    host = os.getenv("TD_HOST")
    user = os.getenv("TD_USER")
    password = os.getenv("TD_PASSWORD")
    logmech = os.getenv("TD_LOGMECH", "LDAP")
    if not host:
        raise RuntimeError("TD_HOST não configurado no .env.")
    if not user:
        raise RuntimeError("TD_USER não configurado no .env.")
    if password is None:
        raise RuntimeError("TD_PASSWORD não configurado no .env.")
    return teradatasql.connect(host=host, user=user, password=password, logmech=logmech)


def executar_comando(cursor, comando: str, ignorar_erro: bool = False):
    try:
        cursor.execute(comando)
    except Exception:
        if ignorar_erro:
            return
        raise


def dividir_comandos_sql(sql: str) -> list[str]:
    return [parte.strip() for parte in sql.split(";") if parte.strip()]


def validar_objeto(cursor, database_name: str, table_name: str):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM DBC.TablesV
        WHERE DatabaseName = ?
          AND TableName = ?
        """,
        (database_name, table_name),
    )
    qtd = cursor.fetchone()[0]
    if int(qtd) == 0:
        raise RuntimeError(f"Objeto não encontrado no Teradata: {database_name}.{table_name}")


def validar_objetos_completo(cursor, referencia: int):
    ref_cadunico = obter_ref_cadunico(referencia)
    validar_objeto(cursor, "BASE_EXEMPLO_07", f"TABELA_EXEMPLO_077{referencia}_CADUN_{ref_cadunico}")
    validar_objeto(cursor, f"BASE_EXEMPLO_04{ref_cadunico}", "TABELA_EXEMPLO_072")
    validar_objeto(cursor, f"BASE_EXEMPLO_04{ref_cadunico}", "TABELA_EXEMPLO_071")


def validar_objetos_macica(cursor):
    validar_objeto(cursor, "BASE_EXEMPLO_06", "TABELA_EXEMPLO_073")
    validar_objeto(cursor, "BASE_EXEMPLO_08", "TABELA_EXEMPLO_069")
    validar_objeto(cursor, "BASE_EXEMPLO_02", "TABELA_EXEMPLO_020")


def preparar_sql_completo(sql_modelo: str, referencia: int) -> str:
    ref_anterior = mes_anterior(referencia)
    ref_cadunico = obter_ref_cadunico(referencia)

    sql = sql_modelo
    sql = sql.replace("BASE_EXEMPLO_01.TABELA_EXEMPLO_002", tabela_destino())
    sql = sql.replace("BASE_EXEMPLO_05", f"BASE_EXEMPLO_04{ref_cadunico}")
    sql = sql.replace(
        "BASE_EXEMPLO_07.TABELA_EXEMPLO_079",
        f"BASE_EXEMPLO_07.TABELA_EXEMPLO_077{referencia}_CADUN_{ref_cadunico}",
    )
    sql = sql.replace("202506", str(ref_anterior))
    sql = sql.replace("202507", str(referencia))
    sql = sql.replace("202508", str(ref_cadunico))
    return sql


def comandos_macica_somente(referencia: int) -> list[str]:
    ref_anterior = mes_anterior(referencia)
    destino = tabela_destino()
    return [
        f"""
        CREATE VOLATILE TABLE VT_MACICA_REF AS
        (
            SELECT
                NU_NB,
                NU_CPF_T,
                ID_NIT_T,
                NM_TIT_BENEF_T,
                NM_UF_MUN_T,
                NM_MUN_T,
                DT_NASC_T,
                NM_MAE_T,
                CS_SEXO_T,
                CS_ESPECIE,
                CS_DIAG_1,
                CS_DESPACHO,
                D2_DDB,
                D2_DER,
                D2_DIB,
                NU_MES_REF
            FROM BASE_EXEMPLO_06.TABELA_EXEMPLO_073
            WHERE CS_SIT_BENEF = 0
              AND CS_ESPECIE IN (11,12,18,30,40,60,87,88)
              AND CS_PA <> 3
              AND NU_MES_REF = {referencia}
            QUALIFY ROW_NUMBER() OVER (PARTITION BY NU_NB ORDER BY NU_NB) = 1
        ) WITH DATA
        PRIMARY INDEX (NU_NB)
        ON COMMIT PRESERVE ROWS
        """,
        f"""
        CREATE VOLATILE TABLE VT_MACICA_ANTERIOR AS
        (
            SELECT DISTINCT ANT.NU_NB
            FROM BASE_EXEMPLO_06.TABELA_EXEMPLO_073 ANT
            INNER JOIN VT_MACICA_REF ATUAL
                ON ATUAL.NU_NB = ANT.NU_NB
            WHERE ANT.CS_SIT_BENEF = 0
              AND ANT.CS_ESPECIE IN (11,12,18,30,40,60,87,88)
              AND ANT.CS_PA <> 3
              AND ANT.NU_MES_REF = {ref_anterior}
        ) WITH DATA
        PRIMARY INDEX (NU_NB)
        ON COMMIT PRESERVE ROWS
        """,
        """
        CREATE VOLATILE TABLE VT_CAMPANHA AS
        (
            SELECT NUMERO_BENEFICIO, CAMPANHA
            FROM
            (
                SELECT
                    NUMERO_BENEFICIO,
                    CAMPANHA,
                    ROW_NUMBER() OVER
                    (
                        PARTITION BY NUMERO_BENEFICIO
                        ORDER BY CAMPANHA
                    ) AS RN
                FROM BASE_EXEMPLO_02.TABELA_EXEMPLO_020 R
                INNER JOIN VT_MACICA_REF A
                    ON A.NU_NB = R.NUMERO_BENEFICIO
            ) X
            WHERE RN = 1
        ) WITH DATA
        PRIMARY INDEX (NUMERO_BENEFICIO)
        ON COMMIT PRESERVE ROWS
        """,
        f"""
        INSERT INTO {destino}
        (
            TIPO_REGISTRO,
            NU_NB,
            CO_FAMILIAR_FAM,
            NU_CPF_T,
            NUM_CPF_PESSOA,
            CO_CHV_NATURAL_PESSOA,
            NU_NIS_T,
            NUM_NIS_PESSOA_ATUAL,
            NM_TIT_BENEF_T,
            NOM_PESSOA,
            DESC_PARENTESCO,
            FLAG_CADUNICO,
            FLAG_REF_MACICA_ANTERIOR,
            UF_MACICA,
            MUNICIPIO_MACICA,
            UF_CAD,
            MUNICIPIO_CAD,
            UF_AG_PGD,
            MUNICIPIO_AG_PGD,
            DT_NASC_T,
            DTA_NASC_PESSOA,
            IDADE_T,
            IDADE_PESSOA,
            NM_MAE_T,
            NOM_COMPLETO_MAE_PESSOA,
            GENERO,
            RACA_COR,
            IND_DORMIR_RUA_MEMB,
            FAMILIA_INDIGENA,
            FAMILIA_QUILOMBOLA,
            CS_ESPECIE,
            CID,
            DESCRICAO_CID,
            TIPO_DESPACHO,
            DT_DESPACHO,
            DT_ENTRADA_REQUERIMENTO,
            DT_INICIO_BENEFICIO,
            SITUACAO_CAD_UNICO,
            PARTICIPACAO_CAMPANHA,
            DTA_ATUAL_MEMB,
            NU_MES_REF
        )
        SELECT
            'NAO_CADASTRADO' AS TIPO_REGISTRO,
            A.NU_NB,
            NULL AS CO_FAMILIAR_FAM,
            A.NU_CPF_T,
            NULL AS NUM_CPF_PESSOA,
            NULL AS CO_CHV_NATURAL_PESSOA,
            A.ID_NIT_T AS NU_NIS_T,
            NULL AS NUM_NIS_PESSOA_ATUAL,
            A.NM_TIT_BENEF_T,
            NULL AS NOM_PESSOA,
            NULL AS DESC_PARENTESCO,
            'PENDENTE_CADUNICO' AS FLAG_CADUNICO,
            CASE WHEN M_ANT.NU_NB IS NOT NULL THEN '1' ELSE '0' END AS FLAG_REF_MACICA_ANTERIOR,
            A.NM_UF_MUN_T AS UF_MACICA,
            A.NM_MUN_T AS MUNICIPIO_MACICA,
            NULL AS UF_CAD,
            NULL AS MUNICIPIO_CAD,
            NULL AS UF_AG_PGD,
            NULL AS MUNICIPIO_AG_PGD,
            A.DT_NASC_T,
            NULL AS DTA_NASC_PESSOA,
            CAST
            (
                MONTHS_BETWEEN
                (
                    LAST_DAY(CAST(CAST(A.NU_MES_REF AS CHAR(6)) || '01' AS DATE FORMAT 'YYYYMMDD')),
                    A.DT_NASC_T
                ) / 12 AS INTEGER
            ) AS IDADE_T,
            NULL AS IDADE_PESSOA,
            A.NM_MAE_T,
            NULL AS NOM_COMPLETO_MAE_PESSOA,
            CASE
                WHEN A.CS_SEXO_T = 1 THEN 'MASCULINO'
                WHEN A.CS_SEXO_T = 3 THEN 'FEMININO'
                ELSE 'NAO INFORMADO'
            END AS GENERO,
            'NAO INFORMADO' AS RACA_COR,
            NULL AS IND_DORMIR_RUA_MEMB,
            NULL AS FAMILIA_INDIGENA,
            NULL AS FAMILIA_QUILOMBOLA,
            A.CS_ESPECIE,
            A.CS_DIAG_1 AS CID,
            CASE
                WHEN D.DS_DESCRICAO IS NOT NULL THEN D.DS_DESCRICAO
                WHEN D.DS_DESCRICAO IS NULL AND A.CS_ESPECIE <> 87 THEN 'NAO SE APLICA'
                ELSE 'NAO ENCONTRADO'
            END AS DESCRICAO_CID,
            CASE
                WHEN A.CS_DESPACHO <> 4 THEN 'ADMINISTRATIVA'
                WHEN A.CS_DESPACHO = 4 THEN 'JUDICIAL'
            END AS TIPO_DESPACHO,
            A.D2_DDB AS DT_DESPACHO,
            A.D2_DER AS DT_ENTRADA_REQUERIMENTO,
            A.D2_DIB AS DT_INICIO_BENEFICIO,
            'MACICA_PROVISORIA_CADUNICO_PENDENTE' AS SITUACAO_CAD_UNICO,
            CASE WHEN F.CAMPANHA IS NOT NULL THEN F.CAMPANHA ELSE 'NAO' END AS PARTICIPACAO_CAMPANHA,
            NULL AS DTA_ATUAL_MEMB,
            {referencia} AS NU_MES_REF
        FROM VT_MACICA_REF A
        LEFT JOIN VT_MACICA_ANTERIOR M_ANT
            ON A.NU_NB = M_ANT.NU_NB
        LEFT JOIN
        (
            SELECT
                CO_CID,
                MAX(DS_DESCRICAO) AS DS_DESCRICAO
            FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_069
            GROUP BY 1
        ) D
            ON A.CS_DIAG_1 = D.CO_CID
        LEFT JOIN VT_CAMPANHA F
            ON A.NU_NB = F.NUMERO_BENEFICIO
        """,
    ]


def apagar_referencia_destino(cursor, referencia: int):
    print(f"Apagando registros existentes da referência {referencia} em {tabela_destino()}...")
    cursor.execute(
        f"""
        DELETE FROM {tabela_destino()}
        WHERE NU_MES_REF = ?
        """,
        (referencia,),
    )


def validar_resultado(cursor, referencia: int):
    cursor.execute(
        f"""
        SELECT TIPO_REGISTRO, COUNT(*) AS QTD
        FROM {tabela_destino()}
        WHERE NU_MES_REF = ?
        GROUP BY 1
        ORDER BY 1
        """,
        (referencia,),
    )
    rows = cursor.fetchall()
    print(f"Resultado carregado para {referencia}:")
    if not rows:
        print("  Nenhum registro encontrado após a carga.")
        return
    for row in rows:
        print(f"  {row[0]}: {row[1]}")


def executar_referencia_completa(cursor, referencia: int):
    ref_cadunico = obter_ref_cadunico(referencia)
    print("\n" + "=" * 80)
    print(f"Processando referência completa: {referencia}")
    print(f"View esperada: BASE_EXEMPLO_07.TABELA_EXEMPLO_077{referencia}_CADUN_{ref_cadunico}")
    print("=" * 80)

    validar_objetos_completo(cursor, referencia)
    executar_comando(cursor, "DROP TABLE VT_CAMPANHA", ignorar_erro=True)
    executar_comando(cursor, "DROP TABLE VT_BEN_CAD", ignorar_erro=True)

    if str_para_bool(os.getenv("TD_REF_APAGAR_ANTES_DE_INSERIR", "false")):
        apagar_referencia_destino(cursor, referencia)

    sql_path = caminho_sql_modelo_completo()
    if not sql_path.exists():
        raise FileNotFoundError(
            f"SQL modelo da carga completa não encontrado: {sql_path}. "
            "Defina TD_REF_SQL_MODELO_COMPLETO no .env."
        )
    sql_modelo = sql_path.read_text(encoding="utf-8")
    comandos = dividir_comandos_sql(preparar_sql_completo(sql_modelo, referencia))
    print(f"Total de comandos SQL completos: {len(comandos)}")
    for idx, comando in enumerate(comandos, start=1):
        print(f"  Executando comando completo {idx}/{len(comandos)}...")
        executar_comando(cursor, comando)

    validar_resultado(cursor, referencia)


def executar_referencia_macica(cursor, referencia: int):
    print("\n" + "=" * 80)
    print(f"Processando referência Maciça somente: {referencia}")
    print("Uso: atualização provisória da Consulta Pessoa enquanto a view CadÚnico não sai.")
    print("=" * 80)

    validar_objetos_macica(cursor)
    executar_comando(cursor, "DROP TABLE VT_MACICA_REF", ignorar_erro=True)
    executar_comando(cursor, "DROP TABLE VT_MACICA_ANTERIOR", ignorar_erro=True)
    executar_comando(cursor, "DROP TABLE VT_CAMPANHA", ignorar_erro=True)

    if str_para_bool(os.getenv("TD_REF_APAGAR_ANTES_DE_INSERIR", "false")):
        apagar_referencia_destino(cursor, referencia)

    comandos = comandos_macica_somente(referencia)
    print(f"Total de comandos SQL Maciça: {len(comandos)}")
    for idx, comando in enumerate(comandos, start=1):
        print(f"  Executando comando Maciça {idx}/{len(comandos)}...")
        executar_comando(cursor, comando)

    validar_resultado(cursor, referencia)


def processar(cursor, modo: str, referencia: int):
    inicio = time.time()
    if modo == "completa":
        executar_referencia_completa(cursor, referencia)
    elif modo == "macica":
        executar_referencia_macica(cursor, referencia)
    else:
        raise ValueError(f"Modo de carga desconhecido: {modo}")
    duracao = (time.time() - inicio) / 60
    print(f"Tempo da referência {referencia}: {duracao:.2f} minutos")


def main():
    if ENV_FILE_USADO:
        print(f"Arquivo de ambiente complementar: {ENV_FILE_USADO}")

    refs_completas = parse_lista_refs("TD_REF_COMPLETAS")
    refs_macica = parse_lista_refs("TD_REF_MACICA_SOMENTE")
    parar_no_erro = str_para_bool(os.getenv("TD_REF_PARAR_NO_PRIMEIRO_ERRO", "true"), True)

    if not refs_completas and not refs_macica:
        raise RuntimeError(
            "Nenhuma referência configurada. Use TD_REF_COMPLETAS e/ou TD_REF_MACICA_SOMENTE no .env."
        )

    print(f"Destino Teradata: {tabela_destino()}")
    print(f"Referências completas: {refs_completas}")
    print(f"Referências Maciça somente: {refs_macica}")

    conexao = get_td_connection()
    try:
        cursor = conexao.cursor()
        tarefas = [("completa", ref) for ref in refs_completas]
        tarefas.extend(("macica", ref) for ref in refs_macica)

        for modo, referencia in tarefas:
            try:
                processar(cursor, modo, referencia)
                conexao.commit()
                print(f"Commit realizado para {referencia} ({modo}).")
            except Exception as exc:
                conexao.rollback()
                print(f"Erro ao processar {referencia} ({modo}): {exc}")
                print("Rollback realizado para essa referência.")
                if parar_no_erro:
                    raise
    finally:
        conexao.close()
        print("Conexão Teradata encerrada.")


if __name__ == "__main__":
    main()
