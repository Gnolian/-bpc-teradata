#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extrai os arquivos mensais BPC por UF e CID no Teradata.

Período:
    202506 até 202607, inclusive.

Saída padrão:
    outputs/csv

Arquivos gerados:
    BPC_CID_202506.csv
    BPC_CID_202507.csv
    ...
    BPC_CID_202607.csv

Dependências:
    pip install teradatasql python-dotenv

Arquivo .env procurado ao lado do script ou na pasta atual:
    TD_HOST=servidor
    TD_USER=usuario
    TD_PASSWORD=senha
    TD_LOGMECH=LDAP
    TD_DATABASE=
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path

try:
    import teradatasql
except ImportError:
    print(
        "Biblioteca 'teradatasql' não instalada.\n"
        "Execute: pip install teradatasql python-dotenv",
        file=sys.stderr,
    )
    raise SystemExit(1)

try:
    from dotenv import dotenv_values, load_dotenv
except ImportError:
    print(
        "Biblioteca 'python-dotenv' não instalada.\n"
        "Execute: pip install teradatasql python-dotenv",
        file=sys.stderr,
    )
    raise SystemExit(1)


COMPETENCIA_INICIAL = "202506"
COMPETENCIA_FINAL = "202607"

PASTA_SAIDA_PADRAO = "outputs/csv"

TAMANHO_LOTE = 10_000


SQL_MODELO = r"""
WITH MACICA_UNICA AS
(
    SELECT
        a.nu_nb,
        a.cs_diag_1 AS cid,
        a.id_orgao_pag
    FROM BASE_EXEMPLO_06.TABELA_EXEMPLO_073 a
    WHERE a.cs_pa <> 3
      AND a.cs_especie = 87
      AND a.cs_sit_benef = 0
      AND a.nu_mes_ref = {mes_ref}

    QUALIFY ROW_NUMBER() OVER
    (
        PARTITION BY a.nu_nb
        ORDER BY
            CASE
                WHEN a.cs_diag_1 IS NULL
                  OR TRIM(a.cs_diag_1) = ''
                THEN 1
                ELSE 0
            END,
            a.cs_diag_1,
            a.id_orgao_pag
    ) = 1
),

AGENTE_UNICO AS
(
    SELECT
        a.co_sinonimo_banc AS id_orgao_pag,
        a.co_mun_inss
    FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_059 a
    WHERE a.nu_mes_ref <= {mes_ref}

    QUALIFY ROW_NUMBER() OVER
    (
        PARTITION BY a.co_sinonimo_banc
        ORDER BY
            a.nu_mes_ref DESC,
            a.co_mun_inss
    ) = 1
),

ENTE_UNICO AS
(
    SELECT
        codigo_municipio_origem,
        MAX(CAST(co_ibge7 AS VARCHAR(7))) AS co_ibge7
    FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_068
    GROUP BY
        codigo_municipio_origem
),

CID_UNICO AS
(
    SELECT
        co_cid,
        MAX(ds_descricao) AS ds_descricao
    FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_069
    GROUP BY
        co_cid
),

BASE AS
(
    SELECT
        m.nu_nb,

        CASE SUBSTRING(e.co_ibge7, 1, 2)
            WHEN '11' THEN 'Rondônia'
            WHEN '12' THEN 'Acre'
            WHEN '13' THEN 'Amazonas'
            WHEN '14' THEN 'Roraima'
            WHEN '15' THEN 'Pará'
            WHEN '16' THEN 'Amapá'
            WHEN '17' THEN 'Tocantins'
            WHEN '21' THEN 'Maranhão'
            WHEN '22' THEN 'Piauí'
            WHEN '23' THEN 'Ceará'
            WHEN '24' THEN 'Rio Grande do Norte'
            WHEN '25' THEN 'Paraíba'
            WHEN '26' THEN 'Pernambuco'
            WHEN '27' THEN 'Alagoas'
            WHEN '28' THEN 'Sergipe'
            WHEN '29' THEN 'Bahia'
            WHEN '31' THEN 'Minas Gerais'
            WHEN '32' THEN 'Espírito Santo'
            WHEN '33' THEN 'Rio de Janeiro'
            WHEN '35' THEN 'São Paulo'
            WHEN '41' THEN 'Paraná'
            WHEN '42' THEN 'Santa Catarina'
            WHEN '43' THEN 'Rio Grande do Sul'
            WHEN '50' THEN 'Mato Grosso do Sul'
            WHEN '51' THEN 'Mato Grosso'
            WHEN '52' THEN 'Goiás'
            WHEN '53' THEN 'Distrito Federal'
            ELSE 'UF Desconhecida'
        END AS uf,

        CASE
            WHEN c.ds_descricao IS NULL
            THEN 'Não Informado'
            ELSE m.cid
        END AS cid_ajustado,

        COALESCE(
            c.ds_descricao,
            'Não Informado'
        ) AS ds_descricao_ajustada

    FROM MACICA_UNICA m

    LEFT JOIN AGENTE_UNICO ap
        ON m.id_orgao_pag = ap.id_orgao_pag

    LEFT JOIN ENTE_UNICO e
        ON ap.co_mun_inss = e.codigo_municipio_origem

    LEFT JOIN CID_UNICO c
        ON m.cid = c.co_cid
),

BASE_FINAL AS
(
    SELECT
        b.*
    FROM BASE b

    QUALIFY ROW_NUMBER() OVER
    (
        PARTITION BY b.nu_nb
        ORDER BY
            CASE
                WHEN b.uf = 'UF Desconhecida' THEN 1
                ELSE 0
            END,

            CASE
                WHEN b.cid_ajustado = 'Não Informado' THEN 1
                ELSE 0
            END,

            b.uf,
            b.cid_ajustado,
            b.ds_descricao_ajustada
    ) = 1
)

SELECT
    uf,
    cid_ajustado,
    ds_descricao_ajustada,
    COUNT(DISTINCT nu_nb) AS bpc_pcd_cid
FROM BASE_FINAL
GROUP BY
    uf,
    cid_ajustado,
    ds_descricao_ajustada
HAVING COUNT(DISTINCT nu_nb) > 0
ORDER BY
    uf,
    cid_ajustado
"""


def proxima_competencia(competencia: str) -> str:
    ano = int(competencia[:4])
    mes = int(competencia[4:])

    if mes == 12:
        return f"{ano + 1}01"

    return f"{ano}{mes + 1:02d}"


def listar_competencias(inicio: str, fim: str) -> list[str]:
    competencias: list[str] = []
    atual = inicio

    while atual <= fim:
        competencias.append(atual)
        atual = proxima_competencia(atual)

    return competencias


def localizar_arquivo_env(caminho_informado: str | None) -> Path:
    """
    Localiza o .env nesta ordem:
    1. Caminho passado em --env;
    2. Pasta em que o script está;
    3. Pasta atual do PowerShell.
    """
    pasta_script = Path(__file__).resolve().parent
    pasta_atual = Path.cwd().resolve()

    candidatos: list[Path] = []

    if caminho_informado:
        candidatos.append(Path(caminho_informado).expanduser())

    candidatos.extend(
        [
            pasta_script / ".env",
            pasta_atual / ".env",
        ]
    )

    # Remove caminhos repetidos sem perder a ordem.
    candidatos_unicos: list[Path] = []
    for candidato in candidatos:
        candidato = candidato.resolve()
        if candidato not in candidatos_unicos:
            candidatos_unicos.append(candidato)

    for candidato in candidatos_unicos:
        if candidato.is_file():
            return candidato

    # Erro comum no Windows: o arquivo aparece como ".env", mas é ".env.txt".
    env_txt_encontrados: list[Path] = []
    for pasta in {pasta_script, pasta_atual}:
        candidato_txt = pasta / ".env.txt"
        if candidato_txt.is_file():
            env_txt_encontrados.append(candidato_txt)

    mensagem = [
        "Arquivo .env não encontrado.",
        "Caminhos verificados:",
        *[f"  - {caminho}" for caminho in candidatos_unicos],
    ]

    if env_txt_encontrados:
        mensagem.extend(
            [
                "",
                "Foi encontrado um possível arquivo com extensão incorreta:",
                *[f"  - {caminho}" for caminho in env_txt_encontrados],
                "Renomeie-o de .env.txt para .env.",
            ]
        )

    raise FileNotFoundError("\n".join(mensagem))


def primeiro_valor(
    valores: dict[str, str | None],
    *nomes: str,
) -> str:
    """Retorna o primeiro valor preenchido entre os nomes informados."""
    for nome in nomes:
        valor = valores.get(nome)
        if valor is not None and str(valor).strip():
            return str(valor).strip()
    return ""


def carregar_configuracao(
    caminho_env: str | None = None,
) -> dict[str, str]:
    """
    Carrega as credenciais do .env sem solicitar servidor, usuário ou senha.

    Aceita os seguintes nomes:

    Servidor:
        TD_HOST, TERADATA_HOST, TERA_HOST

    Usuário:
        TD_USER, TERADATA_USER, TERA_USER

    Senha:
        TD_PASSWORD, TERADATA_PASSWORD, TERA_PASSWORD

    Autenticação:
        TD_LOGMECH, TERADATA_LOGMECH

    Database opcional:
        TD_DATABASE, TERADATA_DATABASE
    """
    arquivo_env = localizar_arquivo_env(caminho_env)

    # encoding="utf-8-sig" remove o BOM que o Bloco de Notas pode inserir
    # no início do arquivo e que faria a primeira variável não ser reconhecida.
    valores_arquivo = dotenv_values(
        dotenv_path=arquivo_env,
        encoding="utf-8-sig",
    )

    load_dotenv(
        dotenv_path=arquivo_env,
        encoding="utf-8-sig",
        override=True,
    )

    # Combina o arquivo com o ambiente, priorizando o conteúdo do .env.
    valores: dict[str, str | None] = dict(os.environ)
    valores.update(valores_arquivo)

    logging.info("Arquivo .env carregado: %s", arquivo_env)

    chaves_encontradas = sorted(
        chave
        for chave, valor in valores_arquivo.items()
        if valor is not None
    )
    logging.info(
        "Variáveis encontradas no .env: %s",
        ", ".join(chaves_encontradas) if chaves_encontradas else "nenhuma",
    )

    configuracao = {
        "host": primeiro_valor(
            valores,
            "TD_HOST",
            "TERADATA_HOST",
            "TERA_HOST",
        ),
        "user": primeiro_valor(
            valores,
            "TD_USER",
            "TERADATA_USER",
            "TERA_USER",
        ),
        "password": primeiro_valor(
            valores,
            "TD_PASSWORD",
            "TERADATA_PASSWORD",
            "TERA_PASSWORD",
        ),
        "logmech": primeiro_valor(
            valores,
            "TD_LOGMECH",
            "TERADATA_LOGMECH",
        ) or "LDAP",
        "database": primeiro_valor(
            valores,
            "TD_DATABASE",
            "TERADATA_DATABASE",
        ),
    }

    faltantes: list[str] = []

    if not configuracao["host"]:
        faltantes.append(
            "servidor (TD_HOST, TERADATA_HOST ou TERA_HOST)"
        )
    if not configuracao["user"]:
        faltantes.append(
            "usuário (TD_USER, TERADATA_USER ou TERA_USER)"
        )
    if not configuracao["password"]:
        faltantes.append(
            "senha (TD_PASSWORD, TERADATA_PASSWORD ou TERA_PASSWORD)"
        )

    if faltantes:
        raise RuntimeError(
            "O .env foi localizado, mas faltam estas configurações:\n  - "
            + "\n  - ".join(faltantes)
            + "\n\nVariáveis encontradas no arquivo: "
            + (
                ", ".join(chaves_encontradas)
                if chaves_encontradas
                else "nenhuma"
            )
        )

    return configuracao


def abrir_conexao(configuracao: dict[str, str]):
    parametros = {
        "host": configuracao["host"],
        "user": configuracao["user"],
        "password": configuracao["password"],
        "logmech": configuracao["logmech"],
    }

    if configuracao["database"]:
        parametros["database"] = configuracao["database"]

    return teradatasql.connect(**parametros)


def salvar_resultado_csv(
    conexao,
    sql: str,
    arquivo_saida: Path,
    tamanho_lote: int = TAMANHO_LOTE,
) -> int:
    arquivo_saida.parent.mkdir(parents=True, exist_ok=True)

    arquivo_temporario = arquivo_saida.with_suffix(".csv.parcial")

    if arquivo_temporario.exists():
        arquivo_temporario.unlink()

    total_linhas = 0

    try:
        with conexao.cursor() as cursor:
            cursor.execute(sql)

            if not cursor.description:
                raise RuntimeError("A consulta não retornou colunas.")

            nomes_colunas = [coluna[0] for coluna in cursor.description]

            with arquivo_temporario.open(
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as arquivo_csv:
                escritor = csv.writer(
                    arquivo_csv,
                    delimiter=";",
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL,
                    lineterminator="\n",
                )

                escritor.writerow(nomes_colunas)

                while True:
                    linhas = cursor.fetchmany(tamanho_lote)

                    if not linhas:
                        break

                    escritor.writerows(linhas)
                    total_linhas += len(linhas)

        arquivo_temporario.replace(arquivo_saida)
        return total_linhas

    except Exception:
        if arquivo_temporario.exists():
            arquivo_temporario.unlink()
        raise


def criar_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extrai BPC por UF e CID de 202506 até 202607."
        )
    )

    parser.add_argument(
        "--env",
        default=None,
        help=(
            "Caminho do arquivo .env. Quando omitido, procura ao lado "
            "do script e na pasta atual."
        ),
    )

    parser.add_argument(
        "--testar-conexao",
        action="store_true",
        help="Carrega o .env, testa a conexão e encerra sem extrair os meses.",
    )

    parser.add_argument(
        "--saida",
        default=PASTA_SAIDA_PADRAO,
        help="Pasta em que os CSVs serão gravados.",
    )

    parser.add_argument(
        "--inicio",
        default=COMPETENCIA_INICIAL,
        help="Competência inicial no formato AAAAMM.",
    )

    parser.add_argument(
        "--fim",
        default=COMPETENCIA_FINAL,
        help="Competência final no formato AAAAMM.",
    )

    parser.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Refaz arquivos que já existem.",
    )

    return parser.parse_args()


def main() -> int:
    args = criar_argumentos()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if (
        len(args.inicio) != 6
        or not args.inicio.isdigit()
        or len(args.fim) != 6
        or not args.fim.isdigit()
    ):
        logging.error("As competências devem usar o formato AAAAMM.")
        return 1

    if args.inicio > args.fim:
        logging.error(
            "A competência inicial não pode ser maior que a final."
        )
        return 1

    pasta_saida = Path(args.saida)
    competencias = listar_competencias(args.inicio, args.fim)

    logging.info("Período: %s até %s", args.inicio, args.fim)
    logging.info("Quantidade de competências: %d", len(competencias))
    logging.info("Pasta de saída: %s", pasta_saida)

    try:
        configuracao = carregar_configuracao(args.env)
    except Exception:
        logging.exception("Erro ao carregar as credenciais.")
        return 1

    falhas: list[str] = []
    sucessos = 0
    ignorados = 0
    inicio_geral = time.perf_counter()

    try:
        with abrir_conexao(configuracao) as conexao:
            logging.info("Conexão com o Teradata realizada.")

            if args.testar_conexao:
                logging.info(
                    "Teste concluído. Nenhuma competência foi extraída."
                )
                return 0

            for indice, competencia in enumerate(competencias, start=1):
                arquivo_saida = (
                    pasta_saida / f"BPC_CID_{competencia}.csv"
                )

                if arquivo_saida.exists() and not args.sobrescrever:
                    logging.info(
                        "[%d/%d] %s já existe; ignorado.",
                        indice,
                        len(competencias),
                        arquivo_saida.name,
                    )
                    ignorados += 1
                    continue

                logging.info(
                    "[%d/%d] Extraindo competência %s...",
                    indice,
                    len(competencias),
                    competencia,
                )

                inicio_mes = time.perf_counter()
                sql = SQL_MODELO.format(mes_ref=competencia)

                try:
                    total_linhas = salvar_resultado_csv(
                        conexao=conexao,
                        sql=sql,
                        arquivo_saida=arquivo_saida,
                    )

                    duracao = time.perf_counter() - inicio_mes
                    sucessos += 1

                    logging.info(
                        "[%d/%d] %s concluída: %s linhas em %.1f s.",
                        indice,
                        len(competencias),
                        competencia,
                        f"{total_linhas:,}".replace(",", "."),
                        duracao,
                    )

                except Exception:
                    falhas.append(competencia)
                    logging.exception(
                        "[%d/%d] Erro na competência %s.",
                        indice,
                        len(competencias),
                        competencia,
                    )

    except Exception:
        logging.exception("Erro de conexão ou execução no Teradata.")
        return 1

    duracao_total = time.perf_counter() - inicio_geral

    logging.info("=" * 80)
    logging.info("Extrações concluídas: %d", sucessos)
    logging.info("Arquivos ignorados: %d", ignorados)
    logging.info("Duração total: %.1f segundos", duracao_total)

    if falhas:
        logging.error(
            "Competências com erro: %s",
            ", ".join(falhas),
        )
        return 2

    logging.info("Processamento finalizado sem erros.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())