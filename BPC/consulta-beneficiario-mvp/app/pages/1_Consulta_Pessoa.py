import time

import pandas as pd
import streamlit as st

from app.auth import exigir_login, logout_button, sidebar_navigation, usuario_eh_admin, usuario_logado
from app.services.sqlite_service import (
    buscar_registro_cadunico_por_cpf,
    buscar_registro_cadunico_por_nb,
    buscar_registro_pessoa_por_cpf,
    buscar_registro_por_nb,
    criar_indices,
    encerrar_cargas_em_andamento,
    obter_periodo_competencias_disponiveis,
    registrar_log_consulta,
    verificar_prontidao_consulta,
)
from app.utils.formatters import (
    descricao_especie,
    formatar_codigo_familiar_exibicao,
    formatar_competencia,
    formatar_cpf,
    formatar_data_br,
    formatar_numero_inteiro,
    normalizar_cpf,
    normalizar_nb,
    valor_legivel,
)
from app.utils.pdf_export import (
    PDFExportError,
    gerar_pdf_detalhamento_pessoa,
    nome_arquivo_pdf_detalhamento,
)
from app.utils.validators import validar_cpf_input, validar_nb_input

st.set_page_config(
    page_title="SCB - Consulta de Pessoa",
    page_icon="📋",
    layout="wide",
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

    div[data-baseweb="select"] > div,
    .stTextInput input {
        background-color: #111827;
        color: #f8fafc;
        border: 1px solid rgba(255,255,255,0.12);
    }

    .stButton > button {
        background-color: #1d4ed8;
        color: white;
        border: none;
        border-radius: 8px;
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

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 8px;
        border-color: rgba(148,163,184,0.18);
        background: rgba(15,23,42,0.52);
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
    unsafe_allow_html=True,
)


def bool_legivel(valor):
    if str(valor) == "1":
        return "Sim"
    if str(valor) == "0":
        return "Não"
    return "Não informado"


def formatar_tempo_pesquisa(segundos):
    if segundos is None:
        return ""
    if segundos < 1:
        return f"{segundos:.2f}s"
    if segundos < 60:
        return f"{segundos:.1f}s"
    minutos, resto = divmod(segundos, 60)
    return f"{int(minutos)}min {resto:.0f}s"


def formatar_nb_exibicao(valor):
    texto = "" if valor is None else str(valor).strip()
    if texto.lower() in ("", "nan", "none"):
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
    return valor_legivel(
        registro.get("NOM_PESSOA") or registro.get("NM_TIT_BENEF_T"),
        vazio="Não informado",
    )


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


def referencia_numero(valor):
    ref = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    if pd.isna(ref):
        return None
    return int(ref)


def referencia_formatada(valor):
    ref = referencia_numero(valor)
    if ref is None:
        return "Não informado"
    return formatar_competencia(ref)


def obter_periodo_base():
    return obter_periodo_competencias_disponiveis()


def complemento_bpc_legivel(cs_especie):
    valor = "" if cs_especie is None else str(cs_especie).strip()
    if valor.endswith(".0"):
        valor = valor[:-2]

    mapa = {
        "87": "à Pessoa com Deficiência (BPC/PCD)",
        "88": "à Pessoa Idosa (BPC/Idoso)",
    }
    return mapa.get(valor)


def descricao_beneficio_formal(registro):
    complemento_bpc = complemento_bpc_legivel(registro.get("CS_ESPECIE"))
    if complemento_bpc:
        return f"Benefício de Prestação Continuada {complemento_bpc}"
    return descricao_especie(registro.get("CS_ESPECIE"))


def preparar_resultado_consulta(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    preparado = df.copy()
    if "TIPO_REGISTRO" in preparado.columns:
        preparado["TIPO_REGISTRO_STR"] = preparado["TIPO_REGISTRO"].fillna("").astype(str)
    else:
        preparado["TIPO_REGISTRO_STR"] = ""

    if "NU_MES_REF" in preparado.columns:
        preparado["NU_MES_REF_NUM"] = pd.to_numeric(preparado["NU_MES_REF"], errors="coerce")
    else:
        preparado["NU_MES_REF_NUM"] = pd.NA

    return preparado.sort_values(
        by=["NU_MES_REF_NUM"],
        ascending=False,
        kind="stable",
    )


def selecionar_registro_principal(resultado: pd.DataFrame):
    if resultado.empty:
        return None

    candidatos = resultado[
        resultado["TIPO_REGISTRO_STR"].isin(["BENEFICIARIO_CADUNICO", "NAO_CADASTRADO"])
    ]
    if not candidatos.empty:
        return candidatos.iloc[0].to_dict()

    return resultado.iloc[0].to_dict()


def montar_mensagem_beneficiario(registro, primeira_ref_disponivel, ultima_ref_disponivel):
    nome = nome_registro(registro)
    cpf = formatar_cpf(cpf_registro(registro))
    beneficio = descricao_beneficio_formal(registro)
    dib = formatar_data_br(registro.get("DT_INICIO_BENEFICIO")) or "não informada"
    ultima_ref_registro = referencia_numero(registro.get("NU_MES_REF"))
    ultima_ref_base = referencia_numero(ultima_ref_disponivel)
    ultima_ref_apareceu = referencia_formatada(ultima_ref_registro)
    ultima_ref_base_fmt = referencia_formatada(ultima_ref_base)
    periodo = (
        f"{referencia_formatada(primeira_ref_disponivel)} a "
        f"{referencia_formatada(ultima_ref_disponivel)}"
    )
    esta_na_ultima_ref = (
        ultima_ref_registro is not None
        and ultima_ref_base is not None
        and ultima_ref_registro == ultima_ref_base
    )
    tipo = str(registro.get("TIPO_REGISTRO") or "").strip()
    nao_cadastrado = tipo == "NAO_CADASTRADO"
    nao_cadastrado_confirmado = nao_cadastrado and not registro_macica_provisoria(registro)

    if esta_na_ultima_ref:
        if nao_cadastrado_confirmado:
            return (
                f"Segundo cruzamento realizado na Maciça, {nome}, CPF nº {cpf}, "
                f"consta como titular beneficiário(a) do {beneficio}, mas não foi localizado(a) "
                f"no CadÚnico, com Data de Início do Benefício (DIB) em {dib}, "
                f"presente na última referência carregada ({ultima_ref_base_fmt}), "
                f"no período analisado de {periodo}."
            )

        return (
            f"Segundo cruzamento realizado entre a Maciça e os dados do CadÚnico, "
            f"{nome}, CPF nº {cpf}, consta como titular beneficiário(a) do {beneficio}, "
            f"com Data de Início do Benefício (DIB) em {dib}, presente na última referência "
            f"carregada ({ultima_ref_base_fmt}), no período analisado de {periodo}."
        )

    if nao_cadastrado_confirmado:
        return (
            f"Segundo cruzamento realizado na Maciça, {nome}, CPF nº {cpf}, "
            f"FOI beneficiário(a) do {beneficio}, mas não foi localizado(a) no CadÚnico, "
            f"com Data de Início do Benefício (DIB) em {dib} e último recebimento em "
            f"{ultima_ref_apareceu}, no período analisado de {periodo}."
        )

    return (
        f"Segundo cruzamento realizado entre a Maciça e os dados do CadÚnico, "
        f"{nome}, CPF nº {cpf}, FOI beneficiário(a) do {beneficio}, com Data de Início "
        f"do Benefício (DIB) em {dib} e último recebimento em {ultima_ref_apareceu}, "
        f"no período analisado de {periodo}."
    )


def montar_mensagem_nao_beneficiario(registro, primeira_ref_disponivel, ultima_ref_disponivel):
    periodo = (
        f"{referencia_formatada(primeira_ref_disponivel)} a "
        f"{referencia_formatada(ultima_ref_disponivel)}"
    )
    return (
        f"Segundo cruzamento realizado entre a Maciça e os dados do CadÚnico, "
        f"{nome_registro(registro)}, CPF nº {formatar_cpf(cpf_registro(registro))}, "
        f"não figura como titular beneficiário(a) do BPC no período analisado de {periodo}. "
        "A pessoa foi localizada apenas como integrante de grupo familiar."
    )


def montar_mensagem_sem_registro(tipo_busca, valor_busca, primeira_ref, ultima_ref):
    periodo = f"{referencia_formatada(primeira_ref)} a {referencia_formatada(ultima_ref)}"
    if tipo_busca == "CPF":
        return (
            f"Conforme cruzamento realizado entre a Maciça e os dados do CadÚnico, "
            f"não foram identificados registros para o CPF nº {formatar_cpf(valor_busca)}, "
            f"no período de {periodo}."
        )
    return (
        f"Conforme cruzamento realizado entre a Maciça e os dados do CadÚnico, "
        f"não foram identificados registros para o Número do Benefício {valor_busca}, "
        f"no período de {periodo}."
    )


def montar_mensagem_resultado(registro, primeira_ref, ultima_ref):
    tipo = str(registro.get("TIPO_REGISTRO") or "").strip()
    if tipo in {"BENEFICIARIO_CADUNICO", "NAO_CADASTRADO"}:
        return montar_mensagem_beneficiario(registro, primeira_ref, ultima_ref)
    return montar_mensagem_nao_beneficiario(registro, primeira_ref, ultima_ref)


def selecionar_registro_detalhamento(registro_atual, registro_cadunico):
    if not registro_atual:
        return None
    return registro_cadunico or registro_atual


def exibir_detalhamento(registro):
    st.markdown("## Detalhamento da pessoa pesquisada")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Dados da pessoa")
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

    with col2:
        st.markdown("### Dados do benefício")
        tipo = str(registro.get("TIPO_REGISTRO", "")).strip()
        st.write(f"**Número do benefício:** {formatar_nb_exibicao(registro.get('NU_NB', ''))}")
        st.write(f"**Tipo do registro:** {tipo_registro_legivel(tipo)}")

        if tipo == "MEMBRO_FAMILIAR":
            st.info("Este registro representa um membro familiar. Os dados de benefício só aparecem quando existirem na própria linha.")
        elif tipo == "NAO_CADASTRADO":
            if registro_macica_provisoria(registro):
                st.info("Este registro representa um beneficiário localizado na Maciça.")
            else:
                st.info("Este registro representa um beneficiário localizado na Maciça, mas não localizado no CadÚnico.")
        else:
            st.success("Este registro representa o beneficiário principal localizado no CadÚnico.")

        cs_especie = registro.get("CS_ESPECIE")
        st.write(f"**Espécie:** {descricao_especie(cs_especie) if valor_legivel(cs_especie, vazio='') else 'Não se aplica'}")
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
        key=f"download_pdf_pessoa_{chave}",
        use_container_width=True,
    )


def registrar_log_sem_interromper(tipo_consulta, valor_pesquisado, quantidade_resultados):
    try:
        registrar_log_consulta(
            user_id=usuario.get("id"),
            username=usuario.get("username"),
            nome_completo=usuario.get("nome_completo"),
            tipo_consulta=tipo_consulta,
            valor_pesquisado=valor_pesquisado,
            quantidade_resultados=quantidade_resultados,
        )
    except Exception:
        pass


if "resultado_consulta_pessoa" not in st.session_state:
    st.session_state["resultado_consulta_pessoa"] = pd.DataFrame()
if "mensagem_consulta_pessoa" not in st.session_state:
    st.session_state["mensagem_consulta_pessoa"] = ""
if "registro_detalhe_pessoa" not in st.session_state:
    st.session_state["registro_detalhe_pessoa"] = None
if "tipo_busca_realizada_pessoa" not in st.session_state:
    st.session_state["tipo_busca_realizada_pessoa"] = ""
if "valor_busca_realizada_pessoa" not in st.session_state:
    st.session_state["valor_busca_realizada_pessoa"] = ""
if "consulta_realizada_pessoa" not in st.session_state:
    st.session_state["consulta_realizada_pessoa"] = False
if "bloqueio_consulta_pessoa" not in st.session_state:
    st.session_state["bloqueio_consulta_pessoa"] = None
if "tempo_consulta_pessoa" not in st.session_state:
    st.session_state["tempo_consulta_pessoa"] = None


def limpar_estado_consulta_pessoa():
    st.session_state["resultado_consulta_pessoa"] = pd.DataFrame()
    st.session_state["mensagem_consulta_pessoa"] = ""
    st.session_state["registro_detalhe_pessoa"] = None
    st.session_state["tipo_busca_realizada_pessoa"] = ""
    st.session_state["valor_busca_realizada_pessoa"] = ""
    st.session_state["consulta_realizada_pessoa"] = False
    st.session_state["bloqueio_consulta_pessoa"] = None
    st.session_state["tempo_consulta_pessoa"] = None


st.title("Consulta de Pessoa e Benefício")
st.caption("Pesquisa enxuta para verificar a pessoa consultada e detalhar apenas o registro localizado.")

with st.sidebar:
    st.header("Filtros de consulta")
    tipo_busca = st.selectbox("Tipo de busca", ["CPF", "Número do Benefício"])
    valor_busca = st.text_input("Digite o valor da busca")
    col_btn1, col_btn2 = st.columns(2)
    pesquisar = col_btn1.button("Pesquisar", use_container_width=True)
    limpar = col_btn2.button("Limpar", use_container_width=True)

logout_button()

if limpar:
    limpar_estado_consulta_pessoa()
    st.rerun()

bloqueio_consulta = st.session_state["bloqueio_consulta_pessoa"]
if bloqueio_consulta:
    st.error(
        "A base está em carga sem índices disponíveis para consulta. "
        f"Competência em andamento: {bloqueio_consulta['competencia']}. "
        f"Fase atual: {bloqueio_consulta['fase']}. "
        "Aguarde a recriação dos índices para pesquisar novamente."
    )
    if usuario_eh_admin() and st.button("Liberar consultas agora", key="liberar_consulta_pessoa"):
        with st.spinner("Encerrando carga órfã e recriando índices..."):
            encerrar_cargas_em_andamento(
                "Carga marcada como erro manualmente para liberar consultas."
            )
            criar_indices()
        limpar_estado_consulta_pessoa()
        st.success("Consultas liberadas. Tente pesquisar novamente.")
        st.rerun()
    st.stop()

if pesquisar:
    valor_busca = valor_busca.strip()
    limpar_estado_consulta_pessoa()
    st.session_state["valor_busca_realizada_pessoa"] = valor_busca
    inicio_pesquisa = time.perf_counter()
    status_pesquisa = st.empty()
    status_pesquisa.info("Pesquisa em andamento. Verificando a base local...")

    try:
        status_pesquisa.info("Pesquisa em andamento. Conferindo cargas e índices da base...")
        prontidao = verificar_prontidao_consulta()
        carga_em_andamento = prontidao["carga_em_andamento"]

        if prontidao["consulta_bloqueada"]:
            st.session_state["tempo_consulta_pessoa"] = time.perf_counter() - inicio_pesquisa
            competencia = carga_em_andamento.get("competencia")
            fase = carga_em_andamento.get("fase_atual") or "não informada"
            st.session_state["bloqueio_consulta_pessoa"] = {
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
                st.error(mensagem_erro)
                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_pessoa"] = tempo_total
                status_pesquisa.warning(
                    f"Pesquisa interrompida em {formatar_tempo_pesquisa(tempo_total)}. "
                    "Revise o valor informado."
                )
            else:
                cpf = normalizar_cpf(valor_busca)
                status_pesquisa.info(f"Pesquisa em andamento. Consultando CPF {formatar_cpf(cpf)}...")
                registro = buscar_registro_pessoa_por_cpf(cpf)
                registro_cadunico = buscar_registro_cadunico_por_cpf(cpf) if registro else None
                registro_detalhe = selecionar_registro_detalhamento(registro, registro_cadunico)

                status_pesquisa.info("Pesquisa em andamento. Montando resultado...")
                resultado = pd.DataFrame([registro]) if registro else pd.DataFrame()
                primeira_ref, ultima_ref = obter_periodo_base()

                st.session_state["resultado_consulta_pessoa"] = resultado
                st.session_state["registro_detalhe_pessoa"] = registro_detalhe
                st.session_state["tipo_busca_realizada_pessoa"] = "CPF"
                st.session_state["consulta_realizada_pessoa"] = True
                st.session_state["mensagem_consulta_pessoa"] = (
                    montar_mensagem_resultado(registro, primeira_ref, ultima_ref)
                    if registro
                    else montar_mensagem_sem_registro("CPF", cpf, primeira_ref, ultima_ref)
                )

                registrar_log_sem_interromper("CPF_PESSOA", cpf, 1 if registro else 0)
                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_pessoa"] = tempo_total
                status_pesquisa.success(
                    f"Consulta concluída em {formatar_tempo_pesquisa(tempo_total)}."
                )
        else:
            valido, mensagem_erro = validar_nb_input(valor_busca)
            if not valido:
                st.error(mensagem_erro)
                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_pessoa"] = tempo_total
                status_pesquisa.warning(
                    f"Pesquisa interrompida em {formatar_tempo_pesquisa(tempo_total)}. "
                    "Revise o valor informado."
                )
            else:
                nb = normalizar_nb(valor_busca)
                status_pesquisa.info(f"Pesquisa em andamento. Consultando número do benefício {nb}...")
                registro = buscar_registro_por_nb(nb)
                registro_cadunico = buscar_registro_cadunico_por_nb(nb) if registro else None
                registro_detalhe = selecionar_registro_detalhamento(registro, registro_cadunico)

                status_pesquisa.info("Pesquisa em andamento. Montando resultado...")
                resultado = pd.DataFrame([registro]) if registro else pd.DataFrame()
                primeira_ref, ultima_ref = obter_periodo_base()

                st.session_state["resultado_consulta_pessoa"] = resultado
                st.session_state["registro_detalhe_pessoa"] = registro_detalhe
                st.session_state["tipo_busca_realizada_pessoa"] = "NB"
                st.session_state["consulta_realizada_pessoa"] = True
                st.session_state["mensagem_consulta_pessoa"] = (
                    montar_mensagem_resultado(registro, primeira_ref, ultima_ref)
                    if registro
                    else montar_mensagem_sem_registro("NB", nb, primeira_ref, ultima_ref)
                )

                registrar_log_sem_interromper("NB_PESSOA", nb, 1 if registro else 0)
                tempo_total = time.perf_counter() - inicio_pesquisa
                st.session_state["tempo_consulta_pessoa"] = tempo_total
                status_pesquisa.success(
                    f"Consulta concluída em {formatar_tempo_pesquisa(tempo_total)}."
                )
    except Exception as exc:
        tempo_total = time.perf_counter() - inicio_pesquisa
        st.session_state["tempo_consulta_pessoa"] = tempo_total
        status_pesquisa.error(
            f"Consulta interrompida após {formatar_tempo_pesquisa(tempo_total)}."
        )
        st.error(f"Erro ao executar a consulta: {exc}")

if st.session_state["consulta_realizada_pessoa"]:
    st.markdown("## Resultado")
    mensagem = st.session_state["mensagem_consulta_pessoa"]
    registro = st.session_state["registro_detalhe_pessoa"]
    tempo_consulta = st.session_state.get("tempo_consulta_pessoa")

    if tempo_consulta is not None:
        st.caption(f"Tempo de pesquisa: {formatar_tempo_pesquisa(tempo_consulta)}")

    if mensagem:
        st.info(mensagem)

    if registro:
        with st.container(border=True):
            exibir_detalhamento(registro)
            exibir_download_pdf(registro, mensagem, "resultado")
