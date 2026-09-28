import streamlit as st

from src.loaders import load_revisao_data
from src.transforms import (
    prepare_revisao_dataframe,
    apply_filters,
    summarize_unique_benefits,
    summarize_by_category,
    summarize_by_two_categories,
    safe_nunique,
)
from src.visuals import show_kpi_row, plot_bar, plot_stacked_bar, show_dataframe

st.set_page_config(page_title="Campanhas Cadastrais", layout="wide")
st.title("Campanhas Cadastrais")

cols_needed = [
    "GRUPO_BENEFICIO", "TIPO_BENEFICIO", "UF", "MUNICIPIO_IBGE",
    "CAMPANHA", "SITUACAO_CADASTRAL_CAD", "QTD_BENEFICIOS"
]

df = prepare_revisao_dataframe(load_revisao_data(columns=cols_needed))

with st.sidebar.form("filtros_revisao"):
    st.header("Filtros")
    grupo = st.multiselect("Grupo de benefício", sorted(df["GRUPO_BENEFICIO"].dropna().astype(str).unique()))
    tipo = st.multiselect("Tipo de benefício", sorted(df["TIPO_BENEFICIO"].dropna().astype(str).unique()))
    uf = st.multiselect("UF", sorted(df["UF"].dropna().astype(str).unique()))

    municipios = sorted(
        df.loc[df["UF"].isin(uf), "MUNICIPIO_IBGE"].dropna().astype(str).unique().tolist()
    ) if uf else []

    municipio = st.multiselect("Município", municipios)
    campanha = st.multiselect("Campanha", sorted(df["CAMPANHA"].dropna().astype(str).unique()))
    situacao = st.multiselect("Situação cadastral", sorted(df["SITUACAO_CADASTRAL_CAD"].dropna().astype(str).unique()))
    aplicar = st.form_submit_button("Aplicar filtros")

filtered = apply_filters(df, {
    "GRUPO_BENEFICIO": grupo,
    "TIPO_BENEFICIO": tipo,
    "UF": uf,
    "MUNICIPIO_IBGE": municipio,
    "CAMPANHA": campanha,
    "SITUACAO_CADASTRAL_CAD": situacao,
})

show_kpi_row([
    ("Benefícios em campanhas", f"{summarize_unique_benefits(filtered):,}".replace(",", ".")),
    ("UFs", f"{safe_nunique(filtered, 'UF'):,}".replace(",", ".")),
    ("Municípios", f"{safe_nunique(filtered, 'MUNICIPIO_IBGE'):,}".replace(",", ".")),
    ("Campanhas", f"{safe_nunique(filtered, 'CAMPANHA'):,}".replace(",", ".")),
])

c1, c2 = st.columns(2)
with c1:
    plot_bar(summarize_by_category(filtered, "CAMPANHA"), "CAMPANHA", "QTD", "Distribuição por campanha", horizontal=True)
with c2:
    plot_bar(summarize_by_category(filtered, "SITUACAO_CADASTRAL_CAD"), "SITUACAO_CADASTRAL_CAD", "QTD", "Situação cadastral", horizontal=True)

plot_stacked_bar(
    summarize_by_two_categories(filtered, "CAMPANHA", "SITUACAO_CADASTRAL_CAD"),
    "CAMPANHA",
    "QTD",
    "SITUACAO_CADASTRAL_CAD",
    "Campanha por situação cadastral"
)