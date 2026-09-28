# Carga de referências mensais no Teradata

> **Versão de portfólio:** nomes de bases e tabelas, caminhos e cabeçalhos institucionais foram substituídos por exemplos. As consultas ilustram a implementação e precisam de adaptação a fontes autorizadas. Não há dados reais incluídos.

Script Python para aplicar um modelo SQL a uma sequência de competências e inserir os resultados em uma tabela de destino.

O objetivo é centralizar a preparação mensal dos dados e as regras de correspondência entre referências, evitando editar e executar manualmente uma consulta para cada mês.

## Funcionamento

1. Gera uma sequência decrescente entre a referência inicial e a final.
2. Determina a referência correspondente do Cadastro Único.
3. Prepara a consulta a partir de [consulta_modelo.sql](consulta_modelo.sql).
4. Executa a carga da referência no destino.
5. Confirma a transação ou realiza rollback em caso de falha.

A regra geral associa a competência principal ao mês seguinte do Cadastro Único. O código possui exceções explícitas para janeiro e fevereiro de 2022, que usam o mesmo mês. Trata-se da regra implementada para essas fontes, não de uma regra universal para outros conjuntos de dados.

## Decisões técnicas

- **Modelo SQL reutilizável:** concentra a lógica de seleção e deixa a iteração mensal no Python.
- **Funções de calendário:** tratam a passagem de dezembro para janeiro e a navegação entre competências.
- **Transação por referência:** permite confirmar ou desfazer o processamento da competência corrente.
- **Exclusão anterior configurável:** atende ao reprocessamento de uma referência já carregada.
- **Política de parada configurável:** permite interromper no primeiro erro ou tentar as referências seguintes.

A opção de apagar antes de inserir altera dados existentes. Com essa opção desabilitada, repetir uma carga requer verificar se a referência já está presente e como a tabela trata duplicidades.

## Tecnologias e estrutura

**Python, SQL/Teradata, teradatasql, python-dotenv e datetime.**

- [carregar_referencias.py](carregar_referencias.py): configuração, calendário e execução.
- [consulta_modelo.sql](consulta_modelo.sql): modelo usado na carga.
- `.env`: conexão local, fora do versionamento.

## Execução

Use Python 3.10 ou superior. Na pasta do projeto:

```powershell
python -m pip install teradatasql python-dotenv
```

Configure `TD_HOST`, `TD_USER`, `TD_PASSWORD` e `TD_LOGMECH` no ambiente ou em um `.env` local.

Revise no início de `carregar_referencias.py`:

| Parâmetro | O que define |
| --- | --- |
| `TABELA_DESTINO` | Tabela que recebe a carga |
| `REFERENCIA_INICIAL` e `REFERENCIA_FINAL` | Intervalo decrescente de processamento |
| `APAGAR_ANTES_DE_INSERIR` | Substituição de dados da referência |
| `PARAR_NO_PRIMEIRO_ERRO` | Política de continuidade |
| `ARQUIVO_SQL_MODELO` | Caminho da consulta usada como modelo |

Após conferir fontes, destino e intervalo em um ambiente autorizado:

```powershell
python carregar_referencias.py
```

A rotina escreve no Teradata; não possui modo de demonstração independente da origem.

## O que este projeto demonstra

Parametrização de SQL, regras temporais, processamento repetível e controle transacional. O escopo é uma automação de carga com configuração em código, não uma plataforma de agendamento ou uma API.

O repositório deve conter apenas código e documentação, sem credenciais ou resultados reais da consulta. Não há massa sintética nem medição de desempenho incluída.
