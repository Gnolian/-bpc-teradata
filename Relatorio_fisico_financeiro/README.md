# Automação de relatórios físico-financeiros — BPC e RMV

> **Versão de portfólio:** nomes de bases e tabelas, caminhos e cabeçalhos institucionais foram substituídos por exemplos. As consultas ilustram a implementação e precisam de adaptação a fontes autorizadas. Não há dados reais incluídos.

Scripts para preparar e conferir relatórios mensais de quantidade de benefícios e recursos pagos do Benefício de Prestação Continuada (BPC) e da Renda Mensal Vitalícia (RMV).

O objetivo é organizar em um fluxo programável a consulta dos dados, a atualização de modelos Excel, a conferência dos totais e a geração de PDFs.

## O que os scripts fazem

1. Definem o contexto da competência mensal.
2. Geram SQLs e, opcionalmente, executam consultas no Teradata.
3. Leem os CSVs e verificam quantidades e valores.
4. Atualizam quadros municipais, estaduais, regionais e nacionais em modelos Excel.
5. Registram divergências e validam as planilhas preenchidas.
6. Exportam PDFs conforme as regras de cada relatório.

São tratadas nove métricas: quantidades de benefícios, valores pagos no mês e valores acumulados no ano, separados entre pessoas com deficiência, idosos e total.

## Decisões técnicas

| Decisão | Motivo técnico atendido |
| --- | --- |
| `Decimal` e arredondamento por centavos | Representar valores monetários durante cálculos e comparações |
| Associação por código IBGE | Relacionar resultados às linhas das planilhas sem depender apenas da posição |
| Automação Excel COM | Trabalhar com modelos existentes e com a exportação do próprio Excel |
| Backup antes da atualização, por padrão | Preservar uma cópia dos arquivos anteriores ao processamento |
| Validação de CSV e de Excel | Conferir tanto a entrada quanto o preenchimento final |
| Argumentos de linha de comando | Permitir trocar competência e diretórios sem editar todo o script |

A escolha de COM vincula a atualização das planilhas ao Windows com Microsoft Excel instalado. Não é uma rotina de exportação independente do Excel.

## Particularidades da RMV

[RMV.py](RMV.py) exporta somente o PDF do quadro Brasil/UF. Registros sem localização são separados em CSV de auditoria. Divergências entre município e UF são tratadas como avisos nessa versão, enquanto outras inconsistências podem ser erros bloqueantes.

Por padrão, erros de validação impedem a geração de PDFs. Existem opções explícitas para continuar com erros ou gerar PDF nessas condições; portanto, os logs e o status final fazem parte da interpretação da entrega.

## Tecnologias e arquivos

**Python, SQL/Teradata, pywin32, Excel COM, CSV, JSON e API de localidades do IBGE.**

- [BPC.py](BPC.py): fluxo do relatório BPC.
- [RMV.py](RMV.py): fluxo do relatório RMV.
- [executar_RMV_FINAL_202607.bat](executar_RMV_FINAL_202607.bat): atalho local específico de uma competência; revise os caminhos antes de usar.

## Preparação e execução

Use Python 3.10 ou superior. Para atualizar planilhas, é necessário Windows, Excel e pywin32. Para executar consultas, também é necessário o driver Python do Teradata:

```powershell
python -m pip install pywin32 teradatasql
python RMV.py --help
python BPC.py --help
```

Exemplo de validação de CSVs já preparados, com diretório local ilustrativo:

```powershell
python RMV.py --ref 202607 --raiz ".\dados\RMV" --validar-somente-csv
```

Esse comando exige os CSVs na estrutura esperada. O modo de validação dispensa abrir o Excel. Para executar as consultas, configure as variáveis de ambiente `TERADATA_HOST`, `TERADATA_USER` e `TERADATA_PASSWORD` e utilize a opção `--executar-consultas`. Os scripts leem essas variáveis do processo; não presumem o carregamento automático de um `.env`.

As opções `--consultas-dir`, `--excel-dir` e `--pdf-dir` permitem ajustar os diretórios. A atualização completa altera planilhas e exige modelos compatíveis.

## Valor para o portfólio e limites

O projeto demonstra integração com um processo baseado em planilhas, precisão monetária, conciliação geográfica e rastreabilidade de divergências.

Modelos Excel, resultados reais e uma massa sintética de demonstração não acompanham o código. Os layouts esperados fazem parte do contrato da automação; mudanças nas planilhas podem exigir adaptação do script. Não há medição publicada de redução de tempo ou erros.
