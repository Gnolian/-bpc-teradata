import pandas as pd


# =========================================================
# HELPERS
# =========================================================
def _normalize_text(series: pd.Series, default: str = "NAO INFORMADO") -> pd.Series:
    return (
        series.astype("string")
        .fillna(default)
        .str.strip()
        .replace("", default)
    )


def _ensure_text_column(df: pd.DataFrame, col: str, default: str = "NAO INFORMADO") -> pd.DataFrame:
    if col not in df.columns:
        df[col] = default
    df[col] = _normalize_text(df[col], default=default)
    return df


def _ensure_numeric_column(df: pd.DataFrame, col: str, default=0) -> pd.DataFrame:
    if col not in df.columns:
        df[col] = default
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)
    return df


def _safe_nunique(df: pd.DataFrame, col: str) -> int:
    if col not in df.columns:
        return 0
    return df[col].dropna().astype(str).nunique()


# =========================================================
# PREPARE FOLHA
# =========================================================
def prepare_folha_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    text_cols = [
        "NU_NB", "NU_CPF", "GRUPO_BENEFICIO", "TIPO_BENEFICIO",
        "TIPO_DESPACHO", "INSCRITO_CADUNICO", "SEXO", "UF",
        "MUNICIPIO_IBGE", "FAIXA_ETARIA"
    ]
    num_cols = ["ESPECIE_CODIGO", "IDADE_ANOS"]

    for col in text_cols:
        df = _ensure_text_column(df, col)

    for col in num_cols:
        df = _ensure_numeric_column(df, col)

    return df


# =========================================================
# PREPARE CADASTRO
# =========================================================
def prepare_cadastro_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    text_cols = ["NU_NB", "NU_CPF", "CO_NB", "SG_UF_APP"]
    num_cols = [
        "CS_ESPECIE", "COD_SABE_LER_ESCREVER_MEMB", "IND_FREQUENTA_ESCOLA_MEMB",
        "COD_CURSO_FREQUENTA_MEMB", "COD_ANO_SERIE_FREQUENTA_MEMB",
        "COD_PARENTESCO_RF_PESSOA", "QTDE_PESSOAS", "QTD_COMODOS_DOMIC_FAM",
        "COD_MATERIAL_PISO_FAM", "COD_MATERIAL_DOMIC_FAM",
        "COD_AGUA_CANALIZADA_FAM", "COD_CALCAMENTO_DOMIC_FAM",
        "COD_FAMILIA_INDIGENA_FAM", "IND_FAMILIA_QUILOMBOLA_FAM",
        "IND_PARC_FAM", "IND_DORMIR_RUA_MEMB", "COD_RACA_COR_PESSOA"
    ]

    for col in text_cols:
        df = _ensure_text_column(df, col)

    for col in num_cols:
        df = _ensure_numeric_column(df, col)

    # recodificações amigáveis
    df["ALFABETIZACAO"] = df["COD_SABE_LER_ESCREVER_MEMB"].map({
        1: "SIM",
        2: "NAO",
    }).fillna("NAO INFORMADO")

    df["FREQUENCIA_ESCOLAR"] = df["IND_FREQUENTA_ESCOLA_MEMB"].map({
        1: "SIM, REDE PUBLICA",
        2: "SIM, REDE PARTICULAR",
        3: "NAO, JA FREQUENTOU",
        4: "NUNCA FREQUENTOU",
    }).fillna("NAO INFORMADO")

    df["CURSO_FREQUENTA"] = df["COD_CURSO_FREQUENTA_MEMB"].map({
        1: "CRECHE",
        2: "PRE-ESCOLA",
        3: "CLASSE DE ALFABETIZACAO",
        4: "ENSINO FUNDAMENTAL 1",
        5: "ENSINO FUNDAMENTAL 2",
        6: "ENSINO MEDIO",
        7: "EJA FUNDAMENTAL",
        8: "EJA MEDIO",
        9: "SUPERIOR",
        10: "ESPECIALIZACAO",
        11: "MESTRADO",
        12: "DOUTORADO",
        13: "PRE-VESTIBULAR",
        14: "NAO SERIADO",
    }).fillna("NAO INFORMADO")

    df["ANO_SERIE_FREQUENTA"] = df["COD_ANO_SERIE_FREQUENTA_MEMB"].map({
        1: "PRIMEIRO",
        2: "SEGUNDO",
        3: "TERCEIRO",
        4: "QUARTO",
        5: "QUINTO",
        6: "SEXTO",
        7: "SETIMO",
        8: "OITAVO",
        9: "NONO",
        10: "CURSO NAO SERIADO",
    }).fillna("NAO INFORMADO")

    df["PARENTESCO_RF"] = df["COD_PARENTESCO_RF_PESSOA"].map({
        1: "RESPONSAVEL FAMILIAR",
        2: "CONJUGE/COMPANHEIRO(A)",
        3: "FILHO(A)",
        4: "ENTEADO(A)",
        5: "NETO(A)/BISNETO(A)",
        6: "PAI/MAE",
        7: "SOGRO(A)",
        8: "IRMAO/IRMA",
        9: "GENRO/NORA",
        10: "OUTRO PARENTE",
        11: "NAO PARENTE",
    }).fillna("NAO INFORMADO")

    df["RESPONSAVEL_FAMILIAR"] = df["COD_PARENTESCO_RF_PESSOA"].map({
        1: "SIM",
    }).fillna("NAO")

    df["AGUA_CANALIZADA"] = df["COD_AGUA_CANALIZADA_FAM"].map({
        1: "SIM",
        2: "NAO",
    }).fillna("NAO INFORMADO")

    df["CALCAMENTO"] = df["COD_CALCAMENTO_DOMIC_FAM"].map({
        1: "SIM",
        2: "NAO",
    }).fillna("NAO INFORMADO")

    df["FAMILIA_INDIGENA"] = df["COD_FAMILIA_INDIGENA_FAM"].map({
        1: "SIM",
        2: "NAO",
    }).fillna("NAO INFORMADO")

    df["FAMILIA_QUILOMBOLA"] = df["IND_FAMILIA_QUILOMBOLA_FAM"].map({
        1: "SIM",
        2: "NAO",
    }).fillna("NAO INFORMADO")

    df["DORMIR_RUA"] = df["IND_DORMIR_RUA_MEMB"].map({
        1: "SIM",
        2: "NAO",
    }).fillna("NAO INFORMADO")

    df["RACA_COR"] = df["COD_RACA_COR_PESSOA"].map({
        1: "BRANCA",
        2: "PRETA",
        3: "AMARELA",
        4: "PARDA",
        5: "INDIGENA",
    }).fillna("NAO INFORMADO")

    df["MATERIAL_PISO"] = df["COD_MATERIAL_PISO_FAM"].astype("Int64").astype("string").fillna("NAO INFORMADO")
    df["MATERIAL_DOMICILIO"] = df["COD_MATERIAL_DOMIC_FAM"].astype("Int64").astype("string").fillna("NAO INFORMADO")

    df["IND_COMODOS_POR_PESSOA"] = (
        df["QTD_COMODOS_DOMIC_FAM"] / df["QTDE_PESSOAS"].replace(0, pd.NA)
    )

    df["FAIXA_COMODOS_POR_PESSOA"] = pd.cut(
        df["IND_COMODOS_POR_PESSOA"],
        bins=[-999999, 0.999999, 999999],
        labels=["MENOR QUE 1", "1 OU MAIS"],
    ).astype("string").fillna("NAO INFORMADO")

    return df


# =========================================================
# PREPARE REVISAO / MAPAS
# =========================================================
def prepare_revisao_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["GRUPO_BENEFICIO", "TIPO_BENEFICIO", "UF", "MUNICIPIO_IBGE", "CAMPANHA", "SITUACAO_CADASTRAL_CAD"]:
        df = _ensure_text_column(df, col)
    df = _ensure_numeric_column(df, "QTD_BENEFICIOS")
    return df


def prepare_mapa_uf_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["GRUPO_BENEFICIO", "TIPO_BENEFICIO", "TIPO_DESPACHO", "SEXO", "UF"]:
        df = _ensure_text_column(df, col)
    df = _ensure_numeric_column(df, "QTD_BENEFICIOS")
    return df


def prepare_mapa_municipio_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["GRUPO_BENEFICIO", "TIPO_BENEFICIO", "SEXO", "UF", "MUNICIPIO_IBGE"]:
        df = _ensure_text_column(df, col)
    df = _ensure_numeric_column(df, "QTD_BENEFICIOS")
    return df


# =========================================================
# FILTROS
# =========================================================
def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    filtered = df.copy()

    for col, values in filters.items():
        if col in filtered.columns and values:
            filtered = filtered[filtered[col].astype(str).isin([str(v) for v in values])]

    return filtered


# =========================================================
# RESUMOS
# =========================================================
def summarize_unique_benefits(df: pd.DataFrame) -> int:
    if "NU_NB" in df.columns:
        return df["NU_NB"].astype(str).nunique()
    if "QTD_BENEFICIOS" in df.columns:
        return int(df["QTD_BENEFICIOS"].sum())
    return len(df)


def summarize_by_category(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in df.columns:
        return pd.DataFrame(columns=[column, "QTD"])

    if "NU_NB" in df.columns:
        out = (
            df.groupby(column, dropna=False)["NU_NB"]
            .nunique()
            .reset_index(name="QTD")
            .sort_values("QTD", ascending=False)
        )
    else:
        out = (
            df.groupby(column, dropna=False)["QTD_BENEFICIOS"]
            .sum()
            .reset_index(name="QTD")
            .sort_values("QTD", ascending=False)
        )
    return out


def summarize_by_two_categories(df: pd.DataFrame, col1: str, col2: str) -> pd.DataFrame:
    if col1 not in df.columns or col2 not in df.columns:
        return pd.DataFrame(columns=[col1, col2, "QTD"])

    if "NU_NB" in df.columns:
        out = (
            df.groupby([col1, col2], dropna=False)["NU_NB"]
            .nunique()
            .reset_index(name="QTD")
            .sort_values("QTD", ascending=False)
        )
    else:
        out = (
            df.groupby([col1, col2], dropna=False)["QTD_BENEFICIOS"]
            .sum()
            .reset_index(name="QTD")
            .sort_values("QTD", ascending=False)
        )
    return out


def safe_nunique(df: pd.DataFrame, col: str) -> int:
    return _safe_nunique(df, col)

def summarize_sex_with_percent(df: pd.DataFrame) -> pd.DataFrame:
    if "SEXO" not in df.columns:
        return pd.DataFrame(columns=["SEXO", "QTD", "PCT"])

    total = df["NU_NB"].astype(str).nunique() if "NU_NB" in df.columns else len(df)

    out = (
        df.groupby("SEXO", dropna=False)["NU_NB"]
        .nunique()
        .reset_index(name="QTD")
        .sort_values("QTD", ascending=False)
    )

    out["PCT"] = (out["QTD"] / total * 100).round(1) if total > 0 else 0
    out["ROTULO"] = out.apply(lambda row: f"{int(row['QTD']):,}".replace(",", ".") + f" ({str(row['PCT']).replace('.', ',')}%)", axis=1)
    return out


def create_faixa_idade_idoso_ajustada(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "IDADE_ANOS" not in df.columns:
        df["FAIXA_IDADE_IDOSO_AJUSTADA"] = "NAO INFORMADO"
        return df

    idade = pd.to_numeric(df["IDADE_ANOS"], errors="coerce")

    def classificar(v):
        if pd.isna(v):
            return "NAO INFORMADO"
        if v <= 64:
            return "0 A 64"
        if 65 <= v <= 70:
            return "65 A 70"
        if 71 <= v <= 75:
            return "71 A 75"
        if 76 <= v <= 80:
            return "76 A 80"
        return "80+"

    df["FAIXA_IDADE_IDOSO_AJUSTADA"] = idade.apply(classificar)
    return df


def summarize_age_band(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in df.columns:
        return pd.DataFrame(columns=[column, "QTD"])

    out = (
        df.groupby(column, dropna=False)["NU_NB"]
        .nunique()
        .reset_index(name="QTD")
    )
    return out


def prepare_binary_labels_com_sem(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    replace_map = {
        "SIM": "COM",
        "NAO": "SEM",
    }

    for col in [
        "ALFABETIZACAO",
        "AGUA_CANALIZADA",
        "CALCAMENTO",
        "FAMILIA_INDIGENA",
        "FAMILIA_QUILOMBOLA",
        "RESPONSAVEL_FAMILIAR",
    ]:
        if col in df.columns:
            df[col] = df[col].replace(replace_map)

    return df