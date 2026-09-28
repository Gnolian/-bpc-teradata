import streamlit as st

st.set_page_config(
    page_title="Painel de Benefícios Assistenciais",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Painel de Benefícios Assistenciais")

st.markdown(
    """
Use o menu lateral para navegar entre as páginas:

1. **BPC Maciça - Folha de pagamento**
2. **BPC Cadastro Único - dados do cadastro**
3. **Campanhas cadastrais**
4. **Auxílio inclusão**
5. **Zika vírus**
6. **Mapas por UF**
7. **Mapas por município**
"""
)

st.info(
    "Os painéis foram reorganizados para separar a base principal da base resumida de revisão cadastral, "
    "melhorando a performance e evitando duplicidade de benefícios."
)