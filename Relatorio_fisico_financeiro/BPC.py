from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import time
import traceback
import unicodedata
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

# ============================================================================
# CONFIGURAÇÃO PRINCIPAL
# ============================================================================

RAIZ_PADRAO = Path("dados/BPC")

EXTENSOES_EXCEL = (".xls", ".xlsx", ".xlsm")
ABA_MUNICIPIO_PREFERIDA = "BRASIL MUNIC"

# Colunas das nove métricas, na mesma ordem das consultas.
METRICAS = [
    "QUANTIDADE_BENEFICIOS_PCD",
    "QUANTIDADE_BENEFICIOS_IDOSO",
    "QUANTIDADE_TOTAL_BENEFICIOS",
    "RECURSOS_PAGOS_MES_PCD",
    "RECURSOS_PAGOS_MES_IDOSO",
    "RECURSOS_TOTAL_PAGOS_MES",
    "RECURSOS_TOTAL_PAGOS_ANO_PCD",
    "RECURSOS_TOTAL_PAGOS_ANO_IDOSO",
    "RECURSOS_TOTAL_PAGOS_ANO",
]

METRICAS_ROTULOS = {
    "QUANTIDADE_BENEFICIOS_PCD": "Quantidade de benefícios PCD",
    "QUANTIDADE_BENEFICIOS_IDOSO": "Quantidade de benefícios Idoso",
    "QUANTIDADE_TOTAL_BENEFICIOS": "Total de benefícios",
    "RECURSOS_PAGOS_MES_PCD": "Recursos pagos no mês PCD",
    "RECURSOS_PAGOS_MES_IDOSO": "Recursos pagos no mês Idoso",
    "RECURSOS_TOTAL_PAGOS_MES": "Total de recursos pagos no mês",
    "RECURSOS_TOTAL_PAGOS_ANO_PCD": "Recursos pagos no ano PCD",
    "RECURSOS_TOTAL_PAGOS_ANO_IDOSO": "Recursos pagos no ano Idoso",
    "RECURSOS_TOTAL_PAGOS_ANO": "Total de recursos pagos no ano",
}

METRICAS_QUANTIDADE = set(METRICAS[:3])
CENTAVO = Decimal("0.01")
ZERO = Decimal("0")

MESES = {
    1: ("Janeiro", "Jan"),
    2: ("Fevereiro", "Fev"),
    3: ("Março", "Mar"),
    4: ("Abril", "Abr"),
    5: ("Maio", "Mai"),
    6: ("Junho", "Jun"),
    7: ("Julho", "Jul"),
    8: ("Agosto", "Ago"),
    9: ("Setembro", "Set"),
    10: ("Outubro", "Out"),
    11: ("Novembro", "Nov"),
    12: ("Dezembro", "Dez"),
}

UFS = {
    "11": ("RO", "Rondônia"),
    "12": ("AC", "Acre"),
    "13": ("AM", "Amazonas"),
    "14": ("RR", "Roraima"),
    "15": ("PA", "Pará"),
    "16": ("AP", "Amapá"),
    "17": ("TO", "Tocantins"),
    "21": ("MA", "Maranhão"),
    "22": ("PI", "Piauí"),
    "23": ("CE", "Ceará"),
    "24": ("RN", "Rio Grande do Norte"),
    "25": ("PB", "Paraíba"),
    "26": ("PE", "Pernambuco"),
    "27": ("AL", "Alagoas"),
    "28": ("SE", "Sergipe"),
    "29": ("BA", "Bahia"),
    "31": ("MG", "Minas Gerais"),
    "32": ("ES", "Espírito Santo"),
    "33": ("RJ", "Rio de Janeiro"),
    "35": ("SP", "São Paulo"),
    "41": ("PR", "Paraná"),
    "42": ("SC", "Santa Catarina"),
    "43": ("RS", "Rio Grande do Sul"),
    "50": ("MS", "Mato Grosso do Sul"),
    "51": ("MT", "Mato Grosso"),
    "52": ("GO", "Goiás"),
    "53": ("DF", "Distrito Federal"),
}

REGIOES = {
    "1": "Norte",
    "2": "Nordeste",
    "3": "Sudeste",
    "4": "Sul",
    "5": "Centro-Oeste",
}

# Mapeamento local para casos recém-criados que ainda não existem no modelo.
# O script também tenta consultar a API de Localidades do IBGE e lê, se existir,
# CONSULTAS/cadastro_municipios_novos.csv (codigo;municipio).
MUNICIPIOS_NOVOS_FIXOS = {
    "510183": "Boa Esperança do Norte",
}

# Constantes do Excel/COM, declaradas numericamente para não depender de makepy.
XL_UP = -4162
XL_SHIFT_DOWN = -4121
XL_PASTE_FORMATS = -4122
XL_CALCULATION_MANUAL = -4135
XL_CALCULATION_AUTOMATIC = -4105
XL_TYPE_PDF = 0
XL_QUALITY_STANDARD = 0
XL_OPEN_XML_WORKBOOK = 51


# ============================================================================
# MODELOS DE DADOS E LOG
# ============================================================================

@dataclass
class Contexto:
    referencia: str
    ano: int
    mes: int
    inicio_ano: str
    pasta_mes: Path
    pasta_consultas: Path
    pasta_excel: Path
    pasta_pdf: Path
    prefixo: str
    mes_nome: str


@dataclass
class Divergencia:
    severidade: str
    etapa: str
    entidade: str
    metrica: str = ""
    esperado: str = ""
    encontrado: str = ""
    diferenca: str = ""
    mensagem: str = ""


class RegistroLog:
    def __init__(self, caminho: Path | None = None) -> None:
        self.caminho = caminho
        self._arquivo = None
        if caminho:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            self._arquivo = caminho.open("w", encoding="utf-8")

    def escrever(self, mensagem: str = "") -> None:
        print(mensagem)
        if self._arquivo:
            self._arquivo.write(mensagem + "\n")
            self._arquivo.flush()

    def fechar(self) -> None:
        if self._arquivo:
            self._arquivo.close()
            self._arquivo = None


class Validador:
    def __init__(self, log: RegistroLog) -> None:
        self.log = log
        self.itens: list[Divergencia] = []
        self.novos_municipios: list[dict[str, str]] = []

    def adicionar(
        self,
        severidade: str,
        etapa: str,
        entidade: str,
        metrica: str = "",
        esperado: Any = "",
        encontrado: Any = "",
        diferenca: Any = "",
        mensagem: str = "",
    ) -> None:
        item = Divergencia(
            severidade=severidade,
            etapa=etapa,
            entidade=entidade,
            metrica=metrica,
            esperado=formatar_saida(esperado),
            encontrado=formatar_saida(encontrado),
            diferenca=formatar_saida(diferenca),
            mensagem=mensagem,
        )
        self.itens.append(item)
        marcador = "ERRO" if severidade == "ERRO" else severidade
        detalhe = f" | {metrica}" if metrica else ""
        self.log.escrever(f"[{marcador}] {etapa} | {entidade}{detalhe} | {mensagem}")

    def erro(self, *args: Any, **kwargs: Any) -> None:
        self.adicionar("ERRO", *args, **kwargs)

    def aviso(self, *args: Any, **kwargs: Any) -> None:
        self.adicionar("AVISO", *args, **kwargs)

    def info(self, *args: Any, **kwargs: Any) -> None:
        self.adicionar("INFO", *args, **kwargs)

    @property
    def tem_erros(self) -> bool:
        return any(i.severidade == "ERRO" for i in self.itens)

    @property
    def total_erros(self) -> int:
        return sum(i.severidade == "ERRO" for i in self.itens)

    @property
    def total_avisos(self) -> int:
        return sum(i.severidade == "AVISO" for i in self.itens)


# ============================================================================
# FUNÇÕES GERAIS
# ============================================================================

def remover_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    texto = remover_acentos(str(valor)).upper().strip()
    return re.sub(r"\s+", " ", texto)


def normalizar_codigo(valor: Any, tamanho: int | None = None) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        texto = str(int(valor))
    else:
        texto = str(valor).strip()
        if texto.endswith(".0"):
            texto = texto[:-2]
    texto = re.sub(r"\D", "", texto)
    if tamanho and texto:
        texto = texto.zfill(tamanho)
    return texto


def decimal_pt(valor: Any) -> Decimal:
    if valor is None or valor == "":
        return ZERO
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return ZERO
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"Valor numérico inválido: {valor!r}") from exc


def quantizar(valor: Decimal, metrica: str) -> Decimal:
    if metrica in METRICAS_QUANTIDADE:
        return valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def iguais(a: Decimal, b: Decimal, metrica: str) -> bool:
    tolerancia = ZERO if metrica in METRICAS_QUANTIDADE else CENTAVO
    return abs(a - b) <= tolerancia


def formatar_saida(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, Decimal):
        return f"{valor:.2f}" if valor != valor.to_integral() else str(valor.to_integral())
    return str(valor)


def zero_metricas() -> dict[str, Decimal]:
    return {m: ZERO for m in METRICAS}


def somar_registros(registros: Iterable[dict[str, Decimal]]) -> dict[str, Decimal]:
    total = zero_metricas()
    for registro in registros:
        for metrica in METRICAS:
            total[metrica] += registro.get(metrica, ZERO)
    return total


def validar_referencia(ref: str) -> tuple[int, int]:
    if not re.fullmatch(r"\d{6}", ref):
        raise ValueError("A referência deve estar no formato AAAAMM, por exemplo 202607.")
    ano = int(ref[:4])
    mes = int(ref[4:6])
    if mes not in range(1, 13):
        raise ValueError("Mês inválido na referência.")
    return ano, mes


def construir_contexto(args: argparse.Namespace) -> Contexto:
    ano, mes = validar_referencia(args.ref)
    mes_ano = f"{mes:02d}{ano}"
    pasta_mes = Path(args.raiz) / str(ano) / mes_ano
    pasta_consultas = Path(args.consultas_dir) if args.consultas_dir else pasta_mes / "CONSULTAS"
    pasta_excel = Path(args.excel_dir) if args.excel_dir else pasta_mes / "EXCEL"
    pasta_pdf = Path(args.pdf_dir) if args.pdf_dir else pasta_mes / "PDF"
    mes_nome, prefixo = MESES[mes]
    return Contexto(
        referencia=args.ref,
        ano=ano,
        mes=mes,
        inicio_ano=f"{ano}01",
        pasta_mes=pasta_mes,
        pasta_consultas=pasta_consultas,
        pasta_excel=pasta_excel,
        pasta_pdf=pasta_pdf,
        prefixo=prefixo,
        mes_nome=mes_nome,
    )


def referencia_anterior(ano: int, mes: int) -> tuple[int, int]:
    if mes == 1:
        return ano - 1, 12
    return ano, mes - 1


# ============================================================================
# SQL E EXTRAÇÃO
# ============================================================================

def sql_base(ctx: Contexto) -> str:
    return f"""
WITH BASE AS (
    SELECT DISTINCT
        a.nu_nb,
        a.cs_especie,
        a.nu_mes_ref,
        a.cs_sit_benef,
        a.vl_bruto,
        a.cs_pa,
        a.id_orgao_pag,
        b.co_ibge7
    FROM BASE_EXEMPLO_06.TABELA_EXEMPLO_073 a
    LEFT JOIN (
        SELECT s.*
        FROM (
            SELECT
                x.*,
                ROW_NUMBER() OVER (
                    PARTITION BY x.id_orgao_pag
                    ORDER BY x.nu_mes_ref DESC
                ) AS rank_ordem
            FROM (
                SELECT DISTINCT
                    TRIM(ap.co_sinonimo_banc) AS id_orgao_pag,
                    ce.co_ibge7,
                    ap.nu_mes_ref
                FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_059 ap
                LEFT JOIN BASE_EXEMPLO_08.TABELA_EXEMPLO_068 ce
                    ON TRIM(ap.co_mun_inss) = ce.codigo_municipio_origem
            ) x
        ) s
        WHERE s.rank_ordem = 1
    ) b
        ON a.id_orgao_pag = b.id_orgao_pag
    WHERE a.cs_pa <> 3
      AND a.cs_especie IN (87, 88)
      AND a.nu_mes_ref BETWEEN {ctx.inicio_ano} AND {ctx.referencia}
)
""".strip()


def gerar_sql_agrupado(ctx: Contexto, tamanho: int, alias: str) -> str:
    return f"""
{sql_base(ctx)}
SELECT
    SUBSTRING(co_ibge7, 1, {tamanho}) AS {alias},
    COUNT(DISTINCT CASE WHEN cs_especie = 87 AND nu_mes_ref = {ctx.referencia} AND cs_sit_benef = 0 THEN nu_nb END) AS QUANTIDADE_BENEFICIOS_PCD,
    COUNT(DISTINCT CASE WHEN cs_especie = 88 AND nu_mes_ref = {ctx.referencia} AND cs_sit_benef = 0 THEN nu_nb END) AS QUANTIDADE_BENEFICIOS_IDOSO,
    COUNT(DISTINCT CASE WHEN cs_especie IN (87, 88) AND nu_mes_ref = {ctx.referencia} AND cs_sit_benef = 0 THEN nu_nb END) AS QUANTIDADE_TOTAL_BENEFICIOS,
    SUM(CASE WHEN cs_especie = 87 AND nu_mes_ref = {ctx.referencia} THEN vl_bruto END) AS RECURSOS_PAGOS_MES_PCD,
    SUM(CASE WHEN cs_especie = 88 AND nu_mes_ref = {ctx.referencia} THEN vl_bruto END) AS RECURSOS_PAGOS_MES_IDOSO,
    SUM(CASE WHEN cs_especie IN (87, 88) AND nu_mes_ref = {ctx.referencia} THEN vl_bruto END) AS RECURSOS_TOTAL_PAGOS_MES,
    SUM(CASE WHEN cs_especie = 87 AND nu_mes_ref BETWEEN {ctx.inicio_ano} AND {ctx.referencia} THEN vl_bruto END) AS RECURSOS_TOTAL_PAGOS_ANO_PCD,
    SUM(CASE WHEN cs_especie = 88 AND nu_mes_ref BETWEEN {ctx.inicio_ano} AND {ctx.referencia} THEN vl_bruto END) AS RECURSOS_TOTAL_PAGOS_ANO_IDOSO,
    SUM(CASE WHEN cs_especie IN (87, 88) AND nu_mes_ref BETWEEN {ctx.inicio_ano} AND {ctx.referencia} THEN vl_bruto END) AS RECURSOS_TOTAL_PAGOS_ANO
FROM BASE
GROUP BY SUBSTRING(co_ibge7, 1, {tamanho})
ORDER BY 1;
""".strip() + "\n"


def gerar_arquivos_sql(ctx: Contexto, log: RegistroLog) -> dict[str, Path]:
    ctx.pasta_consultas.mkdir(parents=True, exist_ok=True)
    arquivos = {
        "municipio": ctx.pasta_consultas / f"bpc_munic_{ctx.referencia}.sql",
        "uf": ctx.pasta_consultas / f"bpc_uf_{ctx.referencia}.sql",
        "regiao": ctx.pasta_consultas / f"bpc_reg_{ctx.referencia}.sql",
    }
    arquivos["municipio"].write_text(gerar_sql_agrupado(ctx, 6, "MUNICIPIO"), encoding="utf-8")
    arquivos["uf"].write_text(gerar_sql_agrupado(ctx, 2, "UF"), encoding="utf-8")
    arquivos["regiao"].write_text(gerar_sql_agrupado(ctx, 1, "REGIAO"), encoding="utf-8")
    log.escrever(f"[OK] Consultas SQL geradas em: {ctx.pasta_consultas}")
    return arquivos


def formatar_csv_teradata(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, Decimal):
        return format(valor, "f").replace(".", ",")
    if isinstance(valor, float):
        return format(Decimal(str(valor)), "f").replace(".", ",")
    return str(valor)


def executar_consultas_teradata(
    ctx: Contexto,
    arquivos_sql: dict[str, Path],
    log: RegistroLog,
) -> None:
    try:
        import teradatasql  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Para executar as consultas automaticamente, instale: pip install teradatasql"
        ) from exc

    host = os.getenv("TERADATA_HOST")
    user = os.getenv("TERADATA_USER")
    password = os.getenv("TERADATA_PASSWORD")
    logmech = os.getenv("TERADATA_LOGMECH", "LDAP")
    if not host or not user or not password:
        raise RuntimeError(
            "Defina TERADATA_HOST, TERADATA_USER e TERADATA_PASSWORD nas variáveis de ambiente."
        )

    saidas = {
        "municipio": ctx.pasta_consultas / f"BPC_munic_{ctx.mes:02d}{ctx.ano}.csv",
        "uf": ctx.pasta_consultas / f"BPC_uf_{ctx.mes:02d}{ctx.ano}.csv",
        "regiao": ctx.pasta_consultas / f"BPC_regiao_{ctx.mes:02d}{ctx.ano}.csv",
    }

    log.escrever("[INFO] Conectando ao Teradata...")
    with teradatasql.connect(
        host=host,
        user=user,
        password=password,
        logmech=logmech,
    ) as conexao:
        for tipo, caminho_sql in arquivos_sql.items():
            sql = caminho_sql.read_text(encoding="utf-8")
            log.escrever(f"[INFO] Executando consulta: {caminho_sql.name}")
            cursor = conexao.cursor()
            cursor.execute(sql)
            cabecalho = [col[0] for col in cursor.description]
            with saidas[tipo].open("w", encoding="utf-8-sig", newline="") as arquivo_csv:
                escritor = csv.writer(arquivo_csv, delimiter=";", quoting=csv.QUOTE_NONNUMERIC)
                escritor.writerow(cabecalho)
                while True:
                    linhas = cursor.fetchmany(1000)
                    if not linhas:
                        break
                    for linha in linhas:
                        escritor.writerow([formatar_csv_teradata(v) for v in linha])
            cursor.close()
            log.escrever(f"[OK] CSV gerado: {saidas[tipo]}")


# ============================================================================
# LEITURA E VALIDAÇÃO DOS CSVs
# ============================================================================

def localizar_csv(pasta: Path, tipo: str, referencia: str | None = None) -> Path:
    padroes = {
        "municipio": ("munic",),
        "uf": ("_uf", "uf_"),
        "regiao": ("regiao", "reg_"),
    }
    candidatos: list[Path] = []
    for caminho in pasta.glob("*.csv"):
        nome = normalizar_texto(caminho.name).replace(" ", "_").lower()
        if tipo == "uf":
            if "munic" in nome or "reg" in nome:
                continue
            if "uf" in nome:
                candidatos.append(caminho)
        elif any(p in nome for p in padroes[tipo]):
            candidatos.append(caminho)
    if not candidatos:
        raise FileNotFoundError(f"CSV de {tipo} não encontrado em {pasta}")
    if referencia:
        ano, mes = validar_referencia(referencia)
        marcadores = (referencia, f"{mes:02d}{ano}")
        da_referencia = [p for p in candidatos if any(m in p.name for m in marcadores)]
        if da_referencia:
            candidatos = da_referencia
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def abrir_csv_com_encoding(caminho: Path):
    ultimo_erro: Exception | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            arquivo = caminho.open("r", encoding=encoding, newline="")
            arquivo.readline()
            arquivo.seek(0)
            return arquivo
        except UnicodeDecodeError as exc:
            ultimo_erro = exc
    raise RuntimeError(f"Não foi possível identificar a codificação de {caminho}") from ultimo_erro


def ler_csv_dados(caminho: Path, chave: str, tamanho_chave: int) -> dict[str, dict[str, Decimal]]:
    dados: dict[str, dict[str, Decimal]] = {}
    with abrir_csv_com_encoding(caminho) as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        if not leitor.fieldnames:
            raise ValueError(f"CSV sem cabeçalho: {caminho}")
        campos = {normalizar_texto(c): c for c in leitor.fieldnames}
        chave_real = campos.get(normalizar_texto(chave))
        if not chave_real:
            raise ValueError(f"Coluna {chave} não encontrada em {caminho.name}")
        metricas_reais: dict[str, str] = {}
        for metrica in METRICAS:
            real = campos.get(normalizar_texto(metrica))
            if not real:
                raise ValueError(f"Coluna {metrica} não encontrada em {caminho.name}")
            metricas_reais[metrica] = real

        for numero_linha, linha in enumerate(leitor, start=2):
            codigo = normalizar_codigo(linha.get(chave_real), tamanho_chave)
            if not codigo:
                raise ValueError(f"Código vazio em {caminho.name}, linha {numero_linha}")
            if len(codigo) != tamanho_chave:
                raise ValueError(
                    f"Código inválido {codigo!r} em {caminho.name}, linha {numero_linha}"
                )
            if codigo in dados:
                raise ValueError(f"Código duplicado {codigo} em {caminho.name}")
            dados[codigo] = {
                metrica: decimal_pt(linha.get(coluna_real))
                for metrica, coluna_real in metricas_reais.items()
            }
    return dados


def comparar_metricas(
    validador: Validador,
    etapa: str,
    entidade: str,
    esperado: dict[str, Decimal],
    encontrado: dict[str, Decimal],
) -> None:
    for metrica in METRICAS:
        exp = quantizar(esperado.get(metrica, ZERO), metrica)
        enc = quantizar(encontrado.get(metrica, ZERO), metrica)
        if not iguais(exp, enc, metrica):
            validador.erro(
                etapa,
                entidade,
                METRICAS_ROTULOS[metrica],
                exp,
                enc,
                enc - exp,
                "Valores divergentes.",
            )


def validar_somas_internas(
    validador: Validador,
    etapa: str,
    entidade: str,
    registro: dict[str, Decimal],
) -> None:
    combinacoes = [
        ("QUANTIDADE_BENEFICIOS_PCD", "QUANTIDADE_BENEFICIOS_IDOSO", "QUANTIDADE_TOTAL_BENEFICIOS"),
        ("RECURSOS_PAGOS_MES_PCD", "RECURSOS_PAGOS_MES_IDOSO", "RECURSOS_TOTAL_PAGOS_MES"),
        ("RECURSOS_TOTAL_PAGOS_ANO_PCD", "RECURSOS_TOTAL_PAGOS_ANO_IDOSO", "RECURSOS_TOTAL_PAGOS_ANO"),
    ]
    for a, b, total in combinacoes:
        calculado = registro[a] + registro[b]
        if not iguais(calculado, registro[total], total):
            validador.erro(
                etapa,
                entidade,
                METRICAS_ROTULOS[total],
                registro[total],
                calculado,
                calculado - registro[total],
                f"{METRICAS_ROTULOS[a]} + {METRICAS_ROTULOS[b]} não fecha com o total.",
            )


def validar_consultas(
    municipios: dict[str, dict[str, Decimal]],
    ufs: dict[str, dict[str, Decimal]],
    regioes: dict[str, dict[str, Decimal]],
    validador: Validador,
) -> dict[str, Decimal]:
    validador.log.escrever("\n==== VALIDAÇÃO DOS ARQUIVOS DE CONSULTA ====")

    for codigo, registro in municipios.items():
        validar_somas_internas(validador, "CSV Município", codigo, registro)
    for codigo, registro in ufs.items():
        validar_somas_internas(validador, "CSV UF", codigo, registro)
    for codigo, registro in regioes.items():
        validar_somas_internas(validador, "CSV Região", codigo, registro)

    municipios_por_uf: dict[str, list[dict[str, Decimal]]] = defaultdict(list)
    for codigo, registro in municipios.items():
        municipios_por_uf[codigo[:2]].append(registro)

    for uf, (_, nome) in UFS.items():
        if uf not in ufs:
            validador.erro("Municípios x UF", f"{uf} - {nome}", mensagem="UF ausente no CSV de UF.")
            continue
        soma = somar_registros(municipios_por_uf.get(uf, []))
        comparar_metricas(validador, "Municípios x UF", f"{uf} - {nome}", ufs[uf], soma)

    ufs_por_regiao: dict[str, list[dict[str, Decimal]]] = defaultdict(list)
    for uf, registro in ufs.items():
        ufs_por_regiao[uf[:1]].append(registro)

    for regiao, nome in REGIOES.items():
        if regiao not in regioes:
            validador.erro("UF x Região", f"{regiao} - {nome}", mensagem="Região ausente no CSV.")
            continue
        soma = somar_registros(ufs_por_regiao.get(regiao, []))
        comparar_metricas(validador, "UF x Região", f"{regiao} - {nome}", regioes[regiao], soma)

    total_uf = somar_registros(ufs.values())
    total_regiao = somar_registros(regioes.values())
    comparar_metricas(validador, "Região x Brasil", "Brasil", total_uf, total_regiao)

    if not validador.tem_erros:
        validador.log.escrever("[OK] Município, UF, região e Brasil fecham nos arquivos de consulta.")
    return total_uf


# ============================================================================
# CATÁLOGO DE MUNICÍPIOS
# ============================================================================

def carregar_municipios_novos_local(pasta_consultas: Path) -> dict[str, str]:
    mapa = dict(MUNICIPIOS_NOVOS_FIXOS)
    caminho = pasta_consultas / "cadastro_municipios_novos.csv"
    if not caminho.exists():
        return mapa
    with abrir_csv_com_encoding(caminho) as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        for linha in leitor:
            codigo = normalizar_codigo(linha.get("codigo") or linha.get("CODIGO"), 6)
            nome = str(linha.get("municipio") or linha.get("MUNICIPIO") or "").strip()
            if codigo and nome:
                mapa[codigo] = nome
    return mapa


def consultar_municipios_ibge(log: RegistroLog) -> dict[str, str]:
    url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
    try:
        log.escrever("[INFO] Consultando nomes de municípios na API do IBGE...")
        with urllib.request.urlopen(url, timeout=20) as resposta:
            dados = json.load(resposta)
        mapa = {
            str(item["id"])[:6]: str(item["nome"])
            for item in dados
            if item.get("id") and item.get("nome")
        }
        log.escrever(f"[OK] API do IBGE: {len(mapa)} municípios carregados.")
        return mapa
    except Exception as exc:
        log.escrever(f"[AVISO] Não foi possível consultar a API do IBGE: {exc}")
        return {}


# ============================================================================
# PREPARAÇÃO DOS MODELOS
# ============================================================================

def copiar_modelos_mes_anterior(ctx: Contexto, sobrescrever: bool, log: RegistroLog) -> None:
    ano_ant, mes_ant = referencia_anterior(ctx.ano, ctx.mes)
    pasta_anterior = Path(ctx.pasta_mes.parent.parent) / str(ano_ant) / f"{mes_ant:02d}{ano_ant}" / "EXCEL"
    if not pasta_anterior.exists():
        raise FileNotFoundError(f"Pasta de modelos do mês anterior não encontrada: {pasta_anterior}")
    ctx.pasta_excel.mkdir(parents=True, exist_ok=True)
    prefixo_anterior = MESES[mes_ant][1]
    copiados = 0
    for origem in pasta_anterior.iterdir():
        if origem.suffix.lower() not in EXTENSOES_EXCEL or origem.name.startswith("~$"):
            continue
        nome_novo = origem.name
        if nome_novo.lower().startswith(prefixo_anterior.lower()):
            nome_novo = ctx.prefixo + nome_novo[len(prefixo_anterior):]
        destino = ctx.pasta_excel / nome_novo
        if destino.exists() and not sobrescrever:
            continue
        shutil.copy2(origem, destino)
        copiados += 1
    log.escrever(f"[OK] Modelos copiados do mês anterior: {copiados} arquivo(s).")


def criar_backup(ctx: Contexto, arquivos: Iterable[Path], log: RegistroLog) -> Path:
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta = ctx.pasta_mes / f"BACKUP_{carimbo}"
    pasta.mkdir(parents=True, exist_ok=True)
    total = 0
    for arquivo in arquivos:
        if arquivo.exists():
            shutil.copy2(arquivo, pasta / arquivo.name)
            total += 1
    log.escrever(f"[OK] Backup criado: {pasta} ({total} arquivo(s)).")
    return pasta


# ============================================================================
# AUTOMAÇÃO DO EXCEL
# ============================================================================

class ExcelCOM:
    def __init__(self, log: RegistroLog, visivel: bool = False) -> None:
        try:
            import pythoncom  # type: ignore
            import pywintypes  # type: ignore
            import win32com.client as win32  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Instale o pywin32: pip install pywin32") from exc

        self.pythoncom = pythoncom
        self.pywintypes = pywintypes
        self.win32 = win32
        self.log = log
        self.app = None
        self._calculo_manual_configurado = False

        self.pythoncom.CoInitialize()
        try:
            self.app = win32.DispatchEx("Excel.Application")
            self.app.Visible = visivel
            self.app.DisplayAlerts = False
            self.app.AskToUpdateLinks = False
            self.app.EnableEvents = False
            self.app.ScreenUpdating = False
            self.app.DisplayStatusBar = False

            # Não define Calculation aqui. Em algumas instalações do Excel essa
            # propriedade só pode ser alterada depois que um workbook é aberto.
        except Exception:
            if self.app is not None:
                try:
                    self.app.Quit()
                except Exception:
                    pass
            self.pythoncom.CoUninitialize()
            raise

    def chamar(self, descricao: str, func, tentativas: int = 15):
        ultimo: Exception | None = None
        for tentativa in range(1, tentativas + 1):
            try:
                self.pythoncom.PumpWaitingMessages()
                return func()
            except self.pywintypes.com_error as exc:
                ultimo = exc
                texto = str(exc).lower()
                if "rejeitada pelo chamado" in texto or "call was rejected by callee" in texto:
                    time.sleep(min(0.35 * tentativa, 3.0))
                    continue
                raise
            except Exception as exc:
                ultimo = exc
                if tentativa < tentativas:
                    time.sleep(min(0.25 * tentativa, 2.0))
                    continue
                raise
        raise RuntimeError(f"Falha COM após tentativas: {descricao}") from ultimo

    def abrir(self, caminho: Path, somente_leitura: bool = False):
        wb = self.chamar(
            f"abrir {caminho.name}",
            lambda: self.app.Workbooks.Open(
                str(caminho), UpdateLinks=0, ReadOnly=somente_leitura, IgnoreReadOnlyRecommended=True
            ),
        )

        # Tenta ativar cálculo manual somente depois de existir workbook aberto.
        # Se o Excel não permitir, a automação continua em cálculo automático.
        if not self._calculo_manual_configurado:
            try:
                self.chamar(
                    "definir cálculo manual",
                    lambda: setattr(self.app, "Calculation", XL_CALCULATION_MANUAL),
                    tentativas=3,
                )
                self._calculo_manual_configurado = True
                self.log.escrever("[OK] Excel configurado para cálculo manual durante a atualização.")
            except Exception as exc:
                self.log.escrever(
                    "[AVISO] O Excel não permitiu alterar o modo de cálculo. "
                    f"A automação continuará em cálculo automático: {exc}"
                )
        return wb

    def fechar_livro(self, wb, salvar: bool = False) -> None:
        self.chamar("fechar workbook", lambda: wb.Close(SaveChanges=salvar))

    def salvar(self, wb) -> None:
        self.chamar("salvar workbook", wb.Save)

    def encerrar(self) -> None:
        try:
            if self.app is None:
                return

            # Cada restauração é independente para garantir que o Excel seja
            # encerrado mesmo quando uma propriedade específica rejeitar alteração.
            restauracoes = [
                ("atualização da tela", lambda: setattr(self.app, "ScreenUpdating", True)),
                ("eventos", lambda: setattr(self.app, "EnableEvents", True)),
                ("barra de status", lambda: setattr(self.app, "DisplayStatusBar", True)),
            ]
            for descricao, acao in restauracoes:
                try:
                    acao()
                except Exception as exc:
                    self.log.escrever(f"[AVISO] Não foi possível restaurar {descricao}: {exc}")

            try:
                self.app.Quit()
            except Exception as exc:
                self.log.escrever(f"[AVISO] Não foi possível encerrar o Excel normalmente: {exc}")
        finally:
            self.pythoncom.CoUninitialize()


def encontrar_aba(wb, preferida: str | None = None, contem: str | None = None):
    if preferida:
        try:
            return wb.Worksheets(preferida)
        except Exception:
            pass
    if contem:
        termo = normalizar_texto(contem)
        for ws in wb.Worksheets:
            if termo in normalizar_texto(ws.Name):
                return ws
    for ws in wb.Worksheets:
        if ws.Visible == -1:
            return ws
    return wb.Worksheets(1)


def valor_range(excel: ExcelCOM, ws, endereco: str):
    return excel.chamar(f"ler {endereco}", lambda: ws.Range(endereco).Value)


def escrever_range(excel: ExcelCOM, ws, endereco: str, valores: Any) -> None:
    excel.chamar(f"escrever {endereco}", lambda: setattr(ws.Range(endereco), "Value", valores))


def ultima_linha(excel: ExcelCOM, ws, coluna: str = "A") -> int:
    return int(
        excel.chamar(
            f"última linha {coluna}",
            lambda: ws.Cells(ws.Rows.Count, coluna).End(XL_UP).Row,
        )
    )


def matriz_2d(valor: Any) -> list[list[Any]]:
    if valor is None:
        return []
    if not isinstance(valor, tuple):
        return [[valor]]
    if valor and not isinstance(valor[0], tuple):
        return [list(valor)]
    return [list(linha) for linha in valor]


def mapa_linhas_codigos(excel: ExcelCOM, ws, inicio: int = 1) -> dict[str, int]:
    fim = ultima_linha(excel, ws, "A")
    valores = matriz_2d(valor_range(excel, ws, f"A{inicio}:A{fim}"))
    resultado: dict[str, int] = {}
    for deslocamento, linha in enumerate(valores):
        codigo = normalizar_codigo(linha[0] if linha else None)
        if len(codigo) in (1, 2, 6) and codigo.isdigit():
            resultado[codigo] = inicio + deslocamento
    return resultado


def copiar_formato_linha(excel: ExcelCOM, ws, origem: int, destino: int, col_final: str = "K") -> None:
    excel.chamar(
        "copiar formato",
        lambda: ws.Range(f"A{origem}:{col_final}{origem}").Copy(),
    )
    excel.chamar(
        "colar formato",
        lambda: ws.Range(f"A{destino}:{col_final}{destino}").PasteSpecial(Paste=XL_PASTE_FORMATS),
    )
    altura = excel.chamar("ler altura", lambda: ws.Rows(origem).RowHeight)
    excel.chamar("definir altura", lambda: setattr(ws.Rows(destino), "RowHeight", altura))
    excel.app.CutCopyMode = False


def inserir_municipio_ordenado(
    excel: ExcelCOM,
    ws,
    codigo: str,
    nome: str,
    col_final: str = "K",
) -> int:
    linhas = mapa_linhas_codigos(excel, ws, 1)
    if codigo in linhas:
        return linhas[codigo]
    uf = codigo[:2]
    municipais = sorted(
        ((cod, linha) for cod, linha in linhas.items() if len(cod) == 6 and cod[:2] == uf),
        key=lambda item: item[0],
    )
    if not municipais:
        raise RuntimeError(f"Não encontrei o bloco municipal da UF {uf} para inserir {codigo}.")
    posteriores = [(cod, linha) for cod, linha in municipais if cod > codigo]
    if posteriores:
        linha_destino = min(posteriores, key=lambda item: item[0])[1]
        linha_modelo_antes = linha_destino
    else:
        linha_destino = max(linha for _, linha in municipais) + 1
        linha_modelo_antes = linha_destino - 1

    excel.chamar(
        f"inserir linha {linha_destino}",
        lambda: ws.Rows(linha_destino).Insert(Shift=XL_SHIFT_DOWN),
    )
    # Após inserir antes de uma linha existente, o modelo passou uma linha para baixo.
    linha_modelo = linha_modelo_antes + 1 if posteriores else linha_modelo_antes
    copiar_formato_linha(excel, ws, linha_modelo, linha_destino, col_final)
    escrever_range(excel, ws, f"A{linha_destino}", codigo)
    escrever_range(excel, ws, f"B{linha_destino}", nome)
    return linha_destino


def extrair_catalogo_municipios(excel: ExcelCOM, ws) -> dict[str, str]:
    fim = ultima_linha(excel, ws, "A")
    valores = matriz_2d(valor_range(excel, ws, f"A1:B{fim}"))
    mapa: dict[str, str] = {}
    for linha in valores:
        codigo = normalizar_codigo(linha[0] if linha else None)
        nome = str(linha[1] or "").strip() if len(linha) > 1 else ""
        if len(codigo) == 6 and nome:
            mapa[codigo] = nome
    return mapa


def metricas_para_excel(registro: dict[str, Decimal]) -> list[Any]:
    saida: list[Any] = []
    for metrica in METRICAS:
        valor = quantizar(registro.get(metrica, ZERO), metrica)
        if metrica in METRICAS_QUANTIDADE:
            saida.append(int(valor))
        else:
            saida.append(float(valor))
    return saida


def metricas_do_excel(linha: list[Any], inicio: int) -> dict[str, Decimal]:
    resultado = zero_metricas()
    for indice, metrica in enumerate(METRICAS):
        posicao = inicio + indice
        valor = linha[posicao] if posicao < len(linha) else None
        resultado[metrica] = decimal_pt(valor)
    return resultado


def atualizar_cabecalho_periodo(excel: ExcelCOM, ws, ctx: Contexto) -> None:
    limite_coluna = min(int(ws.UsedRange.Columns.Count), 15)
    limite_linha = min(int(ws.UsedRange.Rows.Count), 8)
    mes = ctx.mes_nome
    ano = ctx.ano
    textos_exatos = {
        "mes": f"Recursos pagos no mês de {mes} de {ano}",
        "ano": f"Recursos pagos de Janeiro a {mes} de {ano}",
    }
    visitados: set[str] = set()
    for linha in range(1, limite_linha + 1):
        for coluna in range(1, limite_coluna + 1):
            cell = ws.Cells(linha, coluna)
            try:
                if cell.MergeCells:
                    cell = cell.MergeArea.Cells(1, 1)
                endereco = str(cell.Address)
                if endereco in visitados:
                    continue
                visitados.add(endereco)
                valor = excel.chamar("ler cabeçalho", lambda c=cell: c.Value)
                if not isinstance(valor, str):
                    continue
                norm = normalizar_texto(valor)
                novo = valor
                if "RECURSOS PAGOS NO MES DE" in norm:
                    novo = textos_exatos["mes"]
                elif "RECURSOS PAGOS DE JANEIRO A" in norm:
                    novo = textos_exatos["ano"]
                elif "BENEFICIOS ATIVOS EM" in norm:
                    novo = re.sub(
                        r"(?i)(benefícios\s+ativos\s+em\s+).*$",
                        rf"\1{mes} de {ano}",
                        valor,
                    )
                if novo != valor:
                    excel.chamar("atualizar cabeçalho", lambda c=cell, v=novo: setattr(c, "Value", v))
            except Exception:
                continue


def atualizar_planilha_municipio(
    excel: ExcelCOM,
    caminho: Path,
    municipios: dict[str, dict[str, Decimal]],
    ufs: dict[str, dict[str, Decimal]],
    total_brasil: dict[str, Decimal],
    nomes_externos: dict[str, str],
    ctx: Contexto,
    validador: Validador,
) -> dict[str, str]:
    """
    Atualiza a base geral de municípios.

    Estrutura real do modelo:
      - linha Brasil identificada pelo texto "Brasil" na coluna A;
      - municípios identificados por código IBGE de seis dígitos na coluna A;
      - não existem linhas de total por UF nessa planilha.

    O parâmetro ``ufs`` é mantido na assinatura para compatibilidade com o
    fluxo principal, mas os totais por UF são validados pela soma dos
    municípios, e não procurados como linhas dentro desse arquivo.
    """
    validador.log.escrever(f"\n[INFO] Atualizando base municipal: {caminho.name}")
    wb = excel.abrir(caminho)
    try:
        ws = encontrar_aba(wb, ABA_MUNICIPIO_PREFERIDA, "MUNIC")
        catalogo = extrair_catalogo_municipios(excel, ws)
        nomes = {**nomes_externos, **catalogo}

        ausentes = sorted(set(municipios) - set(catalogo))
        sem_nome = [codigo for codigo in ausentes if codigo not in nomes]
        if sem_nome:
            pendentes = ctx.pasta_consultas / f"municipios_sem_nome_{ctx.referencia}.csv"
            with pendentes.open("w", encoding="utf-8-sig", newline="") as arquivo:
                escritor = csv.writer(arquivo, delimiter=";")
                escritor.writerow(["codigo", "municipio"])
                for codigo in sem_nome:
                    escritor.writerow([codigo, ""])
            raise RuntimeError(
                "Municípios novos sem nome: " + ", ".join(sem_nome)
                + f". Preencha {pendentes.name} ou cadastro_municipios_novos.csv."
            )

        for codigo in ausentes:
            linha = inserir_municipio_ordenado(excel, ws, codigo, nomes[codigo])
            validador.novos_municipios.append(
                {
                    "codigo": codigo,
                    "municipio": nomes[codigo],
                    "uf": UFS[codigo[:2]][0],
                    "linha": str(linha),
                }
            )
            validador.log.escrever(f"[OK] Município incluído na base: {codigo} - {nomes[codigo]}")

        linhas = mapa_linhas_codigos(excel, ws, 1)
        linhas_municipais = [linha for cod, linha in linhas.items() if len(cod) == 6]
        if not linhas_municipais:
            raise RuntimeError("Nenhuma linha municipal foi encontrada na planilha geral.")

        inicio, fim = min(linhas_municipais), max(linhas_municipais)
        matriz = matriz_2d(valor_range(excel, ws, f"A{inicio}:K{fim}"))
        for linha_valores in matriz:
            codigo = normalizar_codigo(linha_valores[0] if linha_valores else None)
            if len(codigo) != 6:
                continue
            linha_valores[0] = codigo
            if codigo in nomes:
                linha_valores[1] = nomes[codigo]
            if codigo in municipios:
                linha_valores[2:11] = metricas_para_excel(municipios[codigo])
            else:
                linha_valores[2:11] = metricas_para_excel(zero_metricas())
                validador.aviso(
                    "Atualização Município",
                    codigo,
                    mensagem="Código existe no modelo, mas não apareceu no CSV; valores zerados.",
                )

        escrever_range(excel, ws, f"A{inicio}:K{fim}", tuple(tuple(l) for l in matriz))

        # No modelo municipal, Brasil fica na coluna A e as métricas em C:K.
        linha_brasil = localizar_linha_por_texto_coluna(excel, ws, ["Brasil"], "A", limite=30)
        if linha_brasil:
            escrever_range(
                excel,
                ws,
                f"C{linha_brasil}:K{linha_brasil}",
                (tuple(metricas_para_excel(total_brasil)),),
            )
        else:
            validador.erro(
                "Atualização Município",
                "Brasil",
                mensagem="Linha de total Brasil não encontrada na coluna A da planilha municipal.",
            )

        atualizar_cabecalho_periodo(excel, ws, ctx)
        excel.salvar(wb)
        return nomes
    finally:
        excel.fechar_livro(wb, salvar=False)

def identificar_uf_arquivo(caminho: Path) -> str | None:
    stem = normalizar_texto(caminho.stem).replace(" ", "")
    for codigo, (sigla, _) in UFS.items():
        if stem.endswith(sigla):
            return codigo
    return None


def listar_planilhas_uf(pasta: Path) -> dict[str, Path]:
    resultado: dict[str, Path] = {}
    for caminho in pasta.iterdir():
        if caminho.suffix.lower() not in EXTENSOES_EXCEL or caminho.name.startswith("~$"):
            continue
        nome = normalizar_texto(caminho.name)
        if "BPC_" in nome or "BPC " in nome or "REVISAO" in nome:
            continue
        uf = identificar_uf_arquivo(caminho)
        if uf:
            resultado[uf] = caminho
    return resultado


def atualizar_planilha_uf(
    excel: ExcelCOM,
    caminho: Path,
    uf: str,
    municipios: dict[str, dict[str, Decimal]],
    total_uf: dict[str, Decimal],
    nomes: dict[str, str],
    ctx: Contexto,
    validador: Validador,
) -> None:
    sigla, nome_uf = UFS[uf]
    validador.log.escrever(f"[INFO] Atualizando {sigla}: {caminho.name}")
    wb = excel.abrir(caminho)
    try:
        ws = encontrar_aba(wb, sigla)
        catalogo = extrair_catalogo_municipios(excel, ws)
        esperados = sorted(c for c in municipios if c[:2] == uf)
        ausentes = [c for c in esperados if c not in catalogo]
        for codigo in ausentes:
            nome = nomes.get(codigo)
            if not nome:
                raise RuntimeError(f"Nome não encontrado para {codigo}")
            inserir_municipio_ordenado(excel, ws, codigo, nome)
            validador.log.escrever(f"    [OK] Incluído: {codigo} - {nome}")

        linhas = mapa_linhas_codigos(excel, ws, 1)
        linha_uf = linhas.get(uf)
        if not linha_uf:
            raise RuntimeError(f"Linha total da UF {uf} não encontrada em {caminho.name}")
        linhas_municipais = sorted(l for c, l in linhas.items() if len(c) == 6 and c[:2] == uf)
        if not linhas_municipais:
            raise RuntimeError(f"Municípios da UF {uf} não encontrados em {caminho.name}")
        inicio, fim = linha_uf, max(linhas_municipais)
        matriz = matriz_2d(valor_range(excel, ws, f"A{inicio}:K{fim}"))
        for linha_valores in matriz:
            codigo = normalizar_codigo(linha_valores[0] if linha_valores else None)
            if codigo == uf:
                linha_valores[0] = uf
                linha_valores[1] = nome_uf
                linha_valores[2:11] = metricas_para_excel(total_uf)
            elif len(codigo) == 6 and codigo[:2] == uf:
                linha_valores[0] = codigo
                linha_valores[1] = nomes.get(codigo, linha_valores[1])
                if codigo in municipios:
                    linha_valores[2:11] = metricas_para_excel(municipios[codigo])
                else:
                    linha_valores[2:11] = metricas_para_excel(zero_metricas())
                    validador.aviso(
                        "Atualização UF",
                        f"{sigla} - {codigo}",
                        mensagem="Município do modelo não apareceu no CSV; valores zerados.",
                    )
        escrever_range(excel, ws, f"A{inicio}:K{fim}", tuple(tuple(l) for l in matriz))
        atualizar_cabecalho_periodo(excel, ws, ctx)
        excel.salvar(wb)
    finally:
        excel.fechar_livro(wb, salvar=False)


def localizar_especial(pasta: Path, termo: str) -> Path:
    candidatos = [
        p for p in pasta.iterdir()
        if p.suffix.lower() in EXTENSOES_EXCEL and termo in normalizar_texto(p.name).replace(" ", "_")
    ]
    if not candidatos:
        raise FileNotFoundError(f"Planilha {termo} não encontrada em {pasta}")
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def localizar_linha_por_texto(excel: ExcelCOM, ws, textos: Iterable[str], limite: int = 50) -> int | None:
    return localizar_linha_por_texto_coluna(excel, ws, textos, "A", limite)


def localizar_linha_por_texto_coluna(
    excel: ExcelCOM, ws, textos: Iterable[str], coluna: str, limite: int = 50
) -> int | None:
    normalizados = {normalizar_texto(t) for t in textos}
    fim = min(ultima_linha(excel, ws, coluna), limite)
    valores = matriz_2d(valor_range(excel, ws, f"{coluna}1:{coluna}{fim}"))
    for indice, linha in enumerate(valores, start=1):
        valor = normalizar_texto(linha[0] if linha else None)
        if valor in normalizados:
            return indice
    return None


def atualizar_brasil(
    excel: ExcelCOM,
    caminho: Path,
    ufs: dict[str, dict[str, Decimal]],
    total_brasil: dict[str, Decimal],
    ctx: Contexto,
    validador: Validador,
) -> None:
    """Atualiza o total Brasil e as 27 linhas de UF da planilha Brasil."""
    validador.log.escrever(f"[INFO] Atualizando Brasil e UFs: {caminho.name}")
    wb = excel.abrir(caminho)
    try:
        ws = encontrar_aba(wb, "BRASIL", "BRASIL")

        linha_brasil = localizar_linha_por_texto(excel, ws, ["Brasil"], limite=60) or 9
        escrever_range(excel, ws, f"A{linha_brasil}", "Brasil")
        escrever_range(
            excel,
            ws,
            f"B{linha_brasil}:J{linha_brasil}",
            (tuple(metricas_para_excel(total_brasil)),),
        )

        # O modelo traz as UFs nas linhas seguintes ao Brasil. Procuramos pelo
        # nome para não depender de posição fixa e usamos a ordem oficial apenas
        # como fallback.
        fim = min(ultima_linha(excel, ws, "A"), linha_brasil + 40)
        valores = matriz_2d(valor_range(excel, ws, f"A{linha_brasil + 1}:A{fim}"))
        linhas_por_nome: dict[str, int] = {}
        for linha_excel, linha_valores in enumerate(valores, start=linha_brasil + 1):
            nome = normalizar_texto(linha_valores[0] if linha_valores else None)
            if nome:
                linhas_por_nome[nome] = linha_excel

        for ordem, (codigo, (_, nome_uf)) in enumerate(UFS.items(), start=1):
            linha = linhas_por_nome.get(normalizar_texto(nome_uf), linha_brasil + ordem)
            escrever_range(excel, ws, f"A{linha}", nome_uf)
            escrever_range(
                excel,
                ws,
                f"B{linha}:J{linha}",
                (tuple(metricas_para_excel(ufs[codigo])),),
            )

        atualizar_cabecalho_periodo(excel, ws, ctx)
        excel.salvar(wb)
    finally:
        excel.fechar_livro(wb, salvar=False)

def atualizar_regiao(
    excel: ExcelCOM,
    caminho: Path,
    regioes: dict[str, dict[str, Decimal]],
    total_brasil: dict[str, Decimal],
    ctx: Contexto,
    validador: Validador,
) -> None:
    """Atualiza, em bloco, Brasil e as cinco regiões do modelo."""
    validador.log.escrever(f"[INFO] Atualizando regiões: {caminho.name}")
    wb = excel.abrir(caminho)
    try:
        ws = encontrar_aba(wb, "BRASIL REG", "REG")
        linha_brasil = localizar_linha_por_texto(excel, ws, ["Brasil"], limite=40) or 9

        # A estrutura do modelo é Brasil, Norte, Nordeste, Sudeste, Sul e
        # Centro-Oeste em seis linhas consecutivas. Gravar o bloco inteiro evita
        # qualquer deslocamento ou leitura de uma linha incorreta.
        bloco = [["Brasil", *metricas_para_excel(total_brasil)]]
        for codigo, nome in REGIOES.items():
            bloco.append([nome, *metricas_para_excel(regioes[codigo])])
        escrever_range(
            excel,
            ws,
            f"A{linha_brasil}:J{linha_brasil + len(bloco) - 1}",
            tuple(tuple(linha) for linha in bloco),
        )

        atualizar_cabecalho_periodo(excel, ws, ctx)
        excel.salvar(wb)
    finally:
        excel.fechar_livro(wb, salvar=False)


# ============================================================================
# VALIDAÇÃO DOS ARQUIVOS EXCEL ATUALIZADOS
# ============================================================================

def ler_linhas_codigo_metricas(
    excel: ExcelCOM,
    ws,
    col_inicio_metricas: int,
) -> dict[str, dict[str, Decimal]]:
    fim = ultima_linha(excel, ws, "A")
    letra_fim = "K" if col_inicio_metricas == 2 else "J"
    valores = matriz_2d(valor_range(excel, ws, f"A1:{letra_fim}{fim}"))
    resultado: dict[str, dict[str, Decimal]] = {}
    for linha in valores:
        codigo = normalizar_codigo(linha[0] if linha else None)
        if len(codigo) in (1, 2, 6) and codigo.isdigit():
            resultado[codigo] = metricas_do_excel(linha, col_inicio_metricas)
    return resultado


def ler_linha_texto_metricas(excel: ExcelCOM, ws, texto: str) -> dict[str, Decimal] | None:
    linha = localizar_linha_por_texto(excel, ws, [texto], limite=60)
    if not linha:
        return None
    valores = matriz_2d(valor_range(excel, ws, f"A{linha}:J{linha}"))[0]
    return metricas_do_excel(valores, 1)


def validar_excel_municipio(
    excel: ExcelCOM,
    caminho: Path,
    municipios: dict[str, dict[str, Decimal]],
    ufs: dict[str, dict[str, Decimal]],
    total_brasil: dict[str, Decimal],
    validador: Validador,
) -> None:
    wb = excel.abrir(caminho, somente_leitura=True)
    try:
        ws = encontrar_aba(wb, ABA_MUNICIPIO_PREFERIDA, "MUNIC")
        dados = ler_linhas_codigo_metricas(excel, ws, 2)
        dados_municipais = {codigo: reg for codigo, reg in dados.items() if len(codigo) == 6}

        for codigo, esperado in municipios.items():
            if codigo not in dados_municipais:
                validador.erro("Excel Município", codigo, mensagem="Município não encontrado após atualização.")
            else:
                comparar_metricas(
                    validador,
                    "Excel Município",
                    codigo,
                    esperado,
                    dados_municipais[codigo],
                )

        # A planilha municipal não contém linhas de total por UF. A validação
        # correta é somar os municípios por prefixo IBGE e comparar com o CSV UF.
        for uf, esperado in ufs.items():
            registros_uf = [
                registro
                for codigo, registro in dados_municipais.items()
                if codigo[:2] == uf
            ]
            soma_uf = somar_registros(registros_uf)
            comparar_metricas(
                validador,
                "Excel Município - Soma UF",
                UFS[uf][0],
                esperado,
                soma_uf,
            )

        linha_brasil = localizar_linha_por_texto_coluna(excel, ws, ["Brasil"], "A", limite=30)
        if not linha_brasil:
            validador.erro("Excel Município - Brasil", "Brasil", mensagem="Total Brasil não encontrado.")
        else:
            linha = matriz_2d(valor_range(excel, ws, f"A{linha_brasil}:K{linha_brasil}"))[0]
            comparar_metricas(
                validador,
                "Excel Município - Brasil",
                "Brasil",
                total_brasil,
                metricas_do_excel(linha, 2),
            )

        soma_brasil = somar_registros(dados_municipais.values())
        comparar_metricas(
            validador,
            "Excel Município - Soma Brasil",
            "Brasil",
            total_brasil,
            soma_brasil,
        )
    finally:
        excel.fechar_livro(wb, salvar=False)

def validar_excel_uf(
    excel: ExcelCOM,
    caminho: Path,
    uf: str,
    municipios: dict[str, dict[str, Decimal]],
    total_uf: dict[str, Decimal],
    validador: Validador,
) -> None:
    sigla = UFS[uf][0]
    wb = excel.abrir(caminho, somente_leitura=True)
    try:
        ws = encontrar_aba(wb, sigla)
        dados = ler_linhas_codigo_metricas(excel, ws, 2)
        if uf not in dados:
            validador.erro("Excel UF", sigla, mensagem="Linha total da UF não encontrada.")
        else:
            comparar_metricas(validador, "Excel UF - Total", sigla, total_uf, dados[uf])
        dados_municipais = {
            codigo: registro
            for codigo, registro in dados.items()
            if len(codigo) == 6 and codigo[:2] == uf
        }
        soma_planilha = somar_registros(dados_municipais.values())
        comparar_metricas(validador, "Soma Municípios da UF", sigla, total_uf, soma_planilha)
        esperados = {c: r for c, r in municipios.items() if c[:2] == uf}
        for codigo, esperado in esperados.items():
            if codigo not in dados_municipais:
                validador.erro("Excel UF - Município", f"{sigla}/{codigo}", mensagem="Município ausente.")
            else:
                comparar_metricas(
                    validador, "Excel UF - Município", f"{sigla}/{codigo}", esperado, dados_municipais[codigo]
                )
    finally:
        excel.fechar_livro(wb, salvar=False)


def validar_excel_regiao(
    excel: ExcelCOM,
    caminho: Path,
    regioes: dict[str, dict[str, Decimal]],
    total_brasil: dict[str, Decimal],
    validador: Validador,
) -> None:
    wb = excel.abrir(caminho, somente_leitura=True)
    try:
        ws = encontrar_aba(wb, "BRASIL REG", "REG")
        brasil = ler_linha_texto_metricas(excel, ws, "Brasil")
        if brasil is None:
            validador.erro("Excel Região", "Brasil", mensagem="Linha Brasil não encontrada.")
        else:
            comparar_metricas(validador, "Excel Região - Brasil", "Brasil", total_brasil, brasil)
        for codigo, nome in REGIOES.items():
            registro = ler_linha_texto_metricas(excel, ws, nome)
            if registro is None:
                validador.erro("Excel Região", nome, mensagem="Linha da região não encontrada.")
            else:
                comparar_metricas(validador, "Excel Região", nome, regioes[codigo], registro)
    finally:
        excel.fechar_livro(wb, salvar=False)


def validar_excel_brasil(
    excel: ExcelCOM,
    caminho: Path,
    ufs: dict[str, dict[str, Decimal]],
    total_brasil: dict[str, Decimal],
    validador: Validador,
) -> None:
    wb = excel.abrir(caminho, somente_leitura=True)
    try:
        ws = encontrar_aba(wb, "BRASIL", "BRASIL")

        registro = ler_linha_texto_metricas(excel, ws, "Brasil")
        if registro is None:
            linha = matriz_2d(valor_range(excel, ws, "A9:J9"))[0]
            registro = metricas_do_excel(linha, 1)
        comparar_metricas(validador, "Excel Brasil", "Brasil", total_brasil, registro)

        # Valida também as 27 UFs da planilha Brasil, não apenas o total nacional.
        for codigo, (_, nome_uf) in UFS.items():
            registro_uf = ler_linha_texto_metricas(excel, ws, nome_uf)
            if registro_uf is None:
                validador.erro(
                    "Excel Brasil - UF",
                    UFS[codigo][0],
                    mensagem="Linha da UF não encontrada na planilha Brasil.",
                )
            else:
                comparar_metricas(
                    validador,
                    "Excel Brasil - UF",
                    UFS[codigo][0],
                    ufs[codigo],
                    registro_uf,
                )
    finally:
        excel.fechar_livro(wb, salvar=False)


# ============================================================================
# RELATÓRIO DE REVISÃO E PDF
# ============================================================================

def criar_relatorio_revisao(
    excel: ExcelCOM,
    ctx: Contexto,
    validador: Validador,
    total_brasil: dict[str, Decimal],
) -> Path:
    caminho = ctx.pasta_mes / f"revisao_{ctx.referencia}.xlsx"
    wb = excel.chamar("criar revisão", lambda: excel.app.Workbooks.Add())
    try:
        resumo = wb.Worksheets(1)
        resumo.Name = "Resumo"
        divergencias = wb.Worksheets.Add(After=resumo)
        divergencias.Name = "Divergencias"
        novos = wb.Worksheets.Add(After=divergencias)
        novos.Name = "Municipios Novos"

        status = "ERRO" if validador.tem_erros else "OK"
        resumo_dados = [
            [f"Revisão do Relatório BPC - {ctx.mes_nome} de {ctx.ano}", ""],
            ["Referência", ctx.referencia],
            ["Status geral", status],
            ["Erros", validador.total_erros],
            ["Avisos", validador.total_avisos],
            ["Municípios novos incluídos", len(validador.novos_municipios)],
            ["", ""],
            ["Métrica", "Total Brasil"],
        ]
        for metrica in METRICAS:
            resumo_dados.append([METRICAS_ROTULOS[metrica], float(total_brasil[metrica])])
        escrever_range(excel, resumo, f"A1:B{len(resumo_dados)}", tuple(tuple(r) for r in resumo_dados))

        cab = ["Severidade", "Etapa", "Entidade", "Métrica", "Esperado", "Encontrado", "Diferença", "Mensagem"]
        linhas = [cab] + [
            [
                i.severidade,
                i.etapa,
                i.entidade,
                i.metrica,
                i.esperado,
                i.encontrado,
                i.diferenca,
                i.mensagem,
            ]
            for i in validador.itens
        ]
        escrever_range(excel, divergencias, f"A1:H{max(1, len(linhas))}", tuple(tuple(r) for r in linhas))

        novos_linhas = [["Código", "Município", "UF", "Linha incluída"]]
        novos_linhas += [
            [n.get("codigo", ""), n.get("municipio", ""), n.get("uf", ""), n.get("linha", "")]
            for n in validador.novos_municipios
        ]
        escrever_range(excel, novos, f"A1:D{len(novos_linhas)}", tuple(tuple(r) for r in novos_linhas))

        # Formatação simples e legível.
        for ws, colunas in ((resumo, "A:B"), (divergencias, "A:H"), (novos, "A:D")):
            excel.chamar("autofit", lambda s=ws, c=colunas: s.Columns(c).AutoFit())
            excel.chamar("cabeçalho negrito", lambda s=ws: setattr(s.Rows(1).Font, "Bold", True))
        resumo.Range("A1:B1").Merge()
        resumo.Range("A1").Font.Bold = True
        resumo.Range("A1").Font.Size = 14
        resumo.Range("A3:B3").Font.Bold = True
        if status == "OK":
            resumo.Range("B3").Interior.Color = 13561798  # verde claro
        else:
            resumo.Range("B3").Interior.Color = 13551615  # vermelho claro
        divergencias.Rows(1).Font.Bold = True
        novos.Rows(1).Font.Bold = True
        divergencias.Range("A1:H1").AutoFilter()

        if caminho.exists():
            caminho.unlink()
        excel.chamar(
            "salvar revisão",
            lambda: wb.SaveAs(str(caminho), FileFormat=XL_OPEN_XML_WORKBOOK),
        )
        validador.log.escrever(f"[OK] Relatório de revisão: {caminho}")
        return caminho
    finally:
        excel.fechar_livro(wb, salvar=False)


def aguardar_arquivo(caminho: Path, timeout: int = 30) -> bool:
    inicio = time.time()
    while time.time() - inicio < timeout:
        if caminho.exists() and caminho.stat().st_size > 0:
            return True
        time.sleep(0.5)
    return False


def exportar_pdfs(
    excel: ExcelCOM,
    arquivos: Iterable[Path],
    pasta_pdf: Path,
    log: RegistroLog,
) -> tuple[int, int]:
    pasta_pdf.mkdir(parents=True, exist_ok=True)
    ok = 0
    erros = 0
    for caminho in arquivos:
        wb = None
        try:
            log.escrever(f"[INFO] Exportando PDF: {caminho.name}")
            wb = excel.abrir(caminho, somente_leitura=True)
            ws = encontrar_aba(wb)
            destino = pasta_pdf / f"{caminho.stem}.pdf"
            if destino.exists():
                destino.unlink()
            excel.chamar(
                "exportar PDF",
                lambda: ws.ExportAsFixedFormat(
                    Type=XL_TYPE_PDF,
                    Filename=str(destino),
                    Quality=XL_QUALITY_STANDARD,
                    IncludeDocProperties=True,
                    IgnorePrintAreas=False,
                    OpenAfterPublish=False,
                ),
            )
            if not aguardar_arquivo(destino):
                raise RuntimeError("O Excel não confirmou a criação do PDF.")
            ok += 1
            log.escrever(f"[OK] PDF: {destino.name}")
        except Exception as exc:
            erros += 1
            log.escrever(f"[ERRO] PDF {caminho.name}: {exc}")
        finally:
            if wb is not None:
                try:
                    excel.fechar_livro(wb, salvar=False)
                except Exception:
                    pass
    return ok, erros


def salvar_divergencias_csv(ctx: Contexto, validador: Validador) -> Path:
    caminho = ctx.pasta_mes / f"divergencias_{ctx.referencia}.csv"
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        campos = list(asdict(Divergencia("", "", "")).keys())
        escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        for item in validador.itens:
            escritor.writerow(asdict(item))
    return caminho


# ============================================================================
# FLUXO PRINCIPAL
# ============================================================================

def processar(args: argparse.Namespace) -> int:
    ctx = construir_contexto(args)
    ctx.pasta_mes.mkdir(parents=True, exist_ok=True)
    ctx.pasta_consultas.mkdir(parents=True, exist_ok=True)
    log = RegistroLog(ctx.pasta_mes / f"automacao_{ctx.referencia}.log")
    validador = Validador(log)
    excel: ExcelCOM | None = None

    try:
        log.escrever("=" * 78)
        log.escrever(f"AUTOMAÇÃO DO RELATÓRIO BPC - REFERÊNCIA {ctx.referencia}")
        log.escrever("=" * 78)
        log.escrever(f"Consultas: {ctx.pasta_consultas}")
        log.escrever(f"Excel:     {ctx.pasta_excel}")
        log.escrever(f"PDF:       {ctx.pasta_pdf}")

        sqls = gerar_arquivos_sql(ctx, log)
        if args.executar_consultas:
            executar_consultas_teradata(ctx, sqls, log)

        csv_municipio = localizar_csv(ctx.pasta_consultas, "municipio", ctx.referencia)
        csv_uf = localizar_csv(ctx.pasta_consultas, "uf", ctx.referencia)
        csv_regiao = localizar_csv(ctx.pasta_consultas, "regiao", ctx.referencia)
        log.escrever(f"[OK] CSV município: {csv_municipio.name}")
        log.escrever(f"[OK] CSV UF:        {csv_uf.name}")
        log.escrever(f"[OK] CSV região:    {csv_regiao.name}")

        municipios = ler_csv_dados(csv_municipio, "MUNICIPIO", 6)
        ufs = ler_csv_dados(csv_uf, "UF", 2)
        regioes = ler_csv_dados(csv_regiao, "REGIAO", 1)
        log.escrever(
            f"[INFO] Registros: {len(municipios)} municípios, {len(ufs)} UFs e {len(regioes)} regiões."
        )

        total_brasil = validar_consultas(municipios, ufs, regioes, validador)
        if validador.tem_erros and not args.continuar_com_erros:
            salvar_divergencias_csv(ctx, validador)
            log.escrever("[ERRO] Os CSVs não fecharam. Nenhuma planilha foi alterada.")
            return 2

        if args.validar_somente_csv:
            caminho = salvar_divergencias_csv(ctx, validador)
            log.escrever(f"[OK] Validação somente CSV finalizada: {caminho}")
            return 0 if not validador.tem_erros else 2

        # Por padrão, completa a pasta EXCEL com os modelos do mês anterior.
        # Arquivos que já existem não são sobrescritos.
        if not args.nao_copiar_modelos:
            copiar_modelos_mes_anterior(ctx, args.sobrescrever_modelos, log)
        if not ctx.pasta_excel.exists():
            raise FileNotFoundError(f"Pasta EXCEL não encontrada: {ctx.pasta_excel}")
        ctx.pasta_pdf.mkdir(parents=True, exist_ok=True)

        arquivo_municipio = localizar_especial(ctx.pasta_excel, "BPC_MUNICIPIO")
        arquivo_regiao = localizar_especial(ctx.pasta_excel, "BPC_REGIAO")
        arquivo_brasil = localizar_especial(ctx.pasta_excel, "BPC_BRASIL")
        arquivos_uf = listar_planilhas_uf(ctx.pasta_excel)
        faltantes = [UFS[uf][0] for uf in UFS if uf not in arquivos_uf]
        if faltantes:
            raise FileNotFoundError("Planilhas estaduais ausentes: " + ", ".join(faltantes))

        arquivos_relatorio = [arquivo_municipio, arquivo_regiao, arquivo_brasil] + [
            arquivos_uf[uf] for uf in UFS
        ]
        if not args.sem_backup:
            criar_backup(ctx, arquivos_relatorio, log)

        nomes_locais = carregar_municipios_novos_local(ctx.pasta_consultas)
        nomes_ibge = {} if args.nao_consultar_ibge else consultar_municipios_ibge(log)
        nomes_externos = {**nomes_ibge, **nomes_locais}

        excel = ExcelCOM(log, visivel=args.excel_visivel)
        nomes = atualizar_planilha_municipio(
            excel,
            arquivo_municipio,
            municipios,
            ufs,
            total_brasil,
            nomes_externos,
            ctx,
            validador,
        )
        for uf in UFS:
            atualizar_planilha_uf(
                excel,
                arquivos_uf[uf],
                uf,
                municipios,
                ufs[uf],
                nomes,
                ctx,
                validador,
            )
        atualizar_regiao(excel, arquivo_regiao, regioes, total_brasil, ctx, validador)
        atualizar_brasil(excel, arquivo_brasil, ufs, total_brasil, ctx, validador)

        # Reabre os arquivos e valida o que foi efetivamente salvo.
        log.escrever("\n==== VALIDAÇÃO DOS ARQUIVOS EXCEL ====")
        validar_excel_municipio(excel, arquivo_municipio, municipios, ufs, total_brasil, validador)
        for uf in UFS:
            validar_excel_uf(excel, arquivos_uf[uf], uf, municipios, ufs[uf], validador)
        validar_excel_regiao(excel, arquivo_regiao, regioes, total_brasil, validador)
        validar_excel_brasil(excel, arquivo_brasil, ufs, total_brasil, validador)

        criar_relatorio_revisao(excel, ctx, validador, total_brasil)
        caminho_div = salvar_divergencias_csv(ctx, validador)
        log.escrever(f"[OK] CSV de validação: {caminho_div}")

        if validador.tem_erros and not args.gerar_pdf_com_erros:
            log.escrever(
                f"[ERRO] Foram encontrados {validador.total_erros} erro(s). PDFs não foram gerados."
            )
            return 3

        ok_pdf, erros_pdf = exportar_pdfs(excel, arquivos_relatorio, ctx.pasta_pdf, log)
        log.escrever("\n" + "=" * 78)
        log.escrever("PROCESSAMENTO FINALIZADO")
        log.escrever(f"Status da validação: {'ERRO' if validador.tem_erros else 'OK'}")
        log.escrever(f"Erros: {validador.total_erros} | Avisos: {validador.total_avisos}")
        log.escrever(f"PDFs gerados: {ok_pdf} | Falhas de PDF: {erros_pdf}")
        log.escrever("=" * 78)
        return 0 if not validador.tem_erros and erros_pdf == 0 else 4

    except Exception as exc:
        log.escrever(f"\n[ERRO GERAL] {exc}")
        log.escrever(traceback.format_exc())
        return 1
    finally:
        if excel is not None:
            try:
                excel.encerrar()
                log.escrever("[OK] Excel encerrado.")
            except Exception as exc:
                log.escrever(f"[AVISO] Falha ao encerrar o Excel: {exc}")
        log.fechar()


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Automatiza o relatório mensal de BPC: SQL/CSV, atualização das planilhas, "
            "inclusão de novos municípios, validação e exportação dos PDFs."
        )
    )
    parser.add_argument("--ref", required=True, help="Referência AAAAMM, por exemplo 202607.")
    parser.add_argument("--raiz", default=str(RAIZ_PADRAO), help="Pasta raiz do relatório BPC.")
    parser.add_argument("--consultas-dir", help="Sobrescreve a pasta CONSULTAS calculada pela referência.")
    parser.add_argument("--excel-dir", help="Sobrescreve a pasta EXCEL calculada pela referência.")
    parser.add_argument("--pdf-dir", help="Sobrescreve a pasta PDF calculada pela referência.")
    parser.add_argument("--executar-consultas", action="store_true", help="Executa as três consultas no Teradata.")
    parser.add_argument("--validar-somente-csv", action="store_true", help="Valida os CSVs e não abre o Excel.")
    parser.add_argument(
        "--nao-copiar-modelos",
        action="store_true",
        help="Não completa automaticamente a pasta EXCEL com os modelos do mês anterior.",
    )
    parser.add_argument("--sobrescrever-modelos", action="store_true", help="Sobrescreve modelos já existentes.")
    parser.add_argument("--sem-backup", action="store_true", help="Não cria backup antes das alterações.")
    parser.add_argument("--nao-consultar-ibge", action="store_true", help="Não tenta obter nomes pela API do IBGE.")
    parser.add_argument("--continuar-com-erros", action="store_true", help="Continua mesmo se os CSVs não fecharem.")
    parser.add_argument("--gerar-pdf-com-erros", action="store_true", help="Gera PDFs mesmo com erro na validação final.")
    parser.add_argument("--excel-visivel", action="store_true", help="Deixa o Excel visível durante o processamento.")
    return parser


def main() -> None:
    parser = criar_parser()
    args = parser.parse_args()
    raise SystemExit(processar(args))


if __name__ == "__main__":
    main()