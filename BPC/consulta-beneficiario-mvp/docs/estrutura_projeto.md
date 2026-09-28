# Estrutura do projeto

## Aplicacao

- `app/main.py`: pagina inicial com metricas da base local.
- `app/pages/1_Consulta.py`: tela de pesquisa e detalhamento.
- `app/pages/2_Administracao.py`: usuarios e historico de consultas.
- `app/auth.py`: controle de login e permissao.

## Servicos

- `app/services/sqlite_service.py`: acesso ao SQLite local, consultas, indices, usuarios e logs.
- `app/services/teradata_service.py`: conexao e leitura do Teradata.
- `app/services/base_loader.py`: montagem das tarefas de carga.

## Scripts operacionais

- `scripts/atualizar_base_sqlite.py`: carga da base local.
- `scripts/init_db.py`: inicializacao das tabelas locais.
- `scripts/criar_usuario.py`: criacao de usuarios pelo terminal.
- `scripts/validar_202510.py`: validacao operacional especifica.

## Dependencias

- `requirements/app.txt`: dependencias da interface Streamlit.
- `requirements/load.txt`: dependencias da carga Teradata.
- `requirements/dev.txt`: ponto de entrada para dependencias futuras de desenvolvimento.
- `requirements.txt`: instala as dependencias principais da aplicacao e da carga.

## Dados sensiveis

Nao versionar `.env`, `secrets.toml`, bancos SQLite, exportacoes ou dumps. Use
`.env.example` como modelo sem preencher credenciais reais.
