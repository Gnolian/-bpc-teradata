# BPC por UF e CID — extração mensal e formatação

> **Versão de portfólio:** nomes de bases e tabelas, caminhos e cabeçalhos institucionais foram substituídos por exemplos. As consultas ilustram a implementação e precisam de adaptação a fontes autorizadas. Não há dados reais incluídos.

Rotinas para extrair quantitativos mensais de BPC para pessoas com deficiência por UF e Classificação Internacional de Doenças (CID), e transformar os resultados em planilhas padronizadas.

O objetivo é separar duas responsabilidades: obter os dados no Teradata e preparar o formato de entrega a partir de um modelo Excel.

## Etapas implementadas

1. [Extração](extrair_bpc_cid_202506_202607.py): percorre competências e grava um CSV por mês.
2. [Formatação](formatar_bpc_cid_202506_202607.py): utiliza os CSVs e um XLSX modelo para gerar planilhas formatadas.
3. [Consulta de apoio](consulta_bpc_cid.sql): disponibiliza a lógica SQL para leitura.

O intervalo padrão da extração vai de junho de 2025 a julho de 2026. O extrator aceita outras competências pela linha de comando; isso não garante disponibilidade das fontes para qualquer período.

## Decisões técnicas

| Escolha | Finalidade |
| --- | --- |
| Deduplicação com `ROW_NUMBER` e `QUALIFY` | Selecionar registros antes da agregação e evitar multiplicações indevidas |
| Leitura com `fetchmany` | Gravar a extração em lotes |
| Um CSV por competência | Separar entregas e permitir reprocessamento mensal |
| Extração e formatação independentes | Refazer a apresentação sem repetir a consulta |
| Edição de XLSX como ZIP/XML | Preservar componentes do modelo usando a biblioteca padrão do Python |
| Sobrescrita explícita | Controlar a substituição de arquivos existentes |

A UF utilizada é a da ordem pagadora, conforme a nota do relatório. Ela não deve ser interpretada automaticamente como UF de residência.

## Tecnologias

Python, SQL/Teradata, teradatasql, python-dotenv, CSV, ZIP e XML. O formatador manipula a estrutura do XLSX sem depender da automação COM do Excel.

## Execução

Use Python 3.10 ou superior e execute os comandos nesta pasta:

```powershell
python -m pip install teradatasql python-dotenv
python extrair_bpc_cid_202506_202607.py --help
python formatar_bpc_cid_202506_202607.py --help
```

Configure localmente `TD_HOST`, `TD_USER`, `TD_PASSWORD` e os demais parâmetros de conexão necessários em um `.env`.

Extração em um ambiente autorizado:

```powershell
python extrair_bpc_cid_202506_202607.py --env .env --inicio 202506 --fim 202607 --saida ".\outputs\csv"
```

Formatação com um modelo compatível, fornecido localmente:

```powershell
python formatar_bpc_cid_202506_202607.py --entrada ".\outputs\csv" --modelo ".\dados\modelo.xlsx" --saida ".\outputs\formatados"
```

O extrator possui `--testar-conexao`. Ambos os scripts possuem `--sobrescrever`. Use diretórios explícitos para substituir os caminhos padrão do ambiente de origem.

## Competências demonstradas e limites

SQL analítico, deduplicação, processamento por competência, exportação em lotes e manipulação de documentos estruturados.

O modelo Excel e dados sintéticos de demonstração não estão incluídos. A edição de XML depende da estrutura esperada do modelo. Embora a entrega seja agregada, dados relacionados à saúde exigem revisão de divulgação, especialmente em grupos pequenos; as extrações não fazem parte do portfólio público.
