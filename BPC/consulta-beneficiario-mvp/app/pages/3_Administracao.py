import streamlit as st

from app.auth import exigir_admin, logout_button, sidebar_navigation
from app.services.sqlite_service import (
    listar_usuarios,
    criar_usuario,
    alterar_status_usuario,
    alterar_perfil_usuario,
    redefinir_senha_usuario,
    buscar_usuario_por_id,
    listar_logs_consultas_mascarados,
    SQLiteServiceError
)

st.set_page_config(
    page_title="Administração",
    page_icon="🔐",
    layout="wide"
)

exigir_admin()
sidebar_navigation()
logout_button()

st.title("🔐 Administração de Usuários")
st.caption("Área restrita para administradores")

tab1, tab2, tab3, tab4 = st.tabs([
    "Usuários cadastrados",
    "Criar usuário",
    "Gerenciar usuário",
    "Histórico de consultas"
])

with tab1:
    st.subheader("Lista de usuários")
    try:
        df_usuarios = listar_usuarios()

        if df_usuarios.empty:
            st.info("Nenhum usuário cadastrado.")
        else:
            df_exibicao = df_usuarios.copy()
            df_exibicao["ativo"] = df_exibicao["ativo"].map({1: "Sim", 0: "Não"})
            df_exibicao["precisa_trocar_senha"] = df_exibicao["precisa_trocar_senha"].map({1: "Sim", 0: "Não"})
            df_exibicao["perfil"] = df_exibicao["perfil"].str.capitalize()
            df_exibicao = df_exibicao.rename(columns={
                "id": "ID",
                "username": "Usuário",
                "nome_completo": "Nome completo",
                "perfil": "Perfil",
                "ativo": "Ativo",
                "precisa_trocar_senha": "Troca obrigatória",
                "senha_alterada_em": "Senha alterada em",
                "inativado_em": "Inativado em",
                "motivo_inativacao": "Motivo da inativação",
                "created_at": "Criado em"
            })

            st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Erro ao carregar usuários: {exc}")

with tab2:
    st.subheader("Criar novo usuário")

    with st.form("form_criar_usuario"):
        novo_username = st.text_input("Usuário")
        novo_nome = st.text_input("Nome completo")
        nova_senha = st.text_input("Senha", type="password")
        novo_perfil = st.selectbox("Perfil", ["usuario", "admin"])
        st.caption("O usuário será obrigado a trocar essa senha no primeiro acesso.")
        btn_criar = st.form_submit_button("Criar usuário", use_container_width=True)

    if btn_criar:
        try:
            criar_usuario(
                username=novo_username,
                nome_completo=novo_nome,
                senha=nova_senha,
                perfil=novo_perfil
            )
            st.success("Usuário criado com sucesso.")
            st.rerun()
        except SQLiteServiceError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Erro ao criar usuário: {exc}")

with tab3:
    st.subheader("Gerenciar usuário existente")

    try:
        df_usuarios = listar_usuarios()

        if df_usuarios.empty:
            st.info("Nenhum usuário disponível para gerenciamento.")
        else:
            opcoes = {
                f"{row['nome_completo']} | {row['username']} | perfil={row['perfil']} | ativo={row['ativo']}": row["id"]
                for _, row in df_usuarios.iterrows()
            }

            usuario_escolhido = st.selectbox("Selecione o usuário", list(opcoes.keys()))
            user_id = opcoes[usuario_escolhido]
            usuario = buscar_usuario_por_id(user_id)

            if usuario:
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("### Alterar status")
                    st.write(f"**Nome:** {usuario['nome_completo']}")
                    st.write(f"**Usuário:** {usuario['username']}")
                    st.write(f"**Perfil atual:** {usuario['perfil']}")
                    st.write(f"**Ativo:** {'Sim' if usuario['ativo'] == 1 else 'Não'}")
                    st.write(
                        f"**Troca de senha obrigatória:** "
                        f"{'Sim' if usuario.get('precisa_trocar_senha') == 1 else 'Não'}"
                    )
                    if usuario.get("motivo_inativacao"):
                        st.warning(f"Motivo da inativação: {usuario['motivo_inativacao']}")

                    novo_status = st.selectbox(
                        "Novo status",
                        options=[1, 0],
                        format_func=lambda x: "Ativo" if x == 1 else "Inativo",
                        key="status_usuario"
                    )

                    if st.button("Salvar status", use_container_width=True):
                        alterar_status_usuario(user_id, novo_status)
                        st.success("Status atualizado com sucesso.")
                        st.rerun()

                with col2:
                    st.markdown("### Alterar perfil / senha")

                    novo_perfil = st.selectbox(
                        "Novo perfil",
                        options=["usuario", "admin"],
                        index=0 if usuario["perfil"] == "usuario" else 1,
                        key="perfil_usuario"
                    )

                    if st.button("Salvar perfil", use_container_width=True):
                        alterar_perfil_usuario(user_id, novo_perfil)
                        st.success("Perfil atualizado com sucesso.")
                        st.rerun()

                    st.markdown("---")

                    nova_senha = st.text_input("Nova senha", type="password", key="nova_senha_usuario")

                    if st.button("Redefinir senha", use_container_width=True):
                        try:
                            redefinir_senha_usuario(user_id, nova_senha)
                            st.success(
                                "Senha redefinida com sucesso. "
                                "O usuário deverá trocar a senha no próximo acesso."
                            )
                            st.rerun()
                        except SQLiteServiceError as exc:
                            st.error(str(exc))

    except Exception as exc:
        st.error(f"Erro ao gerenciar usuários: {exc}")

with tab4:
    st.subheader("Histórico de consultas realizadas")
    st.caption("Os valores pesquisados são exibidos de forma mascarada nesta tela.")

    limite = st.selectbox("Quantidade de registros", [50, 100, 200, 500], index=1)

    try:
        df_logs = listar_logs_consultas_mascarados(limit=limite)

        if df_logs.empty:
            st.info("Nenhuma consulta registrada até o momento.")
        else:
            df_logs = df_logs.rename(columns={
                "id": "ID",
                "data_hora": "Data/Hora",
                "nome_completo": "Nome do usuário",
                "username": "Login",
                "tipo_consulta": "Tipo",
                "valor_pesquisado": "Valor pesquisado",
                "quantidade_resultados": "Qtd. resultados"
            })

            st.dataframe(df_logs, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Erro ao carregar histórico de consultas: {exc}")
