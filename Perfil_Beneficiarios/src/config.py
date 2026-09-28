from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# =========================
# TERADATA
# =========================
TD_HOST = os.getenv("TD_HOST", "")
TD_USER = os.getenv("TD_USER", "")
TD_PASSWORD = os.getenv("TD_PASSWORD", "")
TD_LOGMECH = os.getenv("TD_LOGMECH", "")
TD_DATABASE = os.getenv("TD_DATABASE", "BASE_EXEMPLO_01")

TD_TABLE_FOLHA = os.getenv("TD_TABLE_FOLHA", "TABELA_EXEMPLO_064")
TD_TABLE_CADASTRO = os.getenv("TD_TABLE_CADASTRO", "TABELA_EXEMPLO_063")
TD_TABLE_REVISAO = os.getenv("TD_TABLE_REVISAO", "TABELA_EXEMPLO_067")
TD_TABLE_MAPA_UF = os.getenv("TD_TABLE_MAPA_UF", "TABELA_EXEMPLO_066")
TD_TABLE_MAPA_MUNICIPIO = os.getenv("TD_TABLE_MAPA_MUNICIPIO", "TABELA_EXEMPLO_065")

FULL_TABLE_FOLHA = f"{TD_DATABASE}.{TD_TABLE_FOLHA}"
FULL_TABLE_CADASTRO = f"{TD_DATABASE}.{TD_TABLE_CADASTRO}"
FULL_TABLE_REVISAO = f"{TD_DATABASE}.{TD_TABLE_REVISAO}"
FULL_TABLE_MAPA_UF = f"{TD_DATABASE}.{TD_TABLE_MAPA_UF}"
FULL_TABLE_MAPA_MUNICIPIO = f"{TD_DATABASE}.{TD_TABLE_MAPA_MUNICIPIO}"

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "50000"))

# limite aproximado para dividir UFs grandes
UF_PARTITION_ROW_THRESHOLD = int(os.getenv("UF_PARTITION_ROW_THRESHOLD", "500000"))

# particionamento manual opcional
PARTITIONED_UFS_RAW = os.getenv("PARTITIONED_UFS", "SP:2,BA:2,MG:2")
PARTITIONED_UFS = {}
if PARTITIONED_UFS_RAW.strip():
    for item in PARTITIONED_UFS_RAW.split(","):
        item = item.strip()
        if not item:
            continue
        uf, parts = item.split(":")
        PARTITIONED_UFS[uf.strip()] = int(parts.strip())

# =========================
# DIRETÓRIOS
# =========================
BASE_DIR = Path(".")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "outputs"))

PARQUET_DIR = OUTPUT_DIR / "parquets"
METADATA_DIR = OUTPUT_DIR / "metadata"

FOLHA_DIR = PARQUET_DIR / "folha_ufs"
CADASTRO_DIR = PARQUET_DIR / "cadastro_ufs"
REVISAO_DIR = PARQUET_DIR / "revisao"
MAPA_DIR = PARQUET_DIR / "mapas"

FOLHA_PARQUET_PATH = PARQUET_DIR / "folha_full.parquet"
CADASTRO_PARQUET_PATH = PARQUET_DIR / "cadastro_full.parquet"
REVISAO_PARQUET_PATH = REVISAO_DIR / "revisao_resumo_full.parquet"
MAPA_UF_PARQUET_PATH = MAPA_DIR / "mapa_uf_full.parquet"
MAPA_MUNICIPIO_PARQUET_PATH = MAPA_DIR / "mapa_municipio_full.parquet"

FOLHA_METADATA_PATH = METADATA_DIR / "folha_metadata.json"
CADASTRO_METADATA_PATH = METADATA_DIR / "cadastro_metadata.json"
REVISAO_METADATA_PATH = METADATA_DIR / "revisao_metadata.json"
MAPA_UF_METADATA_PATH = METADATA_DIR / "mapa_uf_metadata.json"
MAPA_MUNICIPIO_METADATA_PATH = METADATA_DIR / "mapa_municipio_metadata.json"

# =========================
# ORDENS
# =========================
UF_ORDER = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO", "NAO INFORMADA"
]