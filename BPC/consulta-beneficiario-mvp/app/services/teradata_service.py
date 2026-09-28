import os
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import teradatasql

from app.config.env_loader import load_app_env

BASE_DIR = Path(__file__).resolve().parents[2]
load_app_env(BASE_DIR)

_CONEXAO_TERADATA_JA_REALIZADA = False


def _conectar_teradata_com_retry():
    global _CONEXAO_TERADATA_JA_REALIZADA

    host = os.getenv("TD_HOST")
    user = os.getenv("TD_USER")
    password = os.getenv("TD_PASSWORD")
    logmech = os.getenv("TD_LOGMECH", "LDAP")

    if not host:
        raise RuntimeError("TD_HOST não carregado do .env")
    if not user:
        raise RuntimeError("TD_USER não carregado do .env")
    if password is None:
        raise RuntimeError("TD_PASSWORD não carregado do .env")

    max_tentativas = max(1, int(os.getenv("TD_AUTH_MAX_RETRIES", "5")))
    espera_base = max(1, int(os.getenv("TD_AUTH_RETRY_BASE_SECONDS", "15")))

    for tentativa in range(1, max_tentativas + 1):
        try:
            conn = teradatasql.connect(
                host=host,
                user=user,
                password=password,
                logmech=logmech,
            )
            _CONEXAO_TERADATA_JA_REALIZADA = True
            return conn
        except Exception as exc:
            auth_8017 = "8017" in str(exc).upper()
            pode_repetir = (
                auth_8017
                and _CONEXAO_TERADATA_JA_REALIZADA
                and tentativa < max_tentativas
            )
            if not pode_repetir:
                raise

            espera = espera_base * tentativa
            print(
                "[RETRY AUTH] Nova sessao LDAP recusada temporariamente pelo "
                f"Teradata. Tentativa {tentativa}/{max_tentativas}; "
                f"nova tentativa em {espera}s...",
                flush=True,
            )
            time.sleep(espera)

    raise RuntimeError("Nao foi possivel abrir uma sessao no Teradata.")


@contextmanager
def get_td_connection():
    conn = _conectar_teradata_com_retry()

    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _get_table_name():
    database = os.getenv("TD_DATABASE", "BASE_EXEMPLO_01")
    table = os.getenv("TD_TABLE", "TABELA_EXEMPLO_002")
    return f"{database}.{table}"


def _retry_config():
    tentativas = int(os.getenv("TD_MAX_RETRIES", "4"))
    espera_base = int(os.getenv("TD_RETRY_BASE_SECONDS", "15"))
    return tentativas, espera_base


def _executar_com_retry(func, descricao: str):
    max_retries, base_wait = _retry_config()
    ultima_excecao = None

    for tentativa in range(1, max_retries + 1):
        try:
            return func()
        except Exception as exc:
            ultima_excecao = exc
            if not erro_retentavel(exc) or tentativa == max_retries:
                print(f"[ERRO DEFINITIVO] {descricao} falhou na tentativa {tentativa}: {exc}", flush=True)
                raise

            espera = base_wait * tentativa
            print(f"[RETRY] {descricao} falhou na tentativa {tentativa}/{max_retries}: {exc}", flush=True)
            print(f"Aguardando {espera}s antes de tentar novamente...", flush=True)
            time.sleep(espera)

    raise ultima_excecao


def erro_retentavel(exc: Exception) -> bool:
    mensagem = str(exc).upper()
    erros_definitivos = (
        "3754",
        "PRECISION ERROR",
        "SYNTAX ERROR",
        "OBJECT DOES NOT EXIST",
    )
    if any(erro in mensagem for erro in erros_definitivos):
        return False

    erros_transitorios = (
        "ABORT SESSION",
        "LOST CONNECTION",
        "FAILURE RECEIVING",
        "FAILURE SENDING",
        "BROKEN PIPE",
        "EOF",
        "NETWORK",
        "SOCKET",
        "TIMED OUT",
        "TIMEOUT",
        "503",
        "3134",
        "CONNECTION RESET",
        "CONNECTION REFUSED",
    )
    return any(erro in mensagem for erro in erros_transitorios)


def iterar_lotes_competencia_tipo(
    competencia: int,
    tipo_registro: str,
    chave_sql: str,
    fetch_size: int,
):
    tabela = _get_table_name()

    sql = f"""
        SELECT *
        FROM {tabela}
        WHERE NU_MES_REF = ?
          AND TIPO_REGISTRO = ?
          AND {chave_sql} IS NOT NULL
    """

    with get_td_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, (competencia, tipo_registro))
        colunas = [desc[0] for desc in cursor.description]

        while True:
            rows = cursor.fetchmany(fetch_size)
            if not rows:
                break
            yield pd.DataFrame(rows, columns=colunas)


def buscar_lote_competencia_tipo_keyset(
    competencia: int,
    tipo_registro: str,
    chave_sql: str,
    fetch_size: int,
    ultima_chave: int | None = None,
) -> tuple[pd.DataFrame, int | None]:
    tabela = _get_table_name()
    limite = max(1, int(fetch_size))
    chave_anterior = -1 if ultima_chave is None else int(ultima_chave)
    usar_cast_chave = str(os.getenv("TD_KEYSET_CAST_CHAVE", "true")).strip().lower() in {
        "1",
        "true",
        "t",
        "sim",
        "yes",
        "y",
    }
    chave_expr = f"CAST({chave_sql} AS BIGINT)" if usar_cast_chave else chave_sql

    sql = f"""
        SELECT TOP {limite} *
        FROM {tabela}
        WHERE NU_MES_REF = ?
          AND TIPO_REGISTRO = ?
          AND {chave_sql} IS NOT NULL
          AND {chave_expr} > ?
        ORDER BY {chave_expr}
    """

    def _run():
        with get_td_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, (competencia, tipo_registro, chave_anterior))
            except Exception as exc:
                mensagem = str(exc).upper()
                if not usar_cast_chave and ("3754" in mensagem or "PRECISION ERROR" in mensagem):
                    raise RuntimeError(
                        "Teradata retornou erro de precisao ao comparar a chave sem CAST. "
                        "Defina TD_KEYSET_CAST_CHAVE=true no .env e execute a carga novamente."
                    ) from exc
                raise
            rows = cursor.fetchall()
            colunas = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(rows, columns=colunas)

            if df.empty or chave_sql not in df.columns:
                return df, None

            chaves = pd.to_numeric(df[chave_sql], errors="coerce")
            maior_chave = chaves.max()
            if pd.isna(maior_chave):
                return df, None

            return df, int(maior_chave)

    return _run()


def contar_registros_competencia_teradata(competencia: int) -> int:
    tabela = _get_table_name()
    sql = f"""
        SELECT COUNT(*) AS TOTAL
        FROM {tabela}
        WHERE NU_MES_REF = ?
    """

    def _run():
        with get_td_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (competencia,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    return _executar_com_retry(_run, f"COUNT da competência {competencia}")

def obter_resumo_competencia_teradata(competencia: int):
    tabela = _get_table_name()

    sql = f"""
        SELECT
            TIPO_REGISTRO,
            COUNT(*) AS TOTAL
        FROM {tabela}
        WHERE NU_MES_REF = ?
          AND TIPO_REGISTRO IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """

    def _run():
        with get_td_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (competencia,))
            rows = cursor.fetchall()

            totais_por_tipo = {
                row[0]: int(row[1])
                for row in rows
                if row and row[0]
            }
            total = sum(totais_por_tipo.values())

            return {
                "total": total,
                "tipos": list(totais_por_tipo.keys()),
                "totais_por_tipo": totais_por_tipo,
            }

    return _executar_com_retry(_run, f"Resumo da competência {competencia}")

def listar_tipos_registro_competencia(competencia: int):
    tabela = _get_table_name()

    sql = f"""
        SELECT TIPO_REGISTRO
        FROM {tabela}
        WHERE NU_MES_REF = ?
          AND TIPO_REGISTRO IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """

    def _run():
        with get_td_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (competencia,))
            rows = cursor.fetchall()
            return [row[0] for row in rows if row[0]]

    return _executar_com_retry(_run, f"Listagem de TIPO_REGISTRO da competência {competencia}")


def contar_registros_competencia_tipo(
    competencia: int,
    tipo_registro: str,
    chave_sql: str,
) -> int:
    tabela = _get_table_name()

    sql = f"""
        SELECT COUNT(*) AS TOTAL
        FROM {tabela}
        WHERE NU_MES_REF = ?
          AND TIPO_REGISTRO = ?
          AND {chave_sql} IS NOT NULL
    """

    def _run():
        with get_td_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (competencia, tipo_registro))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    return _executar_com_retry(
        _run,
        f"COUNT competÃªncia {competencia} tipo {tipo_registro}",
    )


def contar_registros_competencia_tipo_bucket(
    competencia: int,
    tipo_registro: str,
    bucket: int,
    total_buckets: int,
    chave_sql: str
) -> int:
    tabela = _get_table_name()

    sql = f"""
        SELECT COUNT(*) AS TOTAL
        FROM {tabela}
        WHERE NU_MES_REF = ?
          AND TIPO_REGISTRO = ?
          AND {chave_sql} IS NOT NULL
          AND MOD(ABS(CAST({chave_sql} AS BIGINT)), ?) = ?
    """

    def _run():
        with get_td_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (competencia, tipo_registro, total_buckets, bucket))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    return _executar_com_retry(
        _run,
        f"COUNT competência {competencia} tipo {tipo_registro} bucket {bucket}"
    )


def buscar_bucket_competencia_tipo(
    competencia: int,
    tipo_registro: str,
    bucket: int,
    total_buckets: int,
    chave_sql: str
) -> pd.DataFrame:
    tabela = _get_table_name()

    sql = f"""
        SELECT *
        FROM {tabela}
        WHERE NU_MES_REF = ?
          AND TIPO_REGISTRO = ?
          AND {chave_sql} IS NOT NULL
          AND MOD(ABS(CAST({chave_sql} AS BIGINT)), ?) = ?
    """

    def _run():
        with get_td_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (competencia, tipo_registro, total_buckets, bucket))
            rows = cursor.fetchall()
            colunas = [desc[0] for desc in cursor.description]
            return pd.DataFrame(rows, columns=colunas)

    return _executar_com_retry(
        _run,
        f"Busca competência {competencia} tipo {tipo_registro} bucket {bucket}"
    )
