import streamlit as st
import pandas as pd

from src.loaders import load_folha_data
from src.transforms import (
    prepare_folha_dataframe,
    apply_filters,
    summarize_unique_benefits,
    summarize_sex_with_percent,
    summarize_age_band,
    create_faixa_idade_idoso_ajustada,
)
from src.visuals import (
    show_kpi_row,
    plot_bar,
    plot_histogram,
    show_dataframe,
    format_int_br,
    format_pct_br,
    SEXO_COLOR_MAP,
)

st.set_page_config(page_title="BPC Maciça", layout="wide")
st.title("BPC Maciça - Folha de pagamento")

cols_needed = [
    "NU_NB", "NU_CPF", "ESPECIE_CODIGO", "GRUPO_BENEFICIO", "TIPO_BENEFICIO",
    "TIPO_DESPACHO", "INSCRITO_CADUNICO", "SEXO", "UF", "MUNICIPIO_IBGE",
    "IDADE_ANOS", "FAIXA_ETARIA"
]

df = prepare_folha_dataframe(load_folha_data(columns=cols_needed))
df_page = df[df["GRUPO_BENEFICIO"].isin(["BPC PCD", "BPC IDOSO"])].copy()
df_page = create_faixa_idade_idoso_ajustada(df_page)

# normalização da espécie
df_page["ESPECIE_ROTULO"] = df_page["ESPECIE_CODIGO"].map({
    87.0: "Espécie 87 - BPC PCD",
    88.0: "Espécie 88 - BPC Idoso",
}).fillna("Outros")

with st.sidebar.form("filtros_folha"):
    st.header("Filtros")
    tipo_despacho = st.multiselect(
        "Tipo de despacho",
        sorted(df_page["TIPO_DESPACHO"].dropna().astype(str).unique())
    )
    uf = st.multiselect(
        "UF",
        sorted(df_page["UF"].dropna().astype(str).unique())
    )

    municipios = sorted(
        df_page.loc[df_page["UF"].isin(uf), "MUNICIPIO_IBGE"].dropna().astype(str).unique().tolist()
    ) if uf else []

    municipio = st.multiselect("Município", municipios)
    sexo = st.multiselect(
        "Sexo",
        sorted(df_page["SEXO"].dropna().astype(str).unique())
    )
    aplicar = st.form_submit_button("Aplicar filtros")

filtered = apply_filters(df_page, {
    "TIPO_DESPACHO": tipo_despacho,
    "UF": uf,
    "MUNICIPIO_IBGE": municipio,
    "SEXO": sexo,
})

df_87 = filtered[filtered["ESPECIE_CODIGO"] == 87].copy()
df_88 = filtered[filtered["ESPECIE_CODIGO"] == 88].copy()

show_kpi_row([
    ("Total BPC", format_int_br(summarize_unique_benefits(filtered))),
    ("Espécie 87 - BPC PCD", format_int_br(summarize_unique_benefits(df_87))),
    ("Espécie 88 - BPC Idoso", format_int_br(summarize_unique_benefits(df_88))),
])

st.markdown("---")
st.header("Espécie 87 - BPC PCD")

col1, col2 = st.columns(2)

with col1:
    media_87 = pd.to_numeric(df_87["IDADE_ANOS"], errors="coerce").mean()
    desvio_87 = pd.to_numeric(df_87["IDADE_ANOS"], errors="coerce").std()
    st.metric("Idade média", f"{media_87:.1f}".replace(".", ",") if pd.notna(media_87) else "0,0")
    st.metric("Desvio padrão da idade", f"{desvio_87:.1f}".replace(".", ",") if pd.notna(desvio_87) else "0,0")

with col2:
    sexo_87 = summarize_sex_with_percent(df_87)
    if not sexo_87.empty:
        sexo_87_show = sexo_87[["SEXO", "QTD", "PCT"]].copy()
        sexo_87_show["QTD"] = sexo_87_show["QTD"].apply(format_int_br)
        sexo_87_show["PCT"] = sexo_87_show["PCT"].apply(format_pct_br)
        st.subheader("Sexo - quantidade e %")
        st.dataframe(sexo_87_show, use_container_width=True, hide_index=True)

plot_histogram(df_87, "IDADE_ANOS", "Distribuição de idade - Espécie 87", nbins=40)

plot_bar(
    summarize_sex_with_percent(df_87),
    x="SEXO",
    y="QTD",
    title="Sexo - Espécie 87",
    color="SEXO",
    color_map=SEXO_COLOR_MAP,
)

st.markdown("---")
st.header("Espécie 88 - BPC Idoso")

col1, col2 = st.columns(2)

with col1:
    media_88 = pd.to_numeric(df_88["IDADE_ANOS"], errors="coerce").mean()
    desvio_88 = pd.to_numeric(df_88["IDADE_ANOS"], errors="coerce").std()
    st.metric("Idade média", f"{media_88:.1f}".replace(".", ",") if pd.notna(media_88) else "0,0")
    st.metric("Desvio padrão da idade", f"{desvio_88:.1f}".replace(".", ",") if pd.notna(desvio_88) else "0,0")

with col2:
    sexo_88 = summarize_sex_with_percent(df_88)
    if not sexo_88.empty:
        sexo_88_show = sexo_88[["SEXO", "QTD", "PCT"]].copy()
        sexo_88_show["QTD"] = sexo_88_show["QTD"].apply(format_int_br)
        sexo_88_show["PCT"] = sexo_88_show["PCT"].apply(format_pct_br)
        st.subheader("Sexo - quantidade e %")
        st.dataframe(sexo_88_show, use_container_width=True, hide_index=True)

dist_88 = summarize_age_band(df_88, "FAIXA_IDADE_IDOSO_AJUSTADA")

ordem_88 = ["0 A 64", "65 A 70", "71 A 75", "76 A 80", "80+", "NAO INFORMADO"]
if not dist_88.empty:
    dist_88["ordem"] = dist_88["FAIXA_IDADE_IDOSO_AJUSTADA"].apply(lambda x: ordem_88.index(x) if x in ordem_88 else 999)
    dist_88 = dist_88.sort_values("ordem").drop(columns="ordem")

plot_bar(
    dist_88,
    x="FAIXA_IDADE_IDOSO_AJUSTADA",
    y="QTD",
    title="Distribuição de idade - Espécie 88",
)

plot_bar(
    summarize_sex_with_percent(df_88),
    x="SEXO",
    y="QTD",
    title="Sexo - Espécie 88",
    color="SEXO",
    color_map=SEXO_COLOR_MAP,
)

with st.expander("Ver amostra dos dados filtrados"):
    show_dataframe(filtered.head(200))