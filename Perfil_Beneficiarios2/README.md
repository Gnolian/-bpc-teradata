# Análise de perfil e condições domiciliares

> **Versão de portfólio:** nomes de bases e tabelas, caminhos e cabeçalhos institucionais foram substituídos por exemplos. As consultas ilustram a implementação e precisam de adaptação a fontes autorizadas. Não há dados reais incluídos.

Rotina Python para combinar o perfil de beneficiários com informações sociais e domiciliares e produzir tabelas, gráficos e mapas por UF.

O objetivo é preparar material analítico reutilizável para apresentações e exploração dos dados. Nesta pasta, a execução ocorre por script e gera arquivos; não há uma interface Streamlit implementada em `main.py`.

## Entregas implementadas

- Distribuições por espécie de benefício, gênero, faixa etária e raça/cor.
- Indicadores de alfabetização, água canalizada, material do piso e cômodos por pessoa.
- Gráficos interativos em HTML e tentativa de exportação em PNG.
- Mapas temáticos por UF.
- Resumos CSV, planilha Excel e caches Parquet.

## Como funciona

O script consulta conjuntos de perfil, condições domiciliares e indicadores territoriais. As extrações de perfil e condições domiciliares são organizadas por UF, armazenadas localmente e reunidas para análise. A combinação local utiliza o número do benefício como chave.

## Decisões técnicas

- **Separar perfil e condições domiciliares na extração:** permite preparar cada conjunto antes da combinação.
- **Cache Parquet:** reaproveita dados já extraídos em novas execuções. A existência do arquivo não garante que esteja atualizado.
- **Normalização de categorias e números:** trata campos vazios e valores incompatíveis antes das agregações.
- **GeoJSON e Plotly:** associam indicadores às geometrias das UFs e produzem visualizações interativas.
- **HTML como saída dos gráficos:** permite consultar a visualização em um navegador fora de uma aplicação web.

A leitura usa lotes, mas acumula DataFrames e realiza a combinação em memória. O consumo total depende do volume. A cardinalidade da chave nas fontes também precisa ser conferida para evitar multiplicação de linhas no cruzamento.

## Tecnologias

Python, Pandas, Plotly, Teradata, python-dotenv, Parquet e OpenPyXL. Kaleido é necessário para exportação de imagens pelo Plotly; a rotina mantém a saída HTML quando a exportação de imagem falha.

## Execução

Na pasta do projeto, com Python 3.10 ou superior:

```powershell
python -m pip install -r requirements.txt
python -m pip install pyarrow openpyxl kaleido
```

Configure as variáveis locais de conexão `TD_HOST`, `TD_USER`, `TD_PASSWORD` e, quando necessário, `TD_LOGMECH`. As fontes são selecionadas por `TD_DATABASE`, `TD_TABLE_PERFIL`, `TD_TABLE_SOCIAL_DOM` e `TD_TABLE_MAPA_UF`.

Com acesso autorizado às fontes compatíveis:

```powershell
python main.py
```

O script usa [assets/br_ufs.geojson](assets/br_ufs.geojson) para os mapas e grava as entregas em `outputs/`. O arquivo `requirements.txt` também lista Streamlit, mas o ponto de entrada deste projeto é um script de processamento.

## Competências demonstradas e limites

Integração de dados, tratamento de categorias, agregação estatística descritiva e comunicação visual. Os indicadores descrevem as bases utilizadas; o código não implementa inferência causal nem modelo preditivo.

Não há dados sintéticos de demonstração incluídos. HTMLs, planilhas e imagens gerados também podem revelar informações da origem e devem ser revisados antes de qualquer divulgação.
