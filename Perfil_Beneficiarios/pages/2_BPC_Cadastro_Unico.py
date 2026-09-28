import streamlit as st
import pandas as pd

from src.loaders import load_cadastro_data, load_folha_data
from src.transforms import (
    prepare_cadastro_dataframe,
    prepare_folha_dataframe,
    apply_filters,
    summarize_by_category,
    safe_nunique,
    prepare_binary_labels_com_sem,
)
from src.visuals import (
    show_kpi_row,
    plot_bar,
    show_dataframe,
    format_int_br,
    format_pct_br,
)

st.set_page_config(page_title="BPC Cadastro Único", layout="wide")
st.title("BPC Cadastro Único")

# base cadastro
cols_cadastro = [
    "NU_NB", "NU_CPF", "CO_NB", "SG_UF_APP",
    "COD_SABE_LER_ESCREVER_MEMB", "IND_FREQUENTA_ESCOLA_MEMB",
    "COD_CURSO_FREQUENTA_MEMB", "COD_ANO_SERIE_FREQUENTA_MEMB",
    "COD_PARENTESCO_RF_PESSOA", "QTDE_PESSOAS", "QTD_COMODOS_DOMIC_FAM",
    "COD_MATERIAL_PISO_FAM", "COD_MATERIAL_DOMIC_FAM",
    "COD_AGUA_CANALIZADA_FAM", "COD_CALCAMENTO_DOMIC_FAM",
    "COD_FAMILIA_INDIGENA_FAM", "IND_FAMILIA_QUILOMBOLA_FAM",
    "IND_PARC_FAM", "IND_DORMIR_RUA_MEMB", "COD_RACA_COR_PESSOA"
]
df = prepare_cadastro_dataframe(load_cadastro_data(columns=cols_cadastro))
df = prepare_binary_labels_com_sem(df)

# base folha para cálculo de inscritos / não inscritos
cols_folha = ["NU_NB", "GRUPO_BENEFICIO", "INSCRITO_CADUNICO"]
df_folha = prepare_folha_dataframe(load_folha_data(columns=cols_folha))
df_folha_bpc = df_folha[df_folha["GRUPO_BENEFICIO"].isin(["BPC PCD", "BPC IDOSO"])].copy()

with st.sidebar.form("filtros_cadastro"):
    st.header("Filtros")
    uf = st.multiselect("UF do cadastro", sorted(df["SG_UF_APP"].dropna().astype(str).unique()))
    alfabetizacao = st.multiselect("Alfabetização", sorted(df["ALFABETIZACAO"].dropna().astype(str).unique()))
    frequencia = st.multiselect("Frequência escolar", sorted(df["FREQUENCIA_ESCOLAR"].dropna().astype(str).unique()))
    rf = st.multiselect("Responsável familiar", sorted(df["RESPONSAVEL_FAMILIAR"].dropna().astype(str).unique()))
    aplicar = st.form_submit_button("Aplicar filtros")

filtered = apply_filters(df, {
    "SG_UF_APP": uf,
    "ALFABETIZACAO": alfabetizacao,
    "FREQUENCIA_ESCOLAR": frequencia,
    "RESPONSAVEL_FAMILIAR": rf,
})

# KPIs novos
qtd_inscritos = df_folha_bpc[df_folha_bpc["INSCRITO_CADUNICO"] == "SIM"]["NU_NB"].astype(str).nunique()
qtd_nao_inscritos = df_folha_bpc[df_folha_bpc["INSCRITO_CADUNICO"] == "NAO"]["NU_NB"].astype(str).nunique()
qtd_total_bpc = df_folha_bpc["NU_NB"].astype(str).nunique()
pct_inscritos = (qtd_inscritos / qtd_total_bpc * 100) if qtd_total_bpc > 0 else 0

show_kpi_row([
    ("Quantidade inscrita", format_int_br(qtd_inscritos)),
    ("Quantidade não inscrita", format_int_br(qtd_nao_inscritos)),
    ("% inscrita no Cadastro Único", format_pct_br(pct_inscritos)),
])

st.subheader("Cadastro e vínculo familiar")
c1, c2 = st.columns(2)
with c1:
    plot_bar(
        summarize_by_category(filtered, "RESPONSAVEL_FAMILIAR"),
        "RESPONSAVEL_FAMILIAR",
        "QTD",
        "Responsável familiar",
        horizontal=True
    )
with c2:
    plot_bar(
        summarize_by_category(filtered, "PARENTESCO_RF"),
        "PARENTESCO_RF",
        "QTD",
        "Parentesco com o responsável familiar",
        horizontal=True
    )

st.subheader("Educação")
c1, c2 = st.columns(2)
with c1:
    plot_bar(
        summarize_by_category(filtered, "ALFABETIZACAO"),
        "ALFABETIZACAO",
        "QTD",
        "Alfabetização",
        horizontal=True
    )
with c2:
    plot_bar(
        summarize_by_category(filtered, "FREQUENCIA_ESCOLAR"),
        "FREQUENCIA_ESCOLAR",
        "QTD",
        "Frequência escolar",
        horizontal=True
    )

c1, c2 = st.columns(2)
with c1:
    plot_bar(
        summarize_by_category(filtered, "CURSO_FREQUENTA"),
        "CURSO_FREQUENTA",
        "QTD",
        "Curso frequentado",
        horizontal=True
    )
with c2:
    plot_bar(
        summarize_by_category(filtered, "ANO_SERIE_FREQUENTA"),
        "ANO_SERIE_FREQUENTA",
        "QTD",
        "Ano/Série frequentada",
        horizontal=True
    )

st.subheader("Condições do domicílio")
c1, c2 = st.columns(2)
with c1:
    plot_bar(
        summarize_by_category(filtered, "AGUA_CANALIZADA"),
        "AGUA_CANALIZADA",
        "QTD",
        "Domicílio com água canalizada",
        horizontal=True
    )
with c2:
    plot_bar(
        summarize_by_category(filtered, "CALCAMENTO"),
        "CALCAMENTO",
        "QTD",
        "Domicílio com calçamento",
        horizontal=True
    )

c1, c2 = st.columns(2)
with c1:
    plot_bar(
        summarize_by_category(filtered, "MATERIAL_PISO"),
        "MATERIAL_PISO",
        "QTD",
        "Material do piso",
        horizontal=True
    )
with c2:
    plot_bar(
        summarize_by_category(filtered, "MATERIAL_DOMICILIO"),
        "MATERIAL_DOMICILIO",
        "QTD",
        "Material do domicílio",
        horizontal=True
    )

st.subheader("Povos e comunidades tradicionais")
c1, c2 = st.columns(2)
with c1:
    plot_bar(
        summarize_by_category(filtered, "FAMILIA_INDIGENA"),
        "FAMILIA_INDIGENA",
        "QTD",
        "Famílias indígenas",
        horizontal=True
    )
with c2:
    plot_bar(
        summarize_by_category(filtered, "FAMILIA_QUILOMBOLA"),
        "FAMILIA_QUILOMBOLA",
        "QTD",
        "Famílias quilombolas",
        horizontal=True
    )

st.subheader("Outros recortes")
c1, c2 = st.columns(2)
with c1:
    plot_bar(
        summarize_by_category(filtered, "RACA_COR"),
        "RACA_COR",
        "QTD",
        "Raça/Cor",
        horizontal=True
    )
with c2:
    rua_uf = filtered[filtered["DORMIR_RUA"] == "SIM"].copy()
    if rua_uf.empty:
        st.info("Não há registros suficientes para distribuição por UF de quem dorme na rua.")
    else:
        plot_bar(
            summarize_by_category(rua_uf, "SG_UF_APP"),
            "SG_UF_APP",
            "QTD",
            "Distribuição por UF de quem dorme na rua",
            horizontal=True
        )

with st.expander("Ver amostra dos dados filtrados"):
    show_dataframe(filtered.head(200))