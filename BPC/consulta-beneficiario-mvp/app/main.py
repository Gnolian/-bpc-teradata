import streamlit as st

from app.auth import exigir_login, logout_button, sidebar_navigation, usuario_eh_admin
from app.services.sqlite_service import carregar_metricas
from app.utils.formatters import formatar_competencia, formatar_numero

st.set_page_config(
    page_title="SCB - Início",
    page_icon="📊",
    layout="wide",
)

exigir_login()
sidebar_navigation()
logout_button()

st.markdown(
    """
    <style>
    .card {
        padding: 1.2rem;
        border-radius: 8px;
        background: rgba(49, 51, 63, 0.20);
        border: 1px solid rgba(250, 250, 250, 0.08);
        box-shadow: 0 4px 14px rgba(0,0,0,0.08);
        min-height: 110px;
        margin-bottom: 1rem;
    }
    .card-title {
        font-size: 0.95rem;
        color: #b0b7c3;
        margin-bottom: 0.35rem;
    }
    .card-value {
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.1;
    }
    .titulo-principal {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .subtitulo {
        font-size: 1.15rem;
        font-weight: 600;
        margin-bottom: 0.1rem;
    }
    .subtitulo-menor {
        font-size: 1.05rem;
        font-weight: 500;
        color: #b0b7c3;
        margin-bottom: 1.2rem;
    }
    .bloco-info {
        padding: 1rem 1.2rem;
        border-radius: 8px;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        margin-top: 1rem;
    }
    .ref-base {
        padding: 0.9rem 1.1rem;
        border-radius: 8px;
        background: rgba(14, 116, 144, 0.18);
        border: 1px solid rgba(34, 211, 238, 0.22);
        color: #dbeafe;
        margin: 1.2rem 0 1rem 0;
        font-weight: 650;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="titulo-principal">Sistema de Consulta de Beneficiários - SCB</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="subtitulo">Ministério do Desenvolvimento e Assistência Social, Família e Combate à Fome</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="subtitulo-menor">Secretaria Nacional de Benefícios Assistenciais - SNBA</div>',
    unsafe_allow_html=True,
)

if usuario_eh_admin():
    st.info(
        "Você está logado como administrador. A página de Administração de Usuários está disponível no menu lateral."
    )

try:
    metricas = carregar_metricas()
    qtd_bpc_pcd = metricas.get("qtd_bpc_pcd", 0) or 0
    qtd_bpc_idoso = metricas.get("qtd_bpc_idoso", 0) or 0
    total_bpc = qtd_bpc_pcd + qtd_bpc_idoso

    st.markdown(
        f"""
        <div class="ref-base">
            Competência de referência da base: {formatar_competencia(metricas.get('competencia'))}
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    col4, col5, col6 = st.columns(3)

    with col1:
        st.markdown(
            f"""
            <div class="card">
                <div class="card-title">Quantidade BPC PCD</div>
                <div class="card-value">{formatar_numero(qtd_bpc_pcd)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="card">
                <div class="card-title">Quantidade BPC Idoso</div>
                <div class="card-value">{formatar_numero(qtd_bpc_idoso)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="card">
                <div class="card-title">Total BPC</div>
                <div class="card-value">{formatar_numero(total_bpc)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="card">
                <div class="card-title">Auxílio-Inclusão</div>
                <div class="card-value">{formatar_numero(metricas.get('qtd_auxilio_inclusao', 0))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col5:
        st.markdown(
            f"""
            <div class="card">
                <div class="card-title">RMV Total</div>
                <div class="card-value">{formatar_numero(metricas.get('qtd_rmv_total', 0))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col6:
        st.markdown(
            f"""
            <div class="card">
                <div class="card-title">Zika Vírus</div>
                <div class="card-value">{formatar_numero(metricas.get('qtd_zika_virus', 0))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="bloco-info">
            <div><strong>Última atualização da base local:</strong> {metricas.get('data_modificacao', 'Não informado')}</div>
            <div><strong>Total de registros importados:</strong> {formatar_numero(metricas.get('total_registros', 0))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Navegação")
    st.write("- Use a página **Consulta de Pessoa e Benefício** para pesquisar rapidamente por CPF ou número do benefício.")
    st.write("- Use a página **Consulta de Grupo Familiar** para linha do tempo das referências e detalhamento completo do grupo.")
    st.write("- Use a página **Administração** para gestão de usuários e histórico de consultas, se você for administrador.")

except Exception as exc:
    st.error(f"Erro ao carregar métricas: {exc}")
    st.warning(
        "Antes de usar a aplicação, execute novamente a carga da base SQLite com a nova estrutura da tabela."
    )
