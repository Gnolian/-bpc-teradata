import streamlit as st

from src.loaders import load_mapa_uf_data
from src.transforms import (
    prepare_mapa_uf_dataframe,
    apply_filters,
    summarize_by_category,
)
from src.visuals import plot_bar, show_dataframe

st.set_page_config(page_title="Mapas por UF", layout="wide")
st.title("Mapas por UF")

cols_needed = ["GRUPO_BENEFICIO", "TIPO_BENEFICIO", "TIPO_DESPACHO", "SEXO", "UF", "QTD_BENEFICIOS"]
df = prepare_mapa_uf_dataframe(load_mapa_uf_data(columns=cols_needed))

with st.sidebar.form("filtros_mapa_uf"):
    st.header("Filtros")
    grupo = st.multiselect("Grupo de benefício", sorted(df["GRUPO_BENEFICIO"].dropna().astype(str).unique()))
    tipo = st.multiselect("Tipo de benefício", sorted(df["TIPO_BENEFICIO"].dropna().astype(str).unique()))
    despacho = st.multiselect("Tipo de despacho", sorted(df["TIPO_DESPACHO"].dropna().astype(str).unique()))
    sexo = st.multiselect("Sexo", sorted(df["SEXO"].dropna().astype(str).unique()))
    aplicar = st.form_submit_button("Aplicar filtros")

filtered = apply_filters(df, {
    "GRUPO_BENEFICIO": grupo,
    "TIPO_BENEFICIO": tipo,
    "TIPO_DESPACHO": despacho,
    "SEXO": sexo,
})

plot_bar(summarize_by_category(filtered, "UF"), "UF", "QTD", "Benefícios por UF")