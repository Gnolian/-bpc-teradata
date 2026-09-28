import streamlit as st

from app.services.sqlite_service import (
    SQLiteServiceError,
    alterar_propria_senha,
    alterar_senha_por_login,
    autenticar_usuario,
    criar_tabela_usuarios,
)


def init_auth_state():
    if "usuarios_schema_ok" not in st.session_state:
        criar_tabela_usuarios()
        st.session_state["usuarios_schema_ok"] = True

    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if "usuario_logado" not in st.session_state:
        st.session_state["usuario_logado"] = None

    if "troca_senha_obrigatoria" not in st.session_state:
        st.session_state["troca_senha_obrigatoria"] = False


def usuario_logado():
    return st.session_state.get("usuario_logado") or {}


def usuario_eh_admin() -> bool:
    usuario = usuario_logado()
    return usuario.get("perfil") == "admin"


def usuario_precisa_trocar_senha() -> bool:
    usuario = usuario_logado()
    return bool(st.session_state.get("troca_senha_obrigatoria")) or int(
        usuario.get("precisa_trocar_senha", 0) or 0
    ) == 1


def sidebar_navigation():
    if not st.session_state.get("autenticado"):
        return

    if usuario_precisa_trocar_senha():
        return

    st.sidebar.page_link("main.py", label="Início")
    st.sidebar.page_link("pages/1_Consulta_Pessoa.py", label="Consulta Pessoa")
    st.sidebar.page_link("pages/2_Consulta_Grupo_Familiar.py", label="Consulta Grupo Familiar")

    if usuario_eh_admin():
        st.sidebar.page_link("pages/3_Administracao.py", label="Administração")

    st.sidebar.divider()


def login_form():
    init_auth_state()

    if st.session_state["autenticado"]:
        return True

    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 1rem;
        }
        .stApp {
            background:
                radial-gradient(circle at 10% 18%, rgba(14, 116, 144, 0.20), transparent 25rem),
                radial-gradient(circle at 82% 20%, rgba(37, 99, 235, 0.18), transparent 27rem),
                linear-gradient(135deg, #020617 0%, #08111f 46%, #0b1628 100%);
        }
        header[data-testid="stHeader"] {
            background: transparent;
        }
        .scb-login-brand {
            max-width: 520px;
            padding: 3.1rem 0 1rem 0;
        }
        .scb-brand-icon {
            width: 3.15rem;
            height: 3.15rem;
            display: grid;
            place-items: center;
            border-radius: 8px;
            background: linear-gradient(135deg, #1d4ed8, #0ea5e9);
            color: #ffffff;
            font-size: 1.35rem;
            font-weight: 800;
            margin-bottom: 1.55rem;
            box-shadow: 0 18px 42px rgba(37, 99, 235, 0.24);
        }
        .scb-brand-kicker {
            color: #60a5fa;
            font-size: 0.82rem;
            font-weight: 800;
            text-transform: uppercase;
            margin-bottom: 0.65rem;
        }
        .scb-brand-title {
            color: #f8fafc;
            font-size: 3.55rem;
            line-height: 1.04;
            font-weight: 850;
            margin-bottom: 1rem;
        }
        .scb-brand-subtitle {
            color: #cbd5e1;
            font-size: 1.08rem;
            line-height: 1.52;
            max-width: 600px;
            margin: 0;
        }
        .scb-brand-badges {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1.35rem;
        }
        .scb-brand-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.38rem;
            border: 1px solid rgba(96, 165, 250, 0.22);
            background: rgba(15, 23, 42, 0.62);
            color: #dbeafe;
            border-radius: 8px;
            padding: 0.4rem 0.66rem;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .scb-brand-badge-icon {
            width: 1.12rem;
            height: 1.12rem;
            display: inline-grid;
            place-items: center;
            border-radius: 999px;
            background: rgba(96, 165, 250, 0.18);
            color: #bfdbfe;
            font-size: 0.75rem;
            line-height: 1;
        }
        .scb-form-heading {
            margin-bottom: 0.85rem;
        }
        .scb-form-kicker {
            color: #60a5fa;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            margin-bottom: 0.42rem;
        }
        .scb-form-heading h2 {
            color: #f8fafc;
            font-size: 1.55rem;
            line-height: 1.2;
            margin: 0 0 0.5rem 0;
        }
        .scb-form-heading p {
            color: #94a3b8;
            margin: 0;
        }
        div[data-testid="stForm"] {
            border-radius: 8px;
            border: 1px solid rgba(148, 163, 184, 0.22);
            background: rgba(15, 23, 42, 0.78);
            box-shadow: 0 26px 72px rgba(2, 6, 23, 0.34);
            padding: 1.25rem 1.35rem;
        }
        div[data-testid="stTextInput"] label {
            color: #e5e7eb;
            font-weight: 800;
        }
        div[data-testid="stTextInput"] {
            margin-bottom: 0.72rem;
        }
        div[data-testid="stTextInput"] div[data-baseweb="input"] {
            width: 100% !important;
            height: 3rem !important;
            min-height: 3rem !important;
            display: flex !important;
            align-items: center !important;
            overflow: hidden;
            background: #111827 !important;
            border: 1px solid rgba(148, 163, 184, 0.30) !important;
            border-radius: 8px !important;
            box-shadow: none !important;
            box-sizing: border-box;
            padding: 0 !important;
        }
        div[data-testid="stTextInput"] div[data-baseweb="input"] > div {
            height: 100% !important;
            min-height: 100% !important;
            display: flex !important;
            align-items: center !important;
            flex: 1 1 auto !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
            border-color: #60a5fa !important;
            box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.22) !important;
        }
        div[data-testid="stTextInput"] input {
            width: 100% !important;
            height: auto !important;
            min-height: 0 !important;
            display: block !important;
            align-self: center !important;
            margin: 0 !important;
            padding: 0 0.92rem !important;
            font-size: 1rem !important;
            line-height: 1.35rem !important;
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            color: #f8fafc !important;
            caret-color: #60a5fa !important;
            box-sizing: border-box;
            outline: none !important;
            box-shadow: none !important;
        }
        div[data-testid="stTextInput"] input:focus {
            outline: none !important;
            box-shadow: none !important;
        }
        div[data-testid="InputInstructions"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        div[data-testid="stTextInput"] div[data-baseweb="input"] button {
            height: 3rem !important;
            width: 3rem !important;
            min-width: 3rem !important;
            max-width: 3rem !important;
            flex: 0 0 3rem !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 0 !important;
            margin: 0 !important;
            background: transparent !important;
            color: #e2e8f0 !important;
            border: 0 !important;
            border-radius: 0 !important;
        }
        div[data-testid="stTextInput"] div[data-baseweb="input"] button:hover {
            background: rgba(96, 165, 250, 0.10) !important;
            color: #ffffff !important;
        }
        div[data-testid="stFormSubmitButton"] button {
            min-height: 3rem;
            border-radius: 8px;
            border: 1px solid #2563eb;
            background: #2563eb;
            color: #ffffff;
            font-weight: 700;
            transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
        }
        div[data-testid="stFormSubmitButton"] button:hover {
            border-color: #3b82f6;
            background: #3b82f6;
            transform: translateY(-1px);
        }
        div[data-testid="stExpander"] {
            max-width: 100%;
            margin-top: 0.72rem;
            margin-left: auto;
            margin-right: auto;
            border-radius: 8px;
            border: 0;
            background: transparent;
        }
        div[data-testid="stExpander"] details {
            border: 0;
        }
        div[data-testid="stExpander"] summary {
            color: #60a5fa;
            font-weight: 700;
            justify-content: center;
        }
        .scb-password-intro {
            color: #94a3b8;
            margin-bottom: 0.65rem;
            font-size: 0.92rem;
        }
        .scb-login-footer {
            max-width: 1180px;
            margin: 0.75rem auto 0 auto;
            color: #94a3b8;
            font-size: 0.82rem;
            text-align: center;
        }
        @media (max-width: 900px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
                padding-top: 1.25rem;
            }
            .scb-login-brand {
                padding: 0 0 1rem 0;
            }
            .scb-brand-title {
                font-size: 2.15rem;
            }
            div[data-testid="stExpander"] {
                max-width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col_info, col_form = st.columns([1.1, 0.9], gap="large")

    with col_info:
        st.markdown(
            """
            <div class="scb-login-brand">
                <div class="scb-brand-icon">⌂</div>
                <div class="scb-brand-kicker">Uso interno Portfolio</div>
                <div class="scb-brand-title">Sistema de Consulta de Beneficiários - SCB</div>
                <p class="scb-brand-subtitle">
                    Consulta institucional de pessoas, benefícios e grupos familiares,
                    com controle de acesso, rastreabilidade e auditoria.
                </p>
                <div class="scb-brand-badges">
                    <span class="scb-brand-badge"><span class="scb-brand-badge-icon">✓</span>Acesso individual</span>
                    <span class="scb-brand-badge"><span class="scb-brand-badge-icon">●</span>Dados protegidos</span>
                    <span class="scb-brand-badge"><span class="scb-brand-badge-icon">↗</span>Consultas auditadas</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_form:
        with st.form("form_login_scb"):
            st.markdown(
                """
                <div class="scb-form-heading">
                    <div class="scb-form-kicker">Acesso interno</div>
                    <h2>Entrar no sistema</h2>
                    <p>Informe suas credenciais para acessar o SCB.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            username = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)

        with st.expander("Alterar minha senha", expanded=False):
            st.markdown(
                """
                <div class="scb-password-intro">
                    Use esta opção se você recebeu uma senha padrão e quer definir a sua.
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.form("form_alterar_senha_login"):
                username_senha = st.text_input("Usuário", key="alterar_senha_username")
                senha_atual = st.text_input(
                    "Senha atual",
                    type="password",
                    key="alterar_senha_atual",
                )
                nova_senha = st.text_input(
                    "Nova senha",
                    type="password",
                    key="alterar_senha_nova",
                )
                confirmar_nova_senha = st.text_input(
                    "Confirmar nova senha",
                    type="password",
                    key="alterar_senha_confirmacao",
                )
                salvar_senha = st.form_submit_button(
                    "Salvar nova senha",
                    use_container_width=True,
                )

    if entrar:
        try:
            usuario = autenticar_usuario(username, senha)
        except SQLiteServiceError as exc:
            st.error(str(exc))
            return False

        if usuario:
            st.session_state["autenticado"] = True
            st.session_state["usuario_logado"] = usuario
            st.session_state["troca_senha_obrigatoria"] = int(
                usuario.get("precisa_trocar_senha", 0) or 0
            ) == 1
            st.success("Login realizado com sucesso.")
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos.")

    if salvar_senha:
        try:
            alterar_senha_por_login(
                username=username_senha,
                senha_atual=senha_atual,
                nova_senha=nova_senha,
                confirmar_nova_senha=confirmar_nova_senha,
            )
            st.success("Senha alterada com sucesso. Você já pode entrar com a nova senha.")
        except SQLiteServiceError as exc:
            st.error(str(exc))

    st.markdown(
        '<div class="scb-login-footer">Portfolio · Sistema de uso interno · Acesso monitorado</div>',
        unsafe_allow_html=True,
    )

    return False


def troca_senha_obrigatoria_form():
    usuario = usuario_logado()

    st.markdown("## Alteração obrigatória de senha")
    st.warning(
        "Por segurança, este usuário precisa trocar a senha inicial antes de acessar a aplicação."
    )
    st.caption(
        "A nova senha deve ter pelo menos 8 caracteres, ser diferente da senha atual "
        "e não pode ser a senha padrão."
    )

    senha_atual = st.text_input("Senha atual", type="password", key="troca_obrigatoria_atual")
    nova_senha = st.text_input("Nova senha", type="password", key="troca_obrigatoria_nova")
    confirmar_nova_senha = st.text_input(
        "Confirmar nova senha",
        type="password",
        key="troca_obrigatoria_confirmar",
    )

    if st.button("Salvar nova senha", use_container_width=True):
        try:
            alterar_propria_senha(
                user_id=usuario["id"],
                senha_atual=senha_atual,
                nova_senha=nova_senha,
                confirmar_nova_senha=confirmar_nova_senha,
            )
            usuario["precisa_trocar_senha"] = 0
            usuario["senha_alterada_em"] = "agora"
            st.session_state["usuario_logado"] = usuario
            st.session_state["troca_senha_obrigatoria"] = False
            st.success("Senha alterada com sucesso.")
            st.rerun()
        except SQLiteServiceError as exc:
            st.error(str(exc))

    if st.button("Sair", use_container_width=True, key="sair_troca_obrigatoria"):
        st.session_state["autenticado"] = False
        st.session_state["usuario_logado"] = None
        st.session_state["troca_senha_obrigatoria"] = False
        st.rerun()


def logout_button():
    if st.session_state.get("autenticado"):
        usuario = usuario_logado()
        nome = usuario.get("nome_completo", "")
        perfil = usuario.get("perfil", "")

        st.sidebar.markdown(
            """
            <style>
            div[data-testid="stSidebarUserContent"] {
                display: flex;
                flex-direction: column;
                min-height: calc(100vh - 5rem);
            }
            .sidebar-logout-spacer {
                flex: 1 1 auto;
                min-height: 1rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.sidebar.success(f"Logado como: {nome}")
        st.sidebar.caption(f"Perfil: {perfil}")
        st.sidebar.markdown('<div class="sidebar-logout-spacer"></div>', unsafe_allow_html=True)

        if st.sidebar.button("Sair", use_container_width=True):
            st.session_state["autenticado"] = False
            st.session_state["usuario_logado"] = None
            st.session_state["troca_senha_obrigatoria"] = False
            st.rerun()


def exigir_login():
    init_auth_state()

    if not st.session_state["autenticado"]:
        login_form()
        st.stop()

    if usuario_precisa_trocar_senha():
        troca_senha_obrigatoria_form()
        st.stop()


def exigir_admin():
    exigir_login()

    if not usuario_eh_admin():
        st.error("Acesso restrito. Esta página é permitida apenas para administradores.")
        st.stop()
