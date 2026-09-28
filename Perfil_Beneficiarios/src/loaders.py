from pathlib import Path
import json
import pandas as pd
import streamlit as st

from src.config import (
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
)


def _read_parquet(path: str | Path, columns=None) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path.resolve()}")
    if path.stat().st_size == 0:
        raise ValueError(f"Arquivo vazio: {path.resolve()}")
    return pd.read_parquet(path, columns=columns)


def _read_metadata(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_folha_data(columns=None) -> pd.DataFrame:
    return _read_parquet(FOLHA_PARQUET_PATH, columns=columns)


@st.cache_data(show_spinner=False)
def load_cadastro_data(columns=None) -> pd.DataFrame:
    return _read_parquet(CADASTRO_PARQUET_PATH, columns=columns)


@st.cache_data(show_spinner=False)
def load_revisao_data(columns=None) -> pd.DataFrame:
    return _read_parquet(REVISAO_PARQUET_PATH, columns=columns)


@st.cache_data(show_spinner=False)
def load_mapa_uf_data(columns=None) -> pd.DataFrame:
    return _read_parquet(MAPA_UF_PARQUET_PATH, columns=columns)


@st.cache_data(show_spinner=False)
def load_mapa_municipio_data(columns=None) -> pd.DataFrame:
    return _read_parquet(MAPA_MUNICIPIO_PARQUET_PATH, columns=columns)


def load_folha_metadata() -> dict:
    return _read_metadata(FOLHA_METADATA_PATH)


def load_cadastro_metadata() -> dict:
    return _read_metadata(CADASTRO_METADATA_PATH)


def load_revisao_metadata() -> dict:
    return _read_metadata(REVISAO_METADATA_PATH)


def load_mapa_uf_metadata() -> dict:
    return _read_metadata(MAPA_UF_METADATA_PATH)


def load_mapa_municipio_metadata() -> dict:
    return _read_metadata(MAPA_MUNICIPIO_METADATA_PATH)