# Consulta de beneficiários — aplicação e carga local

> **Versão de portfólio:** nomes de bases e tabelas, caminhos e cabeçalhos institucionais foram substituídos por exemplos. As consultas ilustram a implementação e precisam de adaptação a fontes autorizadas. Não há dados reais incluídos.

Núcleo do sistema de consulta BPC: interface Streamlit, serviços SQLite e Teradata, geração de PDF e rotinas de preparação da base.

O objetivo técnico é manter a pesquisa de pessoas e grupos familiares independente da execução de grandes cargas na origem. A [apresentação do projeto](../README.md) explica o problema e as principais decisões de arquitetura.

## Fluxo de uso

1. Configurar o ambiente e inicializar o banco local.
2. Carregar as competências necessárias a partir da origem autorizada.
3. Acessar a aplicação com um usuário cadastrado.
4. Consultar pessoa ou grupo familiar e, quando necessário, gerar o relatório.

A inicialização cria estruturas; ela não fornece uma base de demonstração nem popula os benefícios.

## Componentes

| Componente | Responsabilidade |
| --- | --- |
| [app/main.py](app/main.py) | Entrada da aplicação e métricas |
| [app/auth.py](app/auth.py) | Login, estado de sessão e navegação por perfil |
| [app/pages](app/pages) | Consultas e administração |
| [app/services/sqlite_service.py](app/services/sqlite_service.py) | Persistência, consultas locais, usuários e controles de carga |
| [app/services/teradata_service.py](app/services/teradata_service.py) | Acesso à origem, lotes e tratamento de falhas |
| [app/services/base_loader.py](app/services/base_loader.py) | Coordenação do processamento de carga |
| [app/utils/pdf_export.py](app/utils/pdf_export.py) | Exportação em PDF |
| [scripts](scripts) | Preparação, atualização e manutenção |

## Decisões de implementação

- **Leitura em lotes e paginação por chave:** dão suporte ao processamento de grandes referências sem depender de uma única resposta integral.
- **Checkpoints de carga:** registram o avanço para orientar retomadas.
- **Novas tentativas controladas:** tratam falhas de conexão e operações temporariamente indisponíveis; há testes específicos para comportamento de autenticação.
- **Índices e métricas com scripts próprios:** permitem separar a transferência dos dados de etapas de preparação para consulta.
- **Dependências por finalidade:** `requirements/app.txt` atende à aplicação; `requirements/load.txt`, à carga; `requirements/dev.txt` reúne os dois conjuntos.

O SQLite simplifica a instalação local, mas exige gestão de disco, backups e concorrência. A cópia local não é uma sincronização em tempo real.

## Preparação

Execute os comandos nesta pasta, com Python 3.10 ou superior:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements/dev.txt
Copy-Item .env.example .env
```

Preencha localmente o `.env` conforme o cenário. O modelo lista as opções disponíveis, incluindo conexão Teradata, referências, parâmetros de carga, caminho SQLite e senha inicial de administração. Não use credenciais reais em exemplos publicados.

Para inicializar a estrutura local:

```powershell
python -m scripts.init_db
```

A criação do administrador depende da configuração da senha inicial. Para uma carga real, revise competências e opções de recriação/substituição antes de executar:

```powershell
python -m scripts.atualizar_base_sqlite
```

Para abrir a interface:

```powershell
python -m streamlit run app/main.py
```

Use o endereço exibido pelo Streamlit. A configuração de execução está em [.streamlit/config.toml](.streamlit/config.toml).

## Verificação

A suíte usa `unittest` e inclui cenários de conexão Teradata, carga direta e reparo de índices SQLite:

```powershell
python -m unittest discover -s tests
```

Esse comando é uma orientação de execução; não substitui a validação da carga no ambiente de destino.

## Documentação e escopo

- [Estrutura do projeto](docs/estrutura_projeto.md).
- [Regras de negócio](docs/regras_negocio.md).
- [Modelo de configuração](.env.example).

A versão disponível possui três páginas de funcionalidades além da entrada: pessoa, grupo familiar e administração. Não inclui dados sintéticos prontos nem uma demonstração pública hospedada. Para portfólio, publique código e documentação; mantenha bases, credenciais e resultados de consultas fora do Git.
