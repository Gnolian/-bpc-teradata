# Automação de campanhas cadastrais no Teradata

> **Versão de portfólio:** nomes de bases e tabelas, caminhos e cabeçalhos institucionais foram substituídos por exemplos. As consultas ilustram a implementação e precisam de adaptação a fontes autorizadas. Não há dados reais incluídos.

Orquestração em Python de SQLs de campanhas e atualização de uma base consolidada, identificada no código como “listão”.

O objetivo é organizar uma execução recorrente em uma sequência reproduzível: definir a data, preparar os SQLs, executar as etapas e guardar evidências do processamento.

## Fluxo

```text
Data de referência
  -> preparação dos SQLs de campanhas e atualização
  -> gravação do SQL gerado
  -> execução no Teradata, quando habilitada
  -> logs e cópia de evidências para o diretório configurado
```

## Decisões técnicas

- **SQL separado da orquestração:** as regras ficam nos arquivos SQL; Python coordena datas, arquivos, execução e logs.
- **Referência diária configurável:** a variável `DATA_REFERENCIA` permite selecionar a data usada na preparação.
- **SQL gerado persistido:** permite inspecionar o comando preparado para determinada execução.
- **Logs em arquivo e console:** apoiam acompanhamento e investigação de falhas.
- **Modo `DRY_RUN`:** prepara os SQLs sem executá-los no Teradata.
- **Etapas configuráveis:** criação de campanhas e atualização da base consolidada podem ser habilitadas separadamente.

Esses controles facilitam a operação, mas não tornam qualquer reexecução automaticamente segura: os efeitos dependem dos SQLs e das opções selecionadas.

## Tecnologias e arquivos

**Python, SQL/Teradata, teradatasql, python-dotenv, logging e pathlib.**

- [rodar_campanhas_e_listao.py](rodar_campanhas_e_listao.py): coordenação da rotina.
- [campanhas.sql](campanhas.sql): preparação das campanhas.
- [atualizar_listao.sql](atualizar_listao.sql): atualização da base consolidada.
- `logs/` e `sql_gerado/`: evidências locais, excluídas do versionamento.

## Execução

Instale as dependências em um ambiente Python:

```powershell
python -m pip install teradatasql python-dotenv
```

Configure no `.env` local `TD_HOST`, `TD_USER`, `TD_PASSWORD` e, se necessário, `TD_LOGMECH`.

Antes de executar, revise as constantes no início do script: `RODAR_CAMPANHAS`, `RODAR_ATUALIZACAO_LISTAO`, `DRY_RUN`, `DROP_EXISTING` e o destino de evidências `PASTA_DEMANDAS_REDE`. Ajuste também as fontes e destinos dos SQLs.

**Esta versão de portfólio usa `DRY_RUN = True`.** A simulação prepara os SQLs e grava evidências locais. A execução real exige adaptar as fontes de exemplo e alterar essa opção conscientemente.

Na pasta do projeto:

```powershell
$env:DATA_REFERENCIA = "20260701"
python rodar_campanhas_e_listao.py
```

Sem a variável, a rotina usa a data atual. A execução real modifica objetos no Teradata e exige um ambiente autorizado e compatível.

## O que este projeto demonstra

Automação de rotinas SQL, parametrização temporal, tratamento operacional de falhas e organização de evidências. O código mantém parâmetros específicos do ambiente original; não há configuração pronta de demonstração nem métricas de ganho operacional.

Logs e SQLs gerados podem conter detalhes internos. Para o portfólio, mantenha esses artefatos fora do repositório.
