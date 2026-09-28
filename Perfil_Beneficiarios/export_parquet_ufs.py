from pathlib import Path
from datetime import datetime
import json
import math
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import teradatasql

from src.config import (
    CHUNK_SIZE,
    OUTPUT_DIR,
    METADATA_DIR,
    FOLHA_DIR,
    CADASTRO_DIR,
    REVISAO_DIR,
    MAPA_DIR,
    FULL_TABLE_FOLHA,
    FULL_TABLE_CADASTRO,
    FULL_TABLE_REVISAO,
    FULL_TABLE_MAPA_UF,
    FULL_TABLE_MAPA_MUNICIPIO,
    FOLHA_PARQUET_PATH,
    CADASTRO_PARQUET_PATH,
    REVISAO_PARQUET_PATH,
    MAPA_UF_PARQUET_PATH,
    MAPA_MUNICIPIO_PARQUET_PATH,
    FOLHA_METADATA_PATH,
    CADASTRO_METADATA_PATH,
    REVISAO_METADATA_PATH,
    MAPA_UF_METADATA_PATH,
    MAPA_MUNICIPIO_METADATA_PATH,
    UF_ORDER,
    PARTITIONED_UFS,
    UF_PARTITION_ROW_THRESHOLD,
)
from src.database import get_connection


# =========================================================
# SCHEMAS
# =========================================================
ARROW_SCHEMA_FOLHA = pa.schema([
    ("NU_NB", pa.string()),
    ("NU_CPF", pa.string()),
    ("ESPECIE_CODIGO", pa.float64()),
    ("GRUPO_BENEFICIO", pa.string()),
    ("TIPO_BENEFICIO", pa.string()),
    ("TIPO_DESPACHO", pa.string()),
    ("INSCRITO_CADUNICO", pa.string()),
    ("SEXO", pa.string()),
    ("UF", pa.string()),
    ("MUNICIPIO_IBGE", pa.string()),
    ("IDADE_ANOS", pa.float64()),
    ("FAIXA_ETARIA", pa.string()),
])

ARROW_SCHEMA_CADASTRO = pa.schema([
    ("NU_NB", pa.string()),
    ("NU_CPF", pa.string()),
    ("CS_ESPECIE", pa.float64()),
    ("CO_NB", pa.string()),
    ("SG_UF_APP", pa.string()),
    ("COD_SABE_LER_ESCREVER_MEMB", pa.float64()),
    ("IND_FREQUENTA_ESCOLA_MEMB", pa.float64()),
    ("COD_CURSO_FREQUENTA_MEMB", pa.float64()),
    ("COD_ANO_SERIE_FREQUENTA_MEMB", pa.float64()),
    ("COD_PARENTESCO_RF_PESSOA", pa.float64()),
    ("QTDE_PESSOAS", pa.float64()),
    ("QTD_COMODOS_DOMIC_FAM", pa.float64()),
    ("COD_MATERIAL_PISO_FAM", pa.float64()),
    ("COD_MATERIAL_DOMIC_FAM", pa.float64()),
    ("COD_AGUA_CANALIZADA_FAM", pa.float64()),
    ("COD_CALCAMENTO_DOMIC_FAM", pa.float64()),
    ("COD_FAMILIA_INDIGENA_FAM", pa.float64()),
    ("IND_FAMILIA_QUILOMBOLA_FAM", pa.float64()),
    ("IND_PARC_FAM", pa.float64()),
    ("IND_DORMIR_RUA_MEMB", pa.float64()),
    ("COD_RACA_COR_PESSOA", pa.float64()),
])

ARROW_SCHEMA_REVISAO = pa.schema([
    ("GRUPO_BENEFICIO", pa.string()),
    ("TIPO_BENEFICIO", pa.string()),
    ("UF", pa.string()),
    ("MUNICIPIO_IBGE", pa.string()),
    ("CAMPANHA", pa.string()),
    ("SITUACAO_CADASTRAL_CAD", pa.string()),
    ("QTD_BENEFICIOS", pa.float64()),
])

ARROW_SCHEMA_MAPA_UF = pa.schema([
    ("GRUPO_BENEFICIO", pa.string()),
    ("TIPO_BENEFICIO", pa.string()),
    ("TIPO_DESPACHO", pa.string()),
    ("SEXO", pa.string()),
    ("UF", pa.string()),
    ("QTD_BENEFICIOS", pa.float64()),
])

ARROW_SCHEMA_MAPA_MUNICIPIO = pa.schema([
    ("GRUPO_BENEFICIO", pa.string()),
    ("TIPO_BENEFICIO", pa.string()),
    ("SEXO", pa.string()),
    ("UF", pa.string()),
    ("MUNICIPIO_IBGE", pa.string()),
    ("QTD_BENEFICIOS", pa.float64()),
])


# =========================================================
# COLUNAS
# =========================================================
FOLHA_TEXT_COLUMNS = [
    "NU_NB", "NU_CPF", "GRUPO_BENEFICIO", "TIPO_BENEFICIO",
    "TIPO_DESPACHO", "INSCRITO_CADUNICO", "SEXO", "UF",
    "MUNICIPIO_IBGE", "FAIXA_ETARIA",
]
FOLHA_NUMERIC_COLUMNS = ["ESPECIE_CODIGO", "IDADE_ANOS"]

CADASTRO_TEXT_COLUMNS = ["NU_NB", "NU_CPF", "CO_NB", "SG_UF_APP"]
CADASTRO_NUMERIC_COLUMNS = [
    "CS_ESPECIE", "COD_SABE_LER_ESCREVER_MEMB", "IND_FREQUENTA_ESCOLA_MEMB",
    "COD_CURSO_FREQUENTA_MEMB", "COD_ANO_SERIE_FREQUENTA_MEMB",
    "COD_PARENTESCO_RF_PESSOA", "QTDE_PESSOAS", "QTD_COMODOS_DOMIC_FAM",
    "COD_MATERIAL_PISO_FAM", "COD_MATERIAL_DOMIC_FAM",
    "COD_AGUA_CANALIZADA_FAM", "COD_CALCAMENTO_DOMIC_FAM",
    "COD_FAMILIA_INDIGENA_FAM", "IND_FAMILIA_QUILOMBOLA_FAM",
    "IND_PARC_FAM", "IND_DORMIR_RUA_MEMB", "COD_RACA_COR_PESSOA",
]

REVISAO_TEXT_COLUMNS = [
    "GRUPO_BENEFICIO", "TIPO_BENEFICIO", "UF",
    "MUNICIPIO_IBGE", "CAMPANHA", "SITUACAO_CADASTRAL_CAD"
]
REVISAO_NUMERIC_COLUMNS = ["QTD_BENEFICIOS"]

MAPA_UF_TEXT_COLUMNS = ["GRUPO_BENEFICIO", "TIPO_BENEFICIO", "TIPO_DESPACHO", "SEXO", "UF"]
MAPA_UF_NUMERIC_COLUMNS = ["QTD_BENEFICIOS"]

MAPA_MUNICIPIO_TEXT_COLUMNS = ["GRUPO_BENEFICIO", "TIPO_BENEFICIO", "SEXO", "UF", "MUNICIPIO_IBGE"]
MAPA_MUNICIPIO_NUMERIC_COLUMNS = ["QTD_BENEFICIOS"]


# =========================================================
# HELPERS
# =========================================================
def ensure_dirs():
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(METADATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(FOLHA_DIR).mkdir(parents=True, exist_ok=True)
    Path(CADASTRO_DIR).mkdir(parents=True, exist_ok=True)
    Path(REVISAO_DIR).mkdir(parents=True, exist_ok=True)
    Path(MAPA_DIR).mkdir(parents=True, exist_ok=True)


def format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes}min {remaining_seconds:.1f}s"


def sanitize_name(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(" ", "_").strip()


def write_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def build_metadata(
    tipo_base: str,
    parquet_path: Path,
    total_rows: int,
    total_chunks: int,
    elapsed_time: float,
    extra: dict | None = None,
) -> dict:
    metadata = {
        "tipo_base": tipo_base,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows": total_rows,
        "total_chunks": total_chunks,
        "chunk_size": CHUNK_SIZE,
        "elapsed_time_seconds": round(elapsed_time, 2),
        "elapsed_time_human": format_seconds(elapsed_time),
        "parquet_path": str(parquet_path.resolve()),
        "file_size_mb": round(parquet_path.stat().st_size / (1024 * 1024), 2) if parquet_path.exists() else None,
    }
    if extra:
        metadata.update(extra)
    return metadata


def enforce_dtypes(df: pd.DataFrame, text_cols: list[str], numeric_cols: list[str]) -> pd.DataFrame:
    df = df.copy()

    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype("string")

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    return df


def get_uf_parquet_path(base_name: str, uf: str) -> Path:
    safe = sanitize_name(uf)
    if base_name == "folha":
        return Path(FOLHA_DIR) / f"folha_{safe}.parquet"
    if base_name == "cadastro":
        return Path(CADASTRO_DIR) / f"cadastro_{safe}.parquet"
    raise ValueError(f"Base inválida para UF: {base_name}")


def get_uf_metadata_path(base_name: str, uf: str) -> Path:
    safe = sanitize_name(uf)
    return Path(METADATA_DIR) / f"{base_name}_{safe}.json"


def get_uf_part_parquet_path(base_name: str, uf: str, part_index: int, total_parts: int) -> Path:
    safe = sanitize_name(uf)
    folder = Path(FOLHA_DIR) if base_name == "folha" else Path(CADASTRO_DIR)
    return folder / f"{base_name}_{safe}_part_{part_index+1}_de_{total_parts}.parquet"


def get_uf_part_metadata_path(base_name: str, uf: str, part_index: int, total_parts: int) -> Path:
    safe = sanitize_name(uf)
    return Path(METADATA_DIR) / f"{base_name}_{safe}_part_{part_index+1}_de_{total_parts}.json"


def file_done(parquet_path: Path, metadata_path: Path) -> bool:
    return parquet_path.exists() and parquet_path.stat().st_size > 0 and metadata_path.exists()


def remove_if_exists(path: Path):
    if path.exists():
        path.unlink()


# =========================================================
# QUERIES
# =========================================================
def build_query_by_uf(
    table_name: str,
    uf: str,
    uf_column: str,
    sample_limit: int | None = None
) -> str:
    top_clause = f"TOP {sample_limit} " if sample_limit and sample_limit > 0 else ""
    uf_filter = f"{uf_column} = 'NAO INFORMADA'" if uf == "NAO INFORMADA" else f"{uf_column} = '{uf}'"

    return f"""
    SELECT {top_clause} *
    FROM {table_name}
    WHERE {uf_filter}
    """


def build_query_by_uf_part(
    table_name: str,
    uf: str,
    uf_column: str,
    part_index: int,
    total_parts: int,
    sample_limit: int | None = None,
) -> str:
    top_clause = f"TOP {sample_limit} " if sample_limit and sample_limit > 0 else ""
    uf_filter = f"{uf_column} = 'NAO INFORMADA'" if uf == "NAO INFORMADA" else f"{uf_column} = '{uf}'"

    return f"""
    SELECT {top_clause} *
    FROM {table_name}
    WHERE {uf_filter}
      AND MOD(CAST(NU_NB AS BIGINT), {total_parts}) = {part_index}
    """


def build_query_full(table_name: str, sample_limit: int | None = None) -> str:
    top_clause = f"TOP {sample_limit} " if sample_limit and sample_limit > 0 else ""
    return f"""
    SELECT {top_clause} *
    FROM {table_name}
    """


def build_count_uf_query(table_name: str, uf: str, uf_column: str) -> str:
    uf_filter = f"{uf_column} = 'NAO INFORMADA'" if uf == "NAO INFORMADA" else f"{uf_column} = '{uf}'"
    return f"""
    SELECT COUNT(*) AS TOTAL_ROWS
    FROM {table_name}
    WHERE {uf_filter}
    """


# =========================================================
# LEITURA / ESCRITA EM CHUNK
# =========================================================
def export_query_to_parquet(
    query: str,
    parquet_path: Path,
    schema: pa.Schema,
    text_columns: list[str],
    numeric_columns: list[str],
    metadata_path: Path | None = None,
    metadata_type: str | None = None,
    metadata_extra: dict | None = None,
) -> tuple[bool, int]:
    remove_if_exists(parquet_path)
    if metadata_path:
        remove_if_exists(metadata_path)

    total_rows = 0
    total_chunks = 0
    writer = None
    start_total = time.perf_counter()

    try:
        conn = get_connection()
        try:
            for i, chunk_df in enumerate(pd.read_sql(query, conn, chunksize=CHUNK_SIZE), start=1):
                if chunk_df.empty:
                    continue

                chunk_df = enforce_dtypes(chunk_df, text_columns, numeric_columns)
                chunk_df = chunk_df[[field.name for field in schema]]

                table = pa.Table.from_pandas(
                    chunk_df,
                    schema=schema,
                    preserve_index=False,
                )

                if writer is None:
                    writer = pq.ParquetWriter(
                        parquet_path,
                        schema,
                        compression="snappy",
                    )

                writer.write_table(table)

                total_rows += len(chunk_df)
                total_chunks += 1

                print(
                    f"[{parquet_path.name}] chunk {i} carregado com {len(chunk_df):,} linhas | "
                    f"total acumulado: {total_rows:,}".replace(",", ".")
                )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    except teradatasql.OperationalError as e:
        if writer is not None:
            writer.close()
        if parquet_path.exists() and parquet_path.stat().st_size == 0:
            remove_if_exists(parquet_path)
        print(f"[ERRO] Falha por queda de conexão: {e}")
        return False, total_rows

    except Exception as e:
        if writer is not None:
            writer.close()
        remove_if_exists(parquet_path)
        if metadata_path:
            remove_if_exists(metadata_path)
        print(f"[ERRO] Falha na exportação: {e}")
        return False, total_rows

    finally:
        if writer is not None:
            writer.close()

    elapsed_total = time.perf_counter() - start_total

    if metadata_path and metadata_type:
        metadata = build_metadata(
            tipo_base=metadata_type,
            parquet_path=parquet_path,
            total_rows=total_rows,
            total_chunks=total_chunks,
            elapsed_time=elapsed_total,
            extra=metadata_extra or {},
        )
        write_json(metadata_path, metadata)

    return True, total_rows


def export_with_retry(
    query: str,
    parquet_path: Path,
    schema: pa.Schema,
    text_columns: list[str],
    numeric_columns: list[str],
    metadata_path: Path | None = None,
    metadata_type: str | None = None,
    metadata_extra: dict | None = None,
    max_retries: int = 3,
    retry_wait_seconds: int = 5,
) -> tuple[bool, int]:
    last_rows = 0

    for attempt in range(1, max_retries + 1):
        print("")
        print(f"[TENTATIVA] {parquet_path.name} | tentativa {attempt}/{max_retries}")

        ok, rows = export_query_to_parquet(
            query=query,
            parquet_path=parquet_path,
            schema=schema,
            text_columns=text_columns,
            numeric_columns=numeric_columns,
            metadata_path=metadata_path,
            metadata_type=metadata_type,
            metadata_extra=metadata_extra,
        )
        last_rows = rows

        if ok:
            print(f"[OK] {parquet_path.name} concluído com sucesso na tentativa {attempt}.")
            return True, rows

        if attempt < max_retries:
            print(f"[RETRY] Nova tentativa em {retry_wait_seconds}s...")
            time.sleep(retry_wait_seconds)

    print(f"[ERRO FINAL] {parquet_path.name} falhou após {max_retries} tentativas.")
    return False, last_rows


# =========================================================
# CONTAGEM POR UF PARA DECIDIR PARTIÇÃO
# =========================================================
def get_uf_row_count(table_name: str, uf: str, uf_column: str) -> int:
    query = build_count_uf_query(table_name, uf, uf_column)
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn)
        if df.empty:
            return 0
        return int(df.iloc[0]["TOTAL_ROWS"])
    finally:
        try:
            conn.close()
        except Exception:
            pass

def get_total_parts_for_uf(base_name: str, table_name: str, uf: str) -> int:
    if uf in PARTITIONED_UFS:
        return PARTITIONED_UFS[uf]

    uf_column = get_uf_column_name(base_name)
    total_rows = get_uf_row_count(table_name, uf, uf_column)

    if total_rows <= UF_PARTITION_ROW_THRESHOLD:
        return 1

    return max(2, math.ceil(total_rows / UF_PARTITION_ROW_THRESHOLD))


# =========================================================
# EXPORTAÇÃO POR UF
# =========================================================
def export_base_by_uf(
    base_name: str,
    table_name: str,
    schema: pa.Schema,
    text_columns: list[str],
    numeric_columns: list[str],
    final_parquet_path: Path,
    final_metadata_path: Path,
    sample_limit: int | None = None,
    max_retries: int = 3,
    retry_wait_seconds: int = 5,
    only_missing: bool = True,
) -> tuple[int, int]:
    total_ok = 0
    total_failed = 0

    print("")
    print("=" * 100)
    print(f"EXPORTAÇÃO DA BASE {base_name.upper()} POR UF")
    print("=" * 100)

    uf_column = get_uf_column_name(base_name)

    for uf in UF_ORDER:
        total_parts = get_total_parts_for_uf(base_name, table_name, uf)

        if total_parts == 1:
            parquet_path = get_uf_parquet_path(base_name, uf)
            metadata_path = get_uf_metadata_path(base_name, uf)

            if only_missing and file_done(parquet_path, metadata_path):
                print(f"[SKIP] {base_name.upper()} UF {uf} já exportada.")
                total_ok += 1
                continue

            query = build_query_by_uf(
                table_name=table_name,
                uf=uf,
                uf_column=uf_column,
                sample_limit=sample_limit,
            )

            ok, _ = export_with_retry(
                query=query,
                parquet_path=parquet_path,
                schema=schema,
                text_columns=text_columns,
                numeric_columns=numeric_columns,
                metadata_path=metadata_path,
                metadata_type=base_name,
                metadata_extra={"uf": uf},
                max_retries=max_retries,
                retry_wait_seconds=retry_wait_seconds,
            )

            if ok:
                total_ok += 1
            else:
                total_failed += 1

        else:
            print("")
            print(f"[UF PARTICIONADA] {base_name.upper()} {uf} em {total_parts} partes")

            parts_ok = 0

            for part_index in range(total_parts):
                parquet_path = get_uf_part_parquet_path(base_name, uf, part_index, total_parts)
                metadata_path = get_uf_part_metadata_path(base_name, uf, part_index, total_parts)

                if only_missing and file_done(parquet_path, metadata_path):
                    print(f"[SKIP] {base_name.upper()} {uf} parte {part_index + 1}/{total_parts} já exportada.")
                    parts_ok += 1
                    continue

                query = build_query_by_uf_part(
                    table_name=table_name,
                    uf=uf,
                    uf_column=uf_column,
                    part_index=part_index,
                    total_parts=total_parts,
                    sample_limit=sample_limit,
                )

                ok, _ = export_with_retry(
                    query=query,
                    parquet_path=parquet_path,
                    schema=schema,
                    text_columns=text_columns,
                    numeric_columns=numeric_columns,
                    metadata_path=metadata_path,
                    metadata_type=base_name,
                    metadata_extra={
                        "uf": uf,
                        "part_index": part_index,
                        "part_number": part_index + 1,
                        "total_parts": total_parts,
                    },
                    max_retries=max_retries,
                    retry_wait_seconds=retry_wait_seconds,
                )

                if ok:
                    parts_ok += 1

            if parts_ok == total_parts:
                consolidate_uf_parts(base_name, uf, total_parts, schema)
                total_ok += 1
            else:
                print(f"[ERRO] {base_name.upper()} {uf} não foi consolidada porque faltou parte.")
                total_failed += 1

    total_rows = consolidate_ufs(base_name, schema, final_parquet_path)
    metadata = build_metadata(
        tipo_base=base_name,
        parquet_path=final_parquet_path,
        total_rows=total_rows,
        total_chunks=0,
        elapsed_time=0,
        extra={"ufs_processadas": [uf for uf in UF_ORDER if get_uf_parquet_path(base_name, uf).exists()]},
    )
    write_json(final_metadata_path, metadata)

    return total_ok, total_failed


def consolidate_uf_parts(base_name: str, uf: str, total_parts: int, schema: pa.Schema) -> int:
    output_path = get_uf_parquet_path(base_name, uf)
    metadata_path = get_uf_metadata_path(base_name, uf)

    remove_if_exists(output_path)
    remove_if_exists(metadata_path)

    writer = None
    total_rows = 0

    try:
        for part_index in range(total_parts):
            part_path = get_uf_part_parquet_path(base_name, uf, part_index, total_parts)

            if not part_path.exists():
                raise FileNotFoundError(f"Parte não encontrada: {part_path}")

            df = pd.read_parquet(part_path)
            if df.empty:
                continue

            df = df[[field.name for field in schema]]
            table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

            if writer is None:
                writer = pq.ParquetWriter(output_path, schema, compression="snappy")

            writer.write_table(table)
            total_rows += len(df)

    finally:
        if writer is not None:
            writer.close()

    metadata = build_metadata(
        tipo_base=base_name,
        parquet_path=output_path,
        total_rows=total_rows,
        total_chunks=total_parts,
        elapsed_time=0,
        extra={"uf": uf},
    )
    write_json(metadata_path, metadata)

    print(f"[OK] {base_name.upper()} {uf} consolidada: {total_rows:,} registros".replace(",", "."))
    return total_rows


def consolidate_ufs(base_name: str, schema: pa.Schema, output_path: Path) -> int:
    remove_if_exists(output_path)

    uf_files = []
    for uf in UF_ORDER:
        uf_path = get_uf_parquet_path(base_name, uf)
        if uf_path.exists():
            uf_files.append(uf_path)

    if not uf_files:
        raise ValueError(f"Nenhum parquet por UF encontrado para consolidar {base_name}.")

    writer = None
    total_rows = 0

    try:
        for uf_file in uf_files:
            df = pd.read_parquet(uf_file)
            if df.empty:
                continue

            df = df[[field.name for field in schema]]
            table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

            if writer is None:
                writer = pq.ParquetWriter(output_path, schema, compression="snappy")

            writer.write_table(table)
            total_rows += len(df)

    finally:
        if writer is not None:
            writer.close()

    print(f"[OK] {base_name.upper()} full consolidada: {total_rows:,} registros".replace(",", "."))
    print(f"[OK] Parquet salvo em: {output_path.resolve()}")

    return total_rows


# =========================================================
# EXPORTAÇÃO BASES FULL
# =========================================================
def export_full_base(
    base_name: str,
    table_name: str,
    parquet_path: Path,
    metadata_path: Path,
    schema: pa.Schema,
    text_columns: list[str],
    numeric_columns: list[str],
    sample_limit: int | None = None,
    max_retries: int = 3,
    retry_wait_seconds: int = 5,
    only_missing: bool = True,
) -> tuple[bool, int]:
    if only_missing and file_done(parquet_path, metadata_path):
        print(f"[SKIP] {base_name.upper()} já possui parquet e metadata.")
        return True, 0

    query = build_query_full(table_name, sample_limit=sample_limit)

    ok, rows = export_with_retry(
        query=query,
        parquet_path=parquet_path,
        schema=schema,
        text_columns=text_columns,
        numeric_columns=numeric_columns,
        metadata_path=metadata_path,
        metadata_type=base_name,
        metadata_extra={},
        max_retries=max_retries,
        retry_wait_seconds=retry_wait_seconds,
    )
    return ok, rows


# =========================================================
# EXPORTAÇÃO GERAL
# =========================================================
def export_all(
    sample_limit: int | None = None,
    max_retries: int = 3,
    retry_wait_seconds: int = 5,
    only_missing: bool = True,
):
    ensure_dirs()

    total_ok = 0
    total_failed = 0

    print("=" * 100)
    print("EXPORTAÇÃO GERAL INICIADA")
    print("=" * 100)

    # 1) FOLHA por UF
    ok_folha, fail_folha = export_base_by_uf(
        base_name="folha",
        table_name=FULL_TABLE_FOLHA,
        schema=ARROW_SCHEMA_FOLHA,
        text_columns=FOLHA_TEXT_COLUMNS,
        numeric_columns=FOLHA_NUMERIC_COLUMNS,
        final_parquet_path=FOLHA_PARQUET_PATH,
        final_metadata_path=FOLHA_METADATA_PATH,
        sample_limit=sample_limit,
        max_retries=max_retries,
        retry_wait_seconds=retry_wait_seconds,
        only_missing=only_missing,
    )
    total_ok += ok_folha
    total_failed += fail_folha

    # 2) CADASTRO por UF
    ok_cad, fail_cad = export_base_by_uf(
        base_name="cadastro",
        table_name=FULL_TABLE_CADASTRO,
        schema=ARROW_SCHEMA_CADASTRO,
        text_columns=CADASTRO_TEXT_COLUMNS,
        numeric_columns=CADASTRO_NUMERIC_COLUMNS,
        final_parquet_path=CADASTRO_PARQUET_PATH,
        final_metadata_path=CADASTRO_METADATA_PATH,
        sample_limit=sample_limit,
        max_retries=max_retries,
        retry_wait_seconds=retry_wait_seconds,
        only_missing=only_missing,
    )
    total_ok += ok_cad
    total_failed += fail_cad

    # 3) REVISAO full
    ok_rev, _ = export_full_base(
        base_name="revisao_resumo",
        table_name=FULL_TABLE_REVISAO,
        parquet_path=REVISAO_PARQUET_PATH,
        metadata_path=REVISAO_METADATA_PATH,
        schema=ARROW_SCHEMA_REVISAO,
        text_columns=REVISAO_TEXT_COLUMNS,
        numeric_columns=REVISAO_NUMERIC_COLUMNS,
        sample_limit=sample_limit,
        max_retries=max_retries,
        retry_wait_seconds=retry_wait_seconds,
        only_missing=only_missing,
    )
    total_ok += 1 if ok_rev else 0
    total_failed += 0 if ok_rev else 1

    # 4) MAPA UF full
    ok_mapa_uf, _ = export_full_base(
        base_name="mapa_uf",
        table_name=FULL_TABLE_MAPA_UF,
        parquet_path=MAPA_UF_PARQUET_PATH,
        metadata_path=MAPA_UF_METADATA_PATH,
        schema=ARROW_SCHEMA_MAPA_UF,
        text_columns=MAPA_UF_TEXT_COLUMNS,
        numeric_columns=MAPA_UF_NUMERIC_COLUMNS,
        sample_limit=sample_limit,
        max_retries=max_retries,
        retry_wait_seconds=retry_wait_seconds,
        only_missing=only_missing,
    )
    total_ok += 1 if ok_mapa_uf else 0
    total_failed += 0 if ok_mapa_uf else 1

    # 5) MAPA MUNICIPIO full
    ok_mapa_mun, _ = export_full_base(
        base_name="mapa_municipio",
        table_name=FULL_TABLE_MAPA_MUNICIPIO,
        parquet_path=MAPA_MUNICIPIO_PARQUET_PATH,
        metadata_path=MAPA_MUNICIPIO_METADATA_PATH,
        schema=ARROW_SCHEMA_MAPA_MUNICIPIO,
        text_columns=MAPA_MUNICIPIO_TEXT_COLUMNS,
        numeric_columns=MAPA_MUNICIPIO_NUMERIC_COLUMNS,
        sample_limit=sample_limit,
        max_retries=max_retries,
        retry_wait_seconds=retry_wait_seconds,
        only_missing=only_missing,
    )
    total_ok += 1 if ok_mapa_mun else 0
    total_failed += 0 if ok_mapa_mun else 1

    print("")
    print("=" * 100)
    print("RESUMO FINAL")
    print("=" * 100)
    print(f"Execuções concluídas: {total_ok}")
    print(f"Execuções com falha: {total_failed}")
    print("=" * 100)


def main(
    only_missing: bool = True,
    sample_limit: int | None = None,
):
    export_all(
        sample_limit=sample_limit,
        max_retries=3,
        retry_wait_seconds=5,
        only_missing=only_missing,
    )

def get_uf_column_name(base_name: str) -> str:
    if base_name == "folha":
        return "UF"
    if base_name == "cadastro":
        return "SG_UF_APP"
    raise ValueError(f"Base sem coluna de UF mapeada: {base_name}")

if __name__ == "__main__":
    main(only_missing=True, sample_limit=None)