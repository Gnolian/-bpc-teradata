# Engenharia de dados e automação para benefícios assistenciais

> **Versão de portfólio:** nomes de bases e tabelas, caminhos e cabeçalhos institucionais foram substituídos por exemplos. As consultas ilustram a implementação e precisam de adaptação a fontes autorizadas. Não há dados reais incluídos.

Projetos em Python e SQL voltados à consulta, análise e produção de informações sobre benefícios assistenciais. O conjunto reúne aplicações web, cargas de dados, painéis e automações de relatórios, com Teradata como origem em diferentes rotinas.

O objetivo deste portfólio é mostrar como transformei necessidades de consulta e processamento em código: preparar bases para uso local, organizar indicadores por território, automatizar tarefas recorrentes e conferir a consistência das entregas.

**Autor:** [Gnolian](https://github.com/Gnolian)

## Projetos

| Projeto | Problema abordado | Destaques técnicos |
| --- | --- | --- |
| [Consulta de beneficiários](BPC/README.md) | Consultar pessoas, benefícios e grupos familiares por referência mensal | Streamlit, SQLite, cargas com retomada, autenticação |
| [Painel de benefícios assistenciais](Perfil_Beneficiarios/README.md) | Explorar folha, cadastro e distribuição territorial | Pandas, Plotly, Parquet, particionamento por UF |
| [Análise de perfil e condições domiciliares](Perfil_Beneficiarios2/README.md) | Preparar gráficos e tabelas para análise do perfil dos beneficiários | Integração de bases, mapas, exportações HTML e Excel |
| [Relatórios físico-financeiros](Relatorio_fisico_financeiro/README.md) | Atualizar e conferir relatórios mensais de BPC e RMV | Excel COM, precisão monetária, validação e PDF |
| [Campanhas cadastrais](campanhas_teradata/README.md) | Executar uma sequência recorrente de SQLs e atualizar a base consolidada | Orquestração Python, SQL por data, logs e modo de simulação |
| [BPC por UF e CID](Script_bpc_cid/README.md) | Extrair séries mensais e padronizar planilhas de entrega | SQL analítico, leitura em lotes e edição de XLSX via XML |
| [Carga de referências mensais](Script_carregar_referencias/README.md) | Repetir a preparação de dados para diferentes competências | Modelo SQL, regras de calendário e transações por referência |

## Decisões que conectam os projetos

- **Separar processamento de consulta:** SQLite e Parquet permitem reutilizar dados preparados, sem depender de uma nova consulta à origem para cada interação.
- **Tratar o tempo como parte do modelo:** competências mensais aparecem nas cargas, nos filtros, nos nomes dos arquivos e nas validações.
- **Respeitar o formato da entrega:** interfaces web atendem à consulta interativa; Excel, PDF e HTML atendem à análise e ao compartilhamento de resultados.
- **Tornar falhas investigáveis:** logs, registros de divergências e controles de carga ajudam a localizar problemas e orientar reprocessamentos.
- **Adaptar a estratégia ao volume:** há leitura em lotes, divisão por UF e índices locais. Algumas rotinas ainda consolidam DataFrames em memória; essas limitações estão descritas nos projetos.

## Tecnologias

Python, SQL/Teradata, SQLite, Streamlit, Pandas, Plotly, Parquet, python-dotenv, ReportLab e automação do Microsoft Excel com pywin32. Cada README explica quais tecnologias são efetivamente usadas no respectivo projeto.

## Como explorar

Comece pelo sistema de consulta para conhecer a arquitetura de aplicação e carga. Nos relatórios físico-financeiros, veja as regras de conciliação e a integração com Excel. Os projetos de campanhas, referências e CID mostram automações de dados com objetivos mais delimitados.

Os READMEs apresentam o propósito, o funcionamento, as decisões observáveis no código, os requisitos de execução e os limites de cada solução. Não há métricas de desempenho ou economia de tempo medidas neste material.

## Dados e reprodução

As rotinas dependem de esquemas, bases ou modelos do ambiente de origem. Este conjunto não inclui uma demonstração completa com dados sintéticos. Clonar apenas o código não reproduz as bases nem os resultados.

Arquivos de credenciais, bases locais e exportações devem permanecer fora do Git. Para demonstrações públicas, use dados fictícios e modelos sem informações pessoais. As regras de `.gitignore` ajudam a excluir artefatos locais, mas não substituem a revisão do código e do histórico antes da publicação.
