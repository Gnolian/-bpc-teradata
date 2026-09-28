import time
import pandas as pd
import streamlit as st

from app.auth import exigir_login, logout_button, sidebar_navigation, usuario_eh_admin, usuario_logado
from app.services.sqlite_service import (
    buscar_por_cpf,
    buscar_por_nb,
    buscar_por_codigo_familiar,
    buscar_familia_do_nb,
    buscar_registro_pessoa_por_cpf,
    buscar_registro_por_nb,
    criar_indices,
    encerrar_cargas_em_andamento,
    obter_periodo_competencias_disponiveis,
    registrar_log_consulta,
    verificar_prontidao_consulta,
)
from app.utils.validators import (
    validar_cpf_input,
    validar_nb_input,
    validar_codigo_familiar_input,
)
from app.utils.formatters import (
    formatar_cpf,
    normalizar_codigo_familiar,
    normalizar_cpf,
    normalizar_nb,
    formatar_competencia,
    formatar_data_br,
    descricao_especie,
    valor_legivel,
    formatar_codigo_familiar_exibicao,
    formatar_numero_inteiro,
)
from app.utils.pdf_export import (
    PDFExportError,
    gerar_pdf_detalhamento_pessoa,
    nome_arquivo_pdf_detalhamento,
)

st.set_page_config(
    page_title="SCB - Consulta Grupo Familiar",
    page_icon="🔎",
    layout="wide"
)

exigir_login()
sidebar_navigation()
usuario = usuario_logado()

st.markdown(
    """
    <style>
    .stApp {
        background-color: #020817;
        color: #f8fafc;
    }

    [data-testid="stSidebar"] {
        background-color: #1e1f29;
    }

    [data-testid="stSidebar"] * {
        color: #f8fafc !important;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    h1, h2, h3, h4, h5, h6, p, label, div, span {
        color: #f8fafc;
    }

    .stMarkdown, .stText, .stCaption {
        color: #f8fafc !important;
    }

    div[data-baseweb="select"] > div {
        background-color: #111827;
        color: #f8fafc;
        border: 1px solid rgba(255,255,255,0.12);
    }

    .stTextInput input {
        background-color: #111827;
        color: #f8fafc;
        border: 1px solid rgba(255,255,255,0.12);
    }

    .stButton > button {
        background-color: #1d4ed8;
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.45rem 1rem;
        font-weight: 600;
    }

    .stButton > button:hover {
        background-color: #2563eb;
        color: white;
    }

    div[data-testid="stAlert"] {
        border-radius: 8px;
        border: 1px solid rgba(148,163,184,0.24);
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(148,163,184,0.16);
        border-radius: 8px;
        overflow: hidden;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 8px;
        border-color: rgba(148,163,184,0.18);
        background: rgba(15,23,42,0.52);
    }

    .reference-panel {
        padding: 0.75rem 0;
        border-top: 1px solid rgba(148,163,184,0.14);
        border-bottom: 1px solid rgba(148,163,184,0.14);
        margin: 0.5rem 0 1rem;
    }

    .caixa-destaque {
        padding: 1rem;
        border-radius: 8px;
        background: rgba(15,23,42,0.64);
        border: 1px solid rgba(148,163,184,0.16);
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def formatar_tempo_pesquisa(segundos):
    if segundos is None:
        return ""
    if segundos < 1:
        return f"{segundos:.2f}s"
    if segundos < 60:
        return f"{segundos:.1f}s"
    minutos, resto = divmod(segundos, 60)
    return f"{int(minutos)}min {resto:.0f}s"


def bool_legivel(valor):
    if str(valor) == "1":
        return "Sim"
    if str(valor) == "0":
        return "Não"
    return "Não informado"


def formatar_nb_exibicao(valor):
    if pd.isna(valor) or str(valor).strip().lower() in ("", "nan", "none"):
        return "Não possui"
    return normalizar_nb(valor)


def data_ou_nao_informado(valor):
    return formatar_data_br(valor) or "Não informado"


def tipo_registro_legivel(valor):
    mapa = {
        "BENEFICIARIO_CADUNICO": "Beneficiário no CadÚnico",
        "MEMBRO_FAMILIAR": "Membro familiar",
        "NAO_CADASTRADO": "Não cadastrado no CadÚnico",
    }
    return mapa.get(str(valor).strip(), valor_legivel(valor))


def registro_macica_provisoria(registro):
    situacao = str(registro.get("SITUACAO_CAD_UNICO") or "").strip().upper()
    flag = str(registro.get("FLAG_CADUNICO") or "").strip().upper()
    return situacao == "MACICA_PROVISORIA_CADUNICO_PENDENTE" or flag == "PENDENTE_CADUNICO"


def nome_registro(registro):
    return valor_legivel(registro.get("NOM_PESSOA") or registro.get("NM_TIT_BENEF_T"), vazio="Não informado")


def cpf_registro(registro):
    return registro.get("NUM_CPF_PESSOA") or registro.get("NU_CPF_T") or ""


def nis_registro(registro):
    return registro.get("NUM_NIS_PESSOA_ATUAL") or registro.get("NU_NIS_T")


def data_nascimento_registro(registro):
    return registro.get("DTA_NASC_PESSOA") or registro.get("DT_NASC_T")


def idade_registro(registro):
    idade_pessoa = registro.get("IDADE_PESSOA")
    if idade_pessoa not in (None, "", "nan"):
        return idade_pessoa
    return registro.get("IDADE_T")


def nome_mae_registro(registro):
    return registro.get("NOM_COMPLETO_MAE_PESSOA") or registro.get("NM_MAE_T") or ""


def parentesco_registro(registro):
    return registro.get("DESC_PARENTESCO") or ""


def referencia_formatada(valor):
    if valor in (None, "", "nan", "None"):
        return "Não informado"
    return formatar_competencia(valor)


def referencia_numero(valor):
    ref = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    if pd.isna(ref):
        return None
    return int(ref)


def obter_periodo_base():
    return obter_periodo_competencias_disponiveis()


def buscar_beneficio_na_ultima_referencia(registro, ultima_ref_disponivel):
    ultima_ref_base = referencia_numero(ultima_ref_disponivel)
    if ultima_ref_base is None:
        return None

    candidatos = []
    nb = normalizar_nb(registro.get("NU_NB") or "")
    cpf = normalizar_cpf(cpf_registro(registro))

    if nb:
        candidatos.append(buscar_registro_por_nb(nb))
    if cpf:
        candidatos.append(buscar_registro_pessoa_por_cpf(cpf))

    for candidato in candidatos:
        if not candidato:
            continue

        tipo = str(candidato.get("TIPO_REGISTRO") or "").strip()
        ref_candidato = referencia_numero(candidato.get("NU_MES_REF"))
        if (
            ref_candidato == ultima_ref_base
            and tipo in {"BENEFICIARIO_CADUNICO", "NAO_CADASTRADO"}
        ):
            return candidato

    return None


def especie_beneficio_legivel(cs_especie):
    if cs_especie is None:
        return "Não informado"

    valor = str(cs_especie).strip()

    if valor.endswith(".0"):
        valor = valor[:-2]

    mapa = {
        "87": "Benefício de Prestação Continuada à Pessoa com Deficiência (BPC/PCD)",
        "88": "Benefício de Prestação Continuada à Pessoa Idosa (BPC/Idoso)",
        "18": "Auxílio-Inclusão",
        "11": "Renda Mensal Vitalícia por Invalidez (RMV)",
        "12": "Renda Mensal Vitalícia por Idade (RMV)",
        "30": "Renda Mensal Vitalícia por Invalidez (RMV)",
        "40": "Renda Mensal Vitalícia por Idade (RMV)",
        "60": "Benefício relacionado à Síndrome Congênita do Zika Vírus",
    }

    return mapa.get(valor, descricao_especie(valor))


def montar_mensagem_encontrado(registro, primeira_ref_disponivel, ultima_ref_disponivel):
    nome = nome_registro(registro)
    cpf = formatar_cpf(cpf_registro(registro))
    especie = especie_beneficio_legivel(registro.get("CS_ESPECIE"))
    dib = formatar_data_br(registro.get("DT_INICIO_BENEFICIO"))
    ultima_ref_registro = referencia_numero(registro.get("NU_MES_REF"))
    ultima_ref_base = referencia_numero(ultima_ref_disponivel)
    ultima_ref_apareceu = referencia_formatada(ultima_ref_registro)
    esta_na_ultima_ref = (
        ultima_ref_registro is not None
        and ultima_ref_base is not None
        and ultima_ref_registro == ultima_ref_base
    )
    registro_ultima_ref = buscar_beneficio_na_ultima_referencia(registro, ultima_ref_disponivel)

    if esta_na_ultima_ref:
        situacao = (
            f"consta como titular beneficiário(a) do {especie}, "
            f"com Data de Início do Benefício (DIB) em {dib}, na última referência "
            f"carregada ({referencia_formatada(ultima_ref_base)})"
        )
    elif registro_ultima_ref:
        if registro_macica_provisoria(registro_ultima_ref):
            situacao = (
                f"consta como titular beneficiário(a) do {especie}, "
                f"com Data de Início do Benefício (DIB) em {dib}, presente na última "
                f"referência da Maciça carregada ({referencia_formatada(ultima_ref_base)}). "
                f"Os dados de grupo familiar/CadÚnico exibidos nesta página correspondem "
                f"à última referência com CadÚnico disponível ({ultima_ref_apareceu})"
            )
        else:
            situacao = (
                f"consta como titular beneficiário(a) do {especie}, "
                f"com Data de Início do Benefício (DIB) em {dib}, presente na última "
                f"referência carregada ({referencia_formatada(ultima_ref_base)})"
            )
    else:
        situacao = (
            f"foi localizado(a) como titular beneficiário(a) do {especie}, "
            f"com Data de Início do Benefício (DIB) em {dib}, mas não foi encontrado(a) "
            f"na última referência carregada ({referencia_formatada(ultima_ref_base)}). "
            f"A última presença identificada foi em {ultima_ref_apareceu}"
        )

    return (
        f"Segundo cruzamento realizado entre a Maciça e os dados do CadÚnico, "
        f"{nome}, CPF nº {cpf}, {situacao}, no período analisado de "
        f"{referencia_formatada(primeira_ref_disponivel)} a "
        f"{referencia_formatada(ultima_ref_disponivel)}."
    )

def montar_mensagem_nao_encontrado(nome, cpf, primeira_ref_disponivel, ultima_ref_disponivel):
    return (
        f"Conforme cruzamento realizado entre a Maciça e os dados do CadÚnico, "
        f"não foram identificados registros em nome de {nome}, CPF nº {formatar_cpf(cpf)}, "
        f"na condição de titular beneficiário(a) do BPC, do Auxílio-Inclusão ou da RMV, "
        f"no período de {referencia_formatada(primeira_ref_disponivel)} a "
        f"{referencia_formatada(ultima_ref_disponivel)}."
    )


def montar_mensagem_integrante_grupo_familiar(
    registro_pesquisado,
    registro_titular,
    primeira_ref_disponivel,
    ultima_ref_disponivel
):
    nome_pesquisado = nome_registro(registro_pesquisado)
    cpf_pesquisado = formatar_cpf(cpf_registro(registro_pesquisado))
    codigo_familiar = formatar_codigo_familiar_exibicao(registro_pesquisado.get("CO_FAMILIAR_FAM"))

    nome_titular = nome_registro(registro_titular)
    cpf_titular = formatar_cpf(cpf_registro(registro_titular))
    especie = especie_beneficio_legivel(registro_titular.get("CS_ESPECIE"))
    dib = formatar_data_br(registro_titular.get("DT_INICIO_BENEFICIO"))
    ultima_ref_titular = referencia_numero(registro_titular.get("NU_MES_REF"))
    ultima_ref_base = referencia_numero(ultima_ref_disponivel)
    ultima_ref_beneficio = referencia_formatada(ultima_ref_titular)
    esta_na_ultima_ref = (
        ultima_ref_titular is not None
        and ultima_ref_base is not None
        and ultima_ref_titular == ultima_ref_base
    )
    registro_ultima_ref = buscar_beneficio_na_ultima_referencia(registro_titular, ultima_ref_disponivel)

    if esta_na_ultima_ref:
        status_titular = (
            f"é titular de {especie}, com Data de Início do Benefício (DIB) em {dib}, "
            f"na última referência carregada ({referencia_formatada(ultima_ref_base)})"
        )
    elif registro_ultima_ref:
        if registro_macica_provisoria(registro_ultima_ref):
            status_titular = (
                f"é titular de {especie}, com Data de Início do Benefício (DIB) em {dib}, "
                f"presente na última referência da Maciça carregada "
                f"({referencia_formatada(ultima_ref_base)}). Os dados de grupo familiar/CadÚnico "
                f"exibidos nesta página correspondem à última referência com CadÚnico disponível "
                f"({ultima_ref_beneficio})"
            )
        else:
            status_titular = (
                f"é titular de {especie}, com Data de Início do Benefício (DIB) em {dib}, "
                f"presente na última referência carregada ({referencia_formatada(ultima_ref_base)})"
            )
    else:
        status_titular = (
            f"foi titular de {especie}, com Data de Início do Benefício (DIB) em {dib}, "
            f"mas não foi encontrado(a) na última referência carregada "
            f"({referencia_formatada(ultima_ref_base)}). A última presença identificada "
            f"foi em {ultima_ref_beneficio}"
        )

    return (
        f"Segundo cruzamento realizado entre a Maciça e os dados do CadÚnico, "
        f"informa-se que {nome_pesquisado}, CPF nº {cpf_pesquisado}, não figura como titular "
        f"de BPC, Auxílio-Inclusão ou RMV. Todavia, consta como integrante do grupo familiar "
        f"de código nº {codigo_familiar}, no qual {nome_titular}, CPF nº {cpf_titular}, "
        f"{status_titular}, no período analisado de "
        f"{referencia_formatada(primeira_ref_disponivel)} a "
        f"{referencia_formatada(ultima_ref_disponivel)}."
    )

def obter_periodo_analisado(resultado: pd.DataFrame):
    if resultado.empty or "NU_MES_REF" not in resultado.columns:
        return None, None

    refs = pd.to_numeric(resultado["NU_MES_REF"], errors="coerce").dropna()

    if refs.empty:
        return None, None

    return int(refs.min()), int(refs.max())


def _serie_texto(df: pd.DataFrame, coluna: str) -> pd.Series:
    if coluna not in df.columns:
        return pd.Series("", index=df.index, dtype="object")
    return df[coluna].fillna("").astype(str)


def _serie_digitos(df: pd.DataFrame, coluna: str) -> pd.Series:
    return _serie_texto(df, coluna).str.replace(r"\D", "", regex=True)


def preparar_resultado_consulta(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    preparado = df.copy()
    preparado["TIPO_REGISTRO_STR"] = _serie_texto(preparado, "TIPO_REGISTRO")
    preparado["NU_MES_REF_NUM"] = pd.to_numeric(preparado.get("NU_MES_REF"), errors="coerce")
    preparado["CPF_PESSOA_NORM"] = _serie_digitos(preparado, "NUM_CPF_PESSOA")
    preparado["CPF_TITULAR_NORM"] = _serie_digitos(preparado, "NU_CPF_T")
    preparado["NU_NB_NORM"] = _serie_digitos(preparado, "NU_NB")
    preparado["CHAVE_PESSOA_STR"] = _serie_texto(preparado, "CO_CHV_NATURAL_PESSOA").str.strip()

    nome_base = _serie_texto(preparado, "NOM_PESSOA")
    nome_titular = _serie_texto(preparado, "NM_TIT_BENEF_T")
    preparado["NOME_BASE"] = nome_base.mask(nome_base.str.strip().isin(["", "nan", "None"]), nome_titular)

    data_nasc_pessoa = _serie_texto(preparado, "DTA_NASC_PESSOA")
    data_nasc_titular = _serie_texto(preparado, "DT_NASC_T")
    preparado["DATA_NASC_BASE"] = data_nasc_pessoa.mask(
        data_nasc_pessoa.str.strip().isin(["", "nan", "None"]),
        data_nasc_titular,
    )

    parentesco = _serie_texto(preparado, "DESC_PARENTESCO").str.strip().str.upper()
    cpf_chave = preparado["CPF_PESSOA_NORM"].mask(preparado["CPF_PESSOA_NORM"].eq(""), preparado["CPF_TITULAR_NORM"])
    cpf_chave = cpf_chave.mask(cpf_chave.eq(""), None)
    chave_natural = preparado["CHAVE_PESSOA_STR"].mask(preparado["CHAVE_PESSOA_STR"].eq(""), None)
    nb_chave = preparado["NU_NB_NORM"].mask(preparado["NU_NB_NORM"].eq(""), None)

    preparado["PESSOA_CHAVE"] = (
        cpf_chave.map(lambda x: f"CPF:{x}" if x else None)
        .fillna(chave_natural.map(lambda x: f"CHAVE:{x}" if x else None))
        .fillna(nb_chave.map(lambda x: f"NB:{x}" if x else None))
        .fillna(
            "NOME:"
            + preparado["NOME_BASE"].str.strip().str.upper()
            + "|NASC:"
            + preparado["DATA_NASC_BASE"].str.strip()
            + "|PARENTESCO:"
            + parentesco
        )
    )

    return preparado


def dataframe_para_exibicao(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    exibicao = df.copy()

    exibicao["CPF_EXIBICAO"] = exibicao["NUM_CPF_PESSOA"].fillna("")
    mask_sem_cpf_pessoa = exibicao["CPF_EXIBICAO"].astype(str).str.strip().isin(["", "nan", "None"])
    exibicao.loc[mask_sem_cpf_pessoa, "CPF_EXIBICAO"] = exibicao.loc[mask_sem_cpf_pessoa, "NU_CPF_T"]

    exibicao["NOME_EXIBICAO"] = exibicao["NOM_PESSOA"].fillna("")
    mask_sem_nome_pessoa = exibicao["NOME_EXIBICAO"].astype(str).str.strip().isin(["", "nan", "None"])
    exibicao.loc[mask_sem_nome_pessoa, "NOME_EXIBICAO"] = exibicao.loc[mask_sem_nome_pessoa, "NM_TIT_BENEF_T"]

    exibicao["NIS_EXIBICAO"] = exibicao["NUM_NIS_PESSOA_ATUAL"].fillna("")
    mask_sem_nis_pessoa = exibicao["NIS_EXIBICAO"].astype(str).str.strip().isin(["", "nan", "None"])
    exibicao.loc[mask_sem_nis_pessoa, "NIS_EXIBICAO"] = exibicao.loc[mask_sem_nis_pessoa, "NU_NIS_T"]

    exibicao["IDADE_EXIBICAO"] = exibicao["IDADE_PESSOA"]
    mask_sem_idade_pessoa = exibicao["IDADE_EXIBICAO"].isna()
    exibicao.loc[mask_sem_idade_pessoa, "IDADE_EXIBICAO"] = exibicao.loc[mask_sem_idade_pessoa, "IDADE_T"]

    exibicao["DATA_NASC_EXIBICAO"] = exibicao["DTA_NASC_PESSOA"].fillna("")
    mask_sem_dt_pessoa = exibicao["DATA_NASC_EXIBICAO"].astype(str).str.strip().isin(["", "nan", "None"])
    exibicao.loc[mask_sem_dt_pessoa, "DATA_NASC_EXIBICAO"] = exibicao.loc[mask_sem_dt_pessoa, "DT_NASC_T"]

    exibicao["MAE_EXIBICAO"] = exibicao["NOM_COMPLETO_MAE_PESSOA"].fillna("")
    mask_sem_mae_pessoa = exibicao["MAE_EXIBICAO"].astype(str).str.strip().isin(["", "nan", "None"])
    exibicao.loc[mask_sem_mae_pessoa, "MAE_EXIBICAO"] = exibicao.loc[mask_sem_mae_pessoa, "NM_MAE_T"]

    exibicao["TIPO_EXIBICAO"] = exibicao["TIPO_REGISTRO"].apply(tipo_registro_legivel)
    exibicao["PARENTESCO_EXIBICAO"] = exibicao["DESC_PARENTESCO"].apply(lambda x: valor_legivel(x, vazio="Não se aplica"))
    exibicao["NB_EXIBICAO"] = exibicao["NU_NB"].apply(formatar_nb_exibicao)
    exibicao["CPF_EXIBICAO"] = exibicao["CPF_EXIBICAO"].apply(formatar_cpf)
    exibicao["CODIGO_FAMILIAR_EXIBICAO"] = exibicao["CO_FAMILIAR_FAM"].apply(formatar_codigo_familiar_exibicao)

    if "CS_ESPECIE" in exibicao.columns:
        exibicao["ESPECIE_EXIBICAO"] = exibicao["CS_ESPECIE"].apply(
            lambda x: descricao_especie(x) if str(x).strip().lower() not in ("", "nan", "none") else "Não se aplica"
        )

    for col in [
        "DATA_NASC_EXIBICAO",
        "DT_DESPACHO",
        "DT_ENTRADA_REQUERIMENTO",
        "DT_INICIO_BENEFICIO",
        "DTA_ATUAL_MEMB",
    ]:
        if col in exibicao.columns:
            exibicao[col] = exibicao[col].apply(formatar_data_br)

    if "NU_MES_REF" in exibicao.columns:
        exibicao["NU_MES_REF"] = exibicao["NU_MES_REF"].apply(formatar_competencia)

    exibicao = exibicao.rename(columns={
        "NOME_EXIBICAO": "Nome",
        "CPF_EXIBICAO": "CPF",
        "NB_EXIBICAO": "Número do benefício",
        "ESPECIE_EXIBICAO": "Espécie",
        "PARENTESCO_EXIBICAO": "Parentesco",
        "TIPO_EXIBICAO": "Tipo de Registro",
        "SITUACAO_CAD_UNICO": "Situação no CadÚnico",
        "CODIGO_FAMILIAR_EXIBICAO": "Código Familiar",
        "MUNICIPIO_MACICA": "Município Maciça",
        "UF_MACICA": "UF Maciça",
        "MUNICIPIO_CAD": "Município CadÚnico",
        "UF_CAD": "UF CadÚnico",
        "NU_MES_REF": "Competência",
        "IDADE_EXIBICAO": "Idade",
        "DATA_NASC_EXIBICAO": "Nascimento",
    })

    return exibicao


def dataframe_para_tabela(df: pd.DataFrame, colunas_saida: list[str]) -> pd.DataFrame:
    if df.empty:
        return df

    exibicao = pd.DataFrame(index=df.index)

    if "Nome" in colunas_saida:
        if "NOME_BASE" in df.columns:
            exibicao["Nome"] = df["NOME_BASE"]
        else:
            nome_pessoa = _serie_texto(df, "NOM_PESSOA")
            nome_titular = _serie_texto(df, "NM_TIT_BENEF_T")
            exibicao["Nome"] = nome_pessoa.mask(
                nome_pessoa.str.strip().isin(["", "nan", "None"]),
                nome_titular,
            )

    if "CPF" in colunas_saida:
        cpf_pessoa = _serie_texto(df, "NUM_CPF_PESSOA")
        cpf_titular = _serie_texto(df, "NU_CPF_T")
        cpf_exib = cpf_pessoa.mask(
            cpf_pessoa.str.strip().isin(["", "nan", "None"]),
            cpf_titular,
        )
        exibicao["CPF"] = cpf_exib.map(formatar_cpf)

    if "Número do benefício" in colunas_saida:
        exibicao["Número do benefício"] = _serie_texto(df, "NU_NB").map(formatar_nb_exibicao)

    if "Parentesco" in colunas_saida:
        exibicao["Parentesco"] = _serie_texto(df, "DESC_PARENTESCO").map(
            lambda x: valor_legivel(x, vazio="Não se aplica")
        )

    if "Tipo de Registro" in colunas_saida:
        coluna_tipo = "TIPO_REGISTRO_STR" if "TIPO_REGISTRO_STR" in df.columns else "TIPO_REGISTRO"
        exibicao["Tipo de Registro"] = _serie_texto(df, coluna_tipo).map(tipo_registro_legivel)

    if "Espécie" in colunas_saida:
        especie = _serie_texto(df, "CS_ESPECIE")
        exibicao["Espécie"] = especie.map(
            lambda x: descricao_especie(x) if str(x).strip().lower() not in ("", "nan", "none") else "Não se aplica"
        )

    if "Situação no CadÚnico" in colunas_saida and "SITUACAO_CAD_UNICO" in df.columns:
        exibicao["Situação no CadÚnico"] = df["SITUACAO_CAD_UNICO"]

    if "Código Familiar" in colunas_saida:
        exibicao["Código Familiar"] = _serie_texto(df, "CO_FAMILIAR_FAM").map(formatar_codigo_familiar_exibicao)

    if "Município Maciça" in colunas_saida and "MUNICIPIO_MACICA" in df.columns:
        exibicao["Município Maciça"] = df["MUNICIPIO_MACICA"]

    if "UF Maciça" in colunas_saida and "UF_MACICA" in df.columns:
        exibicao["UF Maciça"] = df["UF_MACICA"]

    if "Competência" in colunas_saida and "NU_MES_REF" in df.columns:
        exibicao["Competência"] = df["NU_MES_REF"].map(formatar_competencia)

    colunas_validas = [col for col in colunas_saida if col in exibicao.columns]
    return exibicao[colunas_validas]


def montar_opcoes_registro(df: pd.DataFrame, incluir_referencia: bool = True):
    opcoes = []
    for row in df.itertuples():
        idx = row.Index
        registro = row._asdict()
        registro.pop("Index", None)
        nome = nome_registro(registro)
        nb = formatar_nb_exibicao(registro.get("NU_NB", ""))
        parentesco = valor_legivel(parentesco_registro(registro), vazio="Sem parentesco")
        cpf = formatar_cpf(cpf_registro(registro))
        tipo = tipo_registro_legivel(registro.get("TIPO_REGISTRO"))
        texto = f"{nome} | Número do benefício: {nb} | {parentesco} | CPF: {cpf} | {tipo}"
        if incluir_referencia:
            competencia = formatar_competencia(registro.get("NU_MES_REF", ""))
            texto = f"{texto} | Ref.: {competencia}"
        opcoes.append((texto, idx))
    return opcoes


def obter_chave_pessoa(registro):
    cpf = normalizar_cpf(cpf_registro(registro))
    nb = normalizar_nb(registro.get("NU_NB"))
    chave_natural = str(registro.get("CO_CHV_NATURAL_PESSOA") or "").strip()

    if cpf:
        return ("CPF", cpf)
    if nb:
        return ("NB", nb)
    if chave_natural:
        return ("CHAVE", chave_natural)
    return ("IDX", None)


def filtrar_mesma_pessoa(df: pd.DataFrame, registro_base: dict) -> pd.DataFrame:
    tipo_chave, valor = obter_chave_pessoa(registro_base)

    if tipo_chave == "CPF" and valor:
        if {"CPF_PESSOA_NORM", "CPF_TITULAR_NORM"}.issubset(df.columns):
            mask = df["CPF_PESSOA_NORM"].eq(valor) | df["CPF_TITULAR_NORM"].eq(valor)
        else:
            mask = (
                df["NUM_CPF_PESSOA"].fillna("").apply(normalizar_cpf).eq(valor) |
                df["NU_CPF_T"].fillna("").apply(normalizar_cpf).eq(valor)
            )
        return df[mask].copy()

    if tipo_chave == "NB" and valor:
        if "NU_NB_NORM" in df.columns:
            mask = df["NU_NB_NORM"].eq(valor)
        else:
            mask = df["NU_NB"].fillna("").apply(normalizar_nb).eq(valor)
        return df[mask].copy()

    if tipo_chave == "CHAVE" and valor:
        if "CHAVE_PESSOA_STR" in df.columns:
            mask = df["CHAVE_PESSOA_STR"].eq(valor)
        else:
            mask = df["CO_CHV_NATURAL_PESSOA"].fillna("").astype(str).eq(valor)
        return df[mask].copy()

    return pd.DataFrame([registro_base])


def chave_pessoa_para_contagem(registro):
    cpf = normalizar_cpf(cpf_registro(registro))
    if cpf:
        return f"CPF:{cpf}"

    chave_natural = str(registro.get("CO_CHV_NATURAL_PESSOA") or "").strip()
    if chave_natural:
        return f"CHAVE:{chave_natural}"

    nb = normalizar_nb(registro.get("NU_NB"))
    if nb:
        return f"NB:{nb}"

    nome = nome_registro(registro).strip().upper()
    nascimento = str(data_nascimento_registro(registro) or "").strip()
    parentesco = str(parentesco_registro(registro) or "").strip().upper()
    return f"NOME:{nome}|NASC:{nascimento}|PARENTESCO:{parentesco}"


def contar_pessoas_distintas(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    if "PESSOA_CHAVE" in df.columns:
        return int(df["PESSOA_CHAVE"].nunique())
    chaves = {chave_pessoa_para_contagem(row.to_dict()) for _, row in df.iterrows()}
    return len(chaves)


def selecionar_referencia_grupo(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty or "NU_MES_REF" not in df.columns:
        return df

    refs_df = df.copy()
    if "NU_MES_REF_NUM" not in refs_df.columns:
        refs_df["NU_MES_REF_NUM"] = pd.to_numeric(refs_df["NU_MES_REF"], errors="coerce")
    refs_df = refs_df.dropna(subset=["NU_MES_REF_NUM"])

    if refs_df.empty:
        return df

    refs_df["__macica_provisoria"] = refs_df.apply(
        lambda row: registro_macica_provisoria(row.to_dict()),
        axis=1,
    )
    refs_provisorias = refs_df.loc[refs_df["__macica_provisoria"], "NU_MES_REF_NUM"].dropna()
    refs_grupo = refs_df.loc[~refs_df["__macica_provisoria"]].copy()

    if not refs_provisorias.empty:
        refs_formatadas = ", ".join(
            formatar_competencia(int(ref))
            for ref in sorted(refs_provisorias.unique(), reverse=True)
        )
        st.warning(
            f"A referência {refs_formatadas} ainda possui somente dados da Maciça. "
            "A composição do grupo familiar/CadÚnico dessa referência ainda não foi carregada. "
            "Para consultar o grupo familiar, selecione uma referência anterior."
        )

    if refs_grupo.empty:
        st.warning(
            "Nenhuma referência com composição do grupo familiar/CadÚnico foi localizada para esta consulta."
        )
        return refs_grupo.drop(columns=["NU_MES_REF_NUM", "__macica_provisoria"], errors="ignore")

    refs_df = refs_grupo

    if "PESSOA_CHAVE" in refs_df.columns:
        contagem_refs = refs_df.groupby("NU_MES_REF_NUM")["PESSOA_CHAVE"].nunique().sort_index(ascending=False)
    else:
        contagem_refs = refs_df.groupby("NU_MES_REF_NUM").size().sort_index(ascending=False)

    opcoes = []
    mapa_refs = {}

    for ref, qtd_pessoas in contagem_refs.items():
        ref = int(ref)
        qtd_pessoas = int(qtd_pessoas)
        rotulo = (
            f"{formatar_competencia(ref)} - {qtd_pessoas} "
            f"{'pessoa' if qtd_pessoas == 1 else 'pessoas'}"
        )
        opcoes.append(rotulo)
        mapa_refs[rotulo] = ref

    if len(opcoes) == 1:
        st.caption(f"Referência exibida: {opcoes[0]}")
        ref_unica = next(iter(mapa_refs.values()))
        return refs_df[refs_df["NU_MES_REF_NUM"].eq(ref_unica)].drop(
            columns=["NU_MES_REF_NUM", "__macica_provisoria"],
            errors="ignore",
        )

    st.markdown('<div class="reference-panel">', unsafe_allow_html=True)
    referencia_escolhida = st.select_slider(
        "Escolha a referência do grupo familiar",
        options=opcoes,
        value=opcoes[0],
        key=key,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    ref_num = mapa_refs[referencia_escolhida]
    return refs_df[refs_df["NU_MES_REF_NUM"].eq(ref_num)].drop(
        columns=["NU_MES_REF_NUM", "__macica_provisoria"],
        errors="ignore",
    )


def selecionar_referencia_detalhe(registros: pd.DataFrame, key: str):
    if registros.empty or "NU_MES_REF" not in registros.columns:
        return None

    regs_comp = registros.copy()
    if "NU_MES_REF_NUM" not in regs_comp.columns:
        regs_comp["NU_MES_REF_NUM"] = pd.to_numeric(regs_comp["NU_MES_REF"], errors="coerce")
    regs_comp = regs_comp.dropna(subset=["NU_MES_REF_NUM"]).sort_values("NU_MES_REF_NUM", ascending=False)

    if regs_comp.empty:
        return None

    if len(regs_comp) == 1:
        return regs_comp.iloc[0]

    refs_unicas = regs_comp.drop_duplicates(subset=["NU_MES_REF_NUM"], keep="first")
    opcoes = [formatar_competencia(int(ref)) for ref in refs_unicas["NU_MES_REF_NUM"]]
    mapa = dict(zip(opcoes, refs_unicas.index))

    st.markdown('<div class="reference-panel">', unsafe_allow_html=True)
    st.markdown("### Referência do detalhamento")
    ref_escolhida = st.select_slider(
        "Escolha a referência",
        options=opcoes,
        value=opcoes[0],
        key=key,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    return regs_comp.loc[mapa[ref_escolhida]]


def exibir_detalhamento(registro):
    st.markdown("## Detalhamento do registro selecionado")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Dados da pessoa / registro")
        st.write(f"**Tipo de registro:** {tipo_registro_legivel(registro.get('TIPO_REGISTRO', ''))}")
        st.write(f"**Nome:** {nome_registro(registro)}")
        st.write(f"**CPF:** {formatar_cpf(cpf_registro(registro))}")
        st.write(f"**Data de nascimento:** {data_ou_nao_informado(data_nascimento_registro(registro))}")
        st.write(f"**Idade:** {valor_legivel(idade_registro(registro), vazio='Não informado')}")
        st.write(f"**Nome da mãe:** {valor_legivel(nome_mae_registro(registro), vazio='Não informado')}")
        st.write(f"**Gênero:** {valor_legivel(registro.get('GENERO', ''))}")
        st.write(f"**Raça/Cor:** {valor_legivel(registro.get('RACA_COR', ''))}")
        st.write(f"**Número de Identificação Social:** {formatar_numero_inteiro(nis_registro(registro))}")
        st.write(f"**Chave natural da pessoa:** {formatar_numero_inteiro(registro.get('CO_CHV_NATURAL_PESSOA'))}")
        st.write(f"**Código familiar:** {formatar_codigo_familiar_exibicao(registro.get('CO_FAMILIAR_FAM'))}")
        st.write(f"**Parentesco com o responsável familiar:** {valor_legivel(parentesco_registro(registro), vazio='Não se aplica')}")
        st.write(f"**Situação no CadÚnico:** {valor_legivel(registro.get('SITUACAO_CAD_UNICO', ''))}")
        st.write(f"**Atualização do membro:** {data_ou_nao_informado(registro.get('DTA_ATUAL_MEMB'))}")

        st.markdown("### Localização")
        st.write(f"**UF Maciça:** {valor_legivel(registro.get('UF_MACICA', ''))}")
        st.write(f"**Município Maciça:** {valor_legivel(registro.get('MUNICIPIO_MACICA', ''))}")
        st.write(f"**UF CadÚnico:** {valor_legivel(registro.get('UF_CAD', ''))}")
        st.write(f"**Município CadÚnico:** {valor_legivel(registro.get('MUNICIPIO_CAD', ''))}")
        st.write(f"**UF Agência PGD:** {valor_legivel(registro.get('UF_AG_PGD', ''))}")
        st.write(f"**Município Agência PGD:** {valor_legivel(registro.get('MUNICIPIO_AG_PGD', ''))}")

        st.markdown("### Marcadores sociais")
        st.write(f"**Dorme na rua:** {valor_legivel(registro.get('IND_DORMIR_RUA_MEMB', ''))}")
        st.write(f"**Família indígena:** {bool_legivel(registro.get('FAMILIA_INDIGENA', ''))}")
        st.write(f"**Família quilombola:** {bool_legivel(registro.get('FAMILIA_QUILOMBOLA', ''))}")
        st.write(f"**Constava na maciça anterior:** {bool_legivel(registro.get('FLAG_REF_MACICA_ANTERIOR', ''))}")

    with col2:
        st.markdown("### Dados do benefício")

        nb = formatar_nb_exibicao(registro.get("NU_NB", ""))
        tipo = str(registro.get("TIPO_REGISTRO", "")).strip()

        st.write(f"**Número do benefício:** {nb}")
        st.write(f"**Tipo do registro:** {tipo_registro_legivel(tipo)}")

        if tipo == "MEMBRO_FAMILIAR":
            st.info("Este registro representa um membro familiar. Os dados de benefício só aparecem quando existirem na própria linha.")
        elif tipo == "NAO_CADASTRADO":
            st.info("Este registro representa um beneficiário localizado na Maciça, mas não localizado no CadÚnico.")
        else:
            st.success("Este registro representa o beneficiário principal localizado no CadÚnico.")

        cs_especie = registro.get("CS_ESPECIE")
        st.write(
            f"**Espécie:** {descricao_especie(cs_especie) if valor_legivel(cs_especie, vazio='') else 'Não se aplica'}"
        )
        st.write(f"**Código Internacional de Doenças (CID):** {valor_legivel(registro.get('CID', ''), vazio='Não se aplica')}")
        st.write(f"**Descrição do CID:** {valor_legivel(registro.get('DESCRICAO_CID', ''), vazio='Não se aplica')}")
        st.write(f"**Tipo de despacho:** {valor_legivel(registro.get('TIPO_DESPACHO', ''), vazio='Não se aplica')}")
        st.write(f"**Data do despacho:** {data_ou_nao_informado(registro.get('DT_DESPACHO'))}")
        st.write(f"**Data de Entrada do Requerimento:** {data_ou_nao_informado(registro.get('DT_ENTRADA_REQUERIMENTO'))}")
        st.write(f"**Data de Início do Benefício:** {data_ou_nao_informado(registro.get('DT_INICIO_BENEFICIO'))}")
        st.write(f"**Participação em campanha:** {valor_legivel(registro.get('PARTICIPACAO_CAMPANHA', ''), vazio='Não informado')}")
        st.write(f"**Indicador CadÚnico:** {bool_legivel(registro.get('FLAG_CADUNICO', ''))}")
        st.write(f"**Competência:** {formatar_competencia(registro.get('NU_MES_REF', ''))}")


def exibir_download_pdf(registro, mensagem, chave):
    try:
        pdf_bytes = gerar_pdf_detalhamento_pessoa(
            registro=registro,
            mensagem_resultado=mensagem,
            usuario=usuario,
        )
    except PDFExportError as exc:
        st.warning(str(exc))
        return

    st.download_button(
        "Baixar detalhamento em PDF",
        data=pdf_bytes,
        file_name=nome_arquivo_pdf_detalhamento(registro),
        mime="application/pdf",
        key=f"download_pdf_grupo_{chave}",
        use_container_width=True,
    )


def exibir_familia(df_familia: pd.DataFrame):
    st.markdown("## Composição do grupo familiar")

    df_familia_ref = selecionar_referencia_grupo(
        df_familia,
        key="select_referencia_grupo_familiar",
    )
    qtd_pessoas = contar_pessoas_distintas(df_familia_ref)
    st.caption(
        f"{qtd_pessoas} {'pessoa localizada' if qtd_pessoas == 1 else 'pessoas localizadas'} "
        "na referência selecionada."
    )



    colunas_familia = [
        "Nome",
        "CPF",
        "Número do benefício",
        "Parentesco",
        "Tipo de Registro",
        "Situação no CadÚnico",
        "Código Familiar",
        "Competência",
    ]
    df_exibicao = dataframe_para_tabela(df_familia_ref, colunas_familia)

    st.dataframe(
        df_exibicao,
        use_container_width=True,
        hide_index=True
    )

    coluna_tipo = "TIPO_REGISTRO_STR" if "TIPO_REGISTRO_STR" in df_familia_ref.columns else "TIPO_REGISTRO"
    titulares = df_familia_ref[df_familia_ref[coluna_tipo] == "BENEFICIARIO_CADUNICO"]

    if not titulares.empty:
        titular = titulares.iloc[0]
        st.success(
            f"Beneficiário principal localizado no grupo: "
            f"{nome_registro(titular.to_dict())} | "
            f"Número do benefício: {formatar_nb_exibicao(titular.get('NU_NB'))}"
        )
    else:
        st.warning("Nenhum registro do tipo BENEFICIARIO_CADUNICO foi identificado dentro do grupo retornado.")

    return df_familia_ref


# =========================================================
# ESTADO
# =========================================================

if "resultado_consulta" not in st.session_state:
    st.session_state["resultado_consulta"] = pd.DataFrame()

if "mensagem_consulta" not in st.session_state:
    st.session_state["mensagem_consulta"] = ""

if "tipo_busca_realizada" not in st.session_state:
    st.session_state["tipo_busca_realizada"] = ""

if "valor_busca_realizada" not in st.session_state:
    st.session_state["valor_busca_realizada"] = ""

if "resultado_consulta_preparado" not in st.session_state:
    st.session_state["resultado_consulta_preparado"] = pd.DataFrame()
if "consulta_realizada_grupo" not in st.session_state:
    st.session_state["consulta_realizada_grupo"] = False
if "bloqueio_consulta_grupo" not in st.session_state:
    st.session_state["bloqueio_consulta_grupo"] = None
if "tempo_consulta_grupo" not in st.session_state:
    st.session_state["tempo_consulta_grupo"] = None


# =========================================================
# TELA
# =========================================================

st.title("🔎 Consulta de Grupo Familiar")
st.caption("Use esta página para linha do tempo de referências e detalhamento completo do grupo familiar.")

with st.sidebar:
    st.header("Filtros de consulta")

    tipo_busca = st.selectbox(
        "Tipo de busca",
        ["CPF", "Número do Benefício", "Código Familiar"]
    )

    valor_busca = st.text_input("Digite o valor da busca")

    col_btn1, col_btn2 = st.columns(2)
    pesquisar = col_btn1.button("Pesquisar", use_container_width=True)
    limpar = col_btn2.button("Limpar", use_container_width=True)

logout_button()

if limpar:
    st.session_state["resultado_consulta"] = pd.DataFrame()
    st.session_state["resultado_consulta_preparado"] = pd.DataFrame()
    st.session_state["mensagem_consulta"] = ""
    st.session_state["tipo_busca_realizada"] = ""
    st.session_state["valor_busca_realizada"] = ""
    st.session_state["consulta_realizada_grupo"] = False
    st.session_state["bloqueio_consulta_grupo"] = None
    st.session_state["tempo_consulta_grupo"] = None
    st.rerun()

bloqueio_consulta = st.session_state["bloqueio_consulta_grupo"]
if bloqueio_consulta:
    st.error(
        "A base está em carga sem índices disponíveis para consulta. "
        f"Competência em andamento: {bloqueio_consulta['competencia']}. "
        f"Fase atual: {bloqueio_consulta['fase']}. "
        "Aguarde a recriação dos índices para pesquisar novamente."
    )
    if usuario_eh_admin() and st.button("Liberar consultas agora", key="liberar_consulta_familia"):
        with st.spinner("Encerrando carga órfã e recriando índices..."):
            encerrar_cargas_em_andamento(
                "Carga marcada como erro manualmente para liberar consultas."
            )
            criar_indices()
        st.session_state["resultado_consulta"] = pd.DataFrame()
        st.session_state["resultado_consulta_preparado"] = pd.DataFrame()
        st.session_state["mensagem_consulta"] = ""
        st.session_state["tipo_busca_realizada"] = ""
        st.session_state["valor_busca_realizada"] = ""
        st.session_state["consulta_realizada_grupo"] = False
        st.session_state["bloqueio_consulta_grupo"] = None
        st.session_state["tempo_consulta_grupo"] = None
        st.success("Consultas liberadas. Tente pesquisar novamente.")
        st.rerun()
    st.stop()

if pesquisar:
    valor_busca = valor_busca.strip()
    st.session_state["mensagem_consulta"] = ""
    st.session_state["resultado_consulta"] = pd.DataFrame()
    st.session_state["resultado_consulta_preparado"] = pd.DataFrame()
    st.session_state["tipo_busca_realizada"] = ""
    st.session_state["valor_busca_realizada"] = valor_busca
    st.session_state["consulta_realizada_grupo"] = True
    st.session_state["bloqueio_consulta_grupo"] = None
    st.session_state["tempo_consulta_grupo"] = None
    inicio_pesquisa = time.perf_counter()
    status_pesquisa = st.empty()
    status_pesquisa.info("Pesquisa em andamento. Verificando a base local...")

    try:
        status_pesquisa.info("Pesquisa em andamento. Conferindo cargas e índices da base...")
        prontidao = verificar_prontidao_consulta()
        carga_em_andamento = prontidao["carga_em_andamento"]

        if prontidao["consulta_bloqueada"]:
            st.session_state["tempo_consulta_grupo"] = time.perf_counter() - inicio_pesquisa
            competencia = carga_em_andamento.get("competencia")
            fase = carga_em_andamento.get("fase_atual") or "não informada"
            st.session_state["consulta_realizada_grupo"] = False
            st.session_state["bloqueio_consulta_grupo"] = {
                "competencia": competencia,
                "fase": fase,
            }
            st.rerun()

        if prontidao["precisa_recriar_indices"]:
            status_pesquisa.info("Índices da base ausentes. Recuperando estrutura de consulta...")
            criar_indices()

        if tipo_busca == "CPF":
            valido, mensagem_erro = validar_cpf_input(valor_busca)
            if not valido:
                st.session_state["resultado_consulta"] = pd.DataFrame()
                st.error(mensagem_erro)
                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_grupo"] = tempo_total
                status_pesquisa.warning(
                    f"Pesquisa interrompida em {formatar_tempo_pesquisa(tempo_total)}. "
                    "Revise o valor informado."
                )
            else:
                cpf = normalizar_cpf(valor_busca)
                status_pesquisa.info(f"Pesquisa em andamento. Consultando CPF {formatar_cpf(cpf)}...")
                resultado = buscar_por_cpf(cpf)

                status_pesquisa.info("Pesquisa em andamento. Montando resultado...")
                resultado = preparar_resultado_consulta(resultado)
                st.session_state["resultado_consulta"] = resultado
                st.session_state["resultado_consulta_preparado"] = resultado
                st.session_state["tipo_busca_realizada"] = "CPF"

                try:
                    registrar_log_consulta(
                        user_id=usuario.get("id"),
                        username=usuario.get("username"),
                        nome_completo=usuario.get("nome_completo"),
                        tipo_consulta="CPF",
                        valor_pesquisado=cpf,
                        quantidade_resultados=len(resultado)
                    )
                except Exception as exc:
                    st.warning(f"Não foi possível registrar o log da consulta: {exc}")

                if resultado.empty:
                    primeira_ref, ultima_ref = obter_periodo_base()

                    st.session_state["mensagem_consulta"] = montar_mensagem_nao_encontrado(
                        nome="Pessoa consultada",
                        cpf=cpf,
                        primeira_ref_disponivel=primeira_ref,
                        ultima_ref_disponivel=ultima_ref
                    )

                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_grupo"] = tempo_total
                status_pesquisa.success(
                    f"Consulta concluída em {formatar_tempo_pesquisa(tempo_total)}."
                )

        elif tipo_busca == "Número do Benefício":
            valido, mensagem_erro = validar_nb_input(valor_busca)
            if not valido:
                st.session_state["resultado_consulta"] = pd.DataFrame()
                st.error(mensagem_erro)
                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_grupo"] = tempo_total
                status_pesquisa.warning(
                    f"Pesquisa interrompida em {formatar_tempo_pesquisa(tempo_total)}. "
                    "Revise o valor informado."
                )
            else:
                nb = normalizar_nb(valor_busca)
                status_pesquisa.info(f"Pesquisa em andamento. Consultando número do benefício {nb}...")
                resultado = buscar_familia_do_nb(nb)

                status_pesquisa.info("Pesquisa em andamento. Montando resultado...")
                resultado = preparar_resultado_consulta(resultado)
                st.session_state["resultado_consulta"] = resultado
                st.session_state["resultado_consulta_preparado"] = resultado
                st.session_state["tipo_busca_realizada"] = "NB"

                try:
                    registrar_log_consulta(
                        user_id=usuario.get("id"),
                        username=usuario.get("username"),
                        nome_completo=usuario.get("nome_completo"),
                        tipo_consulta="NB",
                        valor_pesquisado=nb,
                        quantidade_resultados=len(resultado)
                    )
                except Exception as exc:
                    st.warning(f"Não foi possível registrar o log da consulta: {exc}")

                if resultado.empty:
                    primeira_ref, ultima_ref = obter_periodo_base()

                    st.session_state["mensagem_consulta"] = (
                        f"Conforme cruzamento realizado entre a Maciça e os dados do CadÚnico, "
                        f"não foram identificados registros para o Número do Benefício {valor_busca}, "
                        f"no período de {referencia_formatada(primeira_ref)} a {referencia_formatada(ultima_ref)}."
                    )

                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_grupo"] = tempo_total
                status_pesquisa.success(
                    f"Consulta concluída em {formatar_tempo_pesquisa(tempo_total)}."
                )

        else:
            valido, mensagem_erro = validar_codigo_familiar_input(valor_busca)
            if not valido:
                st.session_state["resultado_consulta"] = pd.DataFrame()
                st.error(mensagem_erro)
                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_grupo"] = tempo_total
                status_pesquisa.warning(
                    f"Pesquisa interrompida em {formatar_tempo_pesquisa(tempo_total)}. "
                    "Revise o valor informado."
                )
            else:
                codigo_familiar = normalizar_codigo_familiar(valor_busca)
                status_pesquisa.info(
                    f"Pesquisa em andamento. Consultando código familiar {codigo_familiar}..."
                )
                resultado = buscar_por_codigo_familiar(codigo_familiar)

                status_pesquisa.info("Pesquisa em andamento. Montando resultado...")
                resultado = preparar_resultado_consulta(resultado)
                st.session_state["resultado_consulta"] = resultado
                st.session_state["resultado_consulta_preparado"] = resultado
                st.session_state["tipo_busca_realizada"] = "CODIGO_FAMILIAR"

                try:
                    registrar_log_consulta(
                        user_id=usuario.get("id"),
                        username=usuario.get("username"),
                        nome_completo=usuario.get("nome_completo"),
                        tipo_consulta="CODIGO_FAMILIAR",
                        valor_pesquisado=valor_busca,
                        quantidade_resultados=len(resultado)
                    )
                except Exception as exc:
                    st.warning(f"Não foi possível registrar o log da consulta: {exc}")

                if resultado.empty:
                    st.session_state["mensagem_consulta"] = f"Código familiar {valor_busca} não foi localizado na base."

                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_grupo"] = tempo_total
                status_pesquisa.success(
                    f"Consulta concluída em {formatar_tempo_pesquisa(tempo_total)}."
                )

    except Exception as exc:
        tempo_total = time.perf_counter() - inicio_pesquisa
        st.session_state["tempo_consulta_grupo"] = tempo_total
        status_pesquisa.error(
            f"Consulta interrompida após {formatar_tempo_pesquisa(tempo_total)}."
        )
        st.error(f"Erro ao executar a consulta: {exc}")

resultado = st.session_state["resultado_consulta_preparado"]
mensagem = st.session_state["mensagem_consulta"]
tipo_busca_realizada = st.session_state["tipo_busca_realizada"]
valor_busca_realizada = st.session_state["valor_busca_realizada"]
consulta_realizada = st.session_state["consulta_realizada_grupo"]
tempo_consulta = st.session_state.get("tempo_consulta_grupo")

st.markdown("## Resultados")

if consulta_realizada and tempo_consulta is not None:
    st.caption(f"Tempo de pesquisa: {formatar_tempo_pesquisa(tempo_consulta)}")

if consulta_realizada and mensagem:
    st.warning(mensagem)

if consulta_realizada and resultado.empty:
    if not mensagem:
        st.info("Nenhum registro encontrado.")
elif consulta_realizada:
    st.success(f"{len(resultado)} registro(s) encontrado(s).")

    primeira_ref, ultima_ref = obter_periodo_base()
    mensagem_formal = ""

    if tipo_busca_realizada == "CPF" and "TIPO_REGISTRO" in resultado.columns:
        coluna_tipo = "TIPO_REGISTRO_STR" if "TIPO_REGISTRO_STR" in resultado.columns else "TIPO_REGISTRO"
        beneficiarios = resultado[
            resultado[coluna_tipo] == "BENEFICIARIO_CADUNICO"
        ].copy()

        membros = resultado[
            resultado[coluna_tipo] == "MEMBRO_FAMILIAR"
        ].copy()

        cpf_pesquisado_normalizado = normalizar_cpf(valor_busca_realizada)

        if not beneficiarios.empty:
            beneficiarios = beneficiarios.sort_values("NU_MES_REF_NUM", ascending=False)
            registro_titular = beneficiarios.iloc[0].to_dict()

            membro_pesquisado = pd.DataFrame()

            if not membros.empty:
                coluna_cpf_pessoa = "CPF_PESSOA_NORM" if "CPF_PESSOA_NORM" in membros.columns else "NUM_CPF_PESSOA"
                if coluna_cpf_pessoa == "CPF_PESSOA_NORM":
                    membro_pesquisado = membros[membros[coluna_cpf_pessoa] == cpf_pesquisado_normalizado].copy()
                else:
                    membro_pesquisado = membros[
                        membros["NUM_CPF_PESSOA"].astype(str).str.replace(r"\D", "", regex=True) == cpf_pesquisado_normalizado
                    ].copy()

            if not membro_pesquisado.empty:
                registro_pesquisado = membro_pesquisado.iloc[0].to_dict()

                mensagem_formal = montar_mensagem_integrante_grupo_familiar(
                    registro_pesquisado=registro_pesquisado,
                    registro_titular=registro_titular,
                    primeira_ref_disponivel=primeira_ref,
                    ultima_ref_disponivel=ultima_ref
                )
            else:
                mensagem_formal = montar_mensagem_encontrado(
                    registro=registro_titular,
                    primeira_ref_disponivel=primeira_ref,
                    ultima_ref_disponivel=ultima_ref
                )

            st.info(mensagem_formal)

    elif "TIPO_REGISTRO" in resultado.columns:
        coluna_tipo = "TIPO_REGISTRO_STR" if "TIPO_REGISTRO_STR" in resultado.columns else "TIPO_REGISTRO"
        beneficiarios = resultado[
            resultado[coluna_tipo] == "BENEFICIARIO_CADUNICO"
        ].copy()

        if not beneficiarios.empty:
            beneficiarios = beneficiarios.sort_values("NU_MES_REF_NUM", ascending=False)
            registro_msg = beneficiarios.iloc[0].to_dict()

            mensagem_formal = montar_mensagem_encontrado(
                registro=registro_msg,
                primeira_ref_disponivel=primeira_ref,
                ultima_ref_disponivel=ultima_ref
            )
            st.info(mensagem_formal)

    if tipo_busca_realizada in ["CODIGO_FAMILIAR", "NB"] or (
        tipo_busca_realizada == "CPF" and len(resultado) > 1
    ):
        resultado_referencia = exibir_familia(resultado)

        if not resultado_referencia.empty:
            if len(resultado_referencia) == 1:
                registro_selecionado = resultado_referencia.iloc[0]
            else:
                st.markdown("### Selecionar pessoa para detalhamento")
                opcoes = montar_opcoes_registro(resultado_referencia, incluir_referencia=False)
                mapa_opcoes = {texto: idx for texto, idx in opcoes}

                opcao_escolhida = st.selectbox(
                    "Escolha uma pessoa da referência selecionada",
                    options=list(mapa_opcoes.keys()),
                    key="select_pessoa_familia"
                )
                registro_selecionado = resultado_referencia.loc[mapa_opcoes[opcao_escolhida]]

            with st.container(border=True):
                registro_pdf = (
                    registro_selecionado.to_dict()
                    if hasattr(registro_selecionado, "to_dict")
                    else registro_selecionado
                )
                exibir_detalhamento(registro_pdf)
                exibir_download_pdf(registro_pdf, mensagem_formal, "familia")

    else:


        colunas_tabela = [
            "Número do benefício",
            "CPF",
            "Nome",
            "Espécie",
            "Parentesco",
            "Tipo de Registro",
            "Situação no CadÚnico",
            "Município Maciça",
            "UF Maciça",
            "Competência",
        ]
        df_exibicao = dataframe_para_tabela(resultado, colunas_tabela)

        st.dataframe(
            df_exibicao,
            use_container_width=True,
            hide_index=True
        )

        if len(resultado) == 1:
            registro_selecionado = resultado.iloc[0]
        else:
            st.markdown("### Selecionar registro para detalhamento")
            opcoes = montar_opcoes_registro(resultado)
            mapa_opcoes = {texto: idx for texto, idx in opcoes}
            opcao_escolhida = st.selectbox(
                "Escolha um registro da lista",
                options=list(mapa_opcoes.keys())
            )
            registro_selecionado = resultado.loc[mapa_opcoes[opcao_escolhida]]

        registro_base_dict = (
            registro_selecionado.to_dict()
            if hasattr(registro_selecionado, "to_dict")
            else registro_selecionado
        )

        registros_mesma_pessoa = filtrar_mesma_pessoa(resultado, registro_base_dict)

        registro_por_referencia = selecionar_referencia_detalhe(
            registros_mesma_pessoa,
            key="select_competencia_detalhe",
        )
        if registro_por_referencia is not None:
            registro_selecionado = registro_por_referencia

        with st.container(border=True):
            registro_pdf = (
                registro_selecionado.to_dict()
                if hasattr(registro_selecionado, "to_dict")
                else registro_selecionado
            )
            exibir_detalhamento(registro_pdf)
            exibir_download_pdf(registro_pdf, mensagem_formal, "registro")
