import streamlit as st

from src.loaders import load_folha_data
from src.transforms import (
    prepare_folha_dataframe,
    apply_filters,
    summarize_unique_benefits,
    summarize_by_category,
    safe_nunique,
)
from src.visuals import show_kpi_row, plot_bar, plot_pie, show_dataframe

st.set_page_config(page_title="Auxílio Inclusão", layout="wide")
st.title("Auxílio Inclusão")

cols_needed = [
    "NU_NB", "NU_CPF", "GRUPO_BENEFICIO", "TIPO_BENEFICIO",
    "TIPO_DESPACHO", "SEXO", "UF", "MUNICIPIO_IBGE",
    "IDADE_ANOS", "FAIXA_ETARIA"
]

df = prepare_folha_dataframe(load_folha_data(columns=cols_needed))
df_page = df[df["GRUPO_BENEFICIO"] == "AUXILIO INCLUSAO"].copy()

with st.sidebar.form("filtros_auxilio"):
    st.header("Filtros")
    uf = st.multiselect("UF", sorted(df_page["UF"].dropna().astype(str).unique()))
    municipios = sorted(
        df_page.loc[df_page["UF"].isin(uf), "MUNICIPIO_IBGE"].dropna().astype(str).unique().tolist()
    ) if uf else []
    municipio = st.multiselect("Município", municipios)
    sexo = st.multiselect("Sexo", sorted(df_page["SEXO"].dropna().astype(str).unique()))
    faixa_etaria = st.multiselect("Faixa etária", sorted(df_page["FAIXA_ETARIA"].dropna().astype(str).unique()))
    tipo_despacho = st.multiselect("Tipo de despacho", sorted(df_page["TIPO_DESPACHO"].dropna().astype(str).unique()))
    aplicar = st.form_submit_button("Aplicar filtros")

filtered = apply_filters(df_page, {
    "UF": uf,
    "MUNICIPIO_IBGE": municipio,
    "SEXO": sexo,
    "FAIXA_ETARIA": faixa_etaria,
    "TIPO_DESPACHO": tipo_despacho,
})

show_kpi_row([
    ("Benefícios", f"{summarize_unique_benefits(filtered):,}".replace(",", ".")),
    ("UFs", f"{safe_nunique(filtered, 'UF'):,}".replace(",", ".")),
    ("Municípios", f"{safe_nunique(filtered, 'MUNICIPIO_IBGE'):,}".replace(",", ".")),
    ("CPFs", f"{safe_nunique(filtered, 'NU_CPF'):,}".replace(",", ".")),
])

c1, c2 = st.columns(2)
with c1:
    plot_pie(summarize_by_category(filtered, "SEXO"), "SEXO", "QTD", "Distribuição por sexo")
with c2:
    plot_bar(summarize_by_category(filtered, "FAIXA_ETARIA"), "FAIXA_ETARIA", "QTD", "Faixa etária", horizontal=True)

plot_bar(summarize_by_category(filtered, "UF"), "UF", "QTD", "Distribuição por UF")
plot_bar(summarize_by_category(filtered, "TIPO_DESPACHO"), "TIPO_DESPACHO", "QTD", "Tipo de despacho", horizontal=True)
