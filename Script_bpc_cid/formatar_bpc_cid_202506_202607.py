from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

# -----------------------------------------------------------------------------
# TÍTULOS INSTITUCIONAIS CORRETOS
# -----------------------------------------------------------------------------
TITULO_1 = "Projeto demonstrativo de analise de beneficios"
TITULO_2 = "Portfolio de engenharia de dados"
TITULO_3 = "Relatorio de exemplo"
TITULO_5 = "CID e Descrição"
FONTE = "Fonte: dados de demonstracao"
NOTA = "Nota1: A UF de referência é da ordem pagadora"

MESES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

REF_INICIAL_ANTIGOS = 201901
REF_FINAL_ANTIGOS = 202506
REF_INICIAL_NOVOS = 202506
REF_FINAL_NOVOS = 202607

PASTA_BASE_PADRAO = Path("dados/modelos")
PASTA_ENTRADA_PADRAO = PASTA_BASE_PADRAO / "202506_202607"
MODELO_PADRAO = PASTA_BASE_PADRAO / "BPC_CID_202506_titulo_atualizado.xlsx"
PASTA_SAIDA_PADRAO = PASTA_ENTRADA_PADRAO / "FORMATADOS"

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


# -----------------------------------------------------------------------------
# FUNÇÕES GERAIS
# -----------------------------------------------------------------------------
def extrair_referencia(nome: str) -> int | None:
    """Extrai uma referência AAAAMM válida do nome do arquivo."""
    candidatos = re.findall(r"(?<!\d)(20\d{4})(?!\d)", nome)
    for texto in candidatos:
        ref = int(texto)
        mes = ref % 100
        if 1 <= mes <= 12:
            return ref
    return None


def titulo_periodo(ref: int) -> str:
    ano, mes = divmod(ref, 100)
    if mes not in MESES:
        raise ValueError(f"Referência inválida: {ref}")
    return (
        "Benefício de Prestação Continuada (BPC) - "
        f"Benefícios PCD ativos em {MESES[mes]} {ano}"
    )


def caminho_dentro_de(caminho: Path, pasta: Path) -> bool:
    try:
        caminho.resolve().relative_to(pasta.resolve())
        return True
    except ValueError:
        return False


def copiar_zip_com_alteracoes(
    origem: Path,
    destino: Path,
    alteracoes: dict[str, bytes],
) -> None:
    """Copia um XLSX (ZIP) preservando seus componentes e troca partes indicadas."""
    destino.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=destino.stem + "_",
        suffix=".xlsx",
        dir=destino.parent,
        delete=False,
    ) as temporario:
        caminho_temp = Path(temporario.name)

    try:
        with zipfile.ZipFile(origem, "r") as zin, zipfile.ZipFile(
            caminho_temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zout:
            nomes = set(zin.namelist())
            faltantes = set(alteracoes) - nomes
            if faltantes:
                raise ValueError(
                    "O arquivo modelo não possui as partes esperadas: "
                    + ", ".join(sorted(faltantes))
                )

            for item in zin.infolist():
                dados = alteracoes.get(item.filename, zin.read(item.filename))
                zout.writestr(item, dados)

        # Teste estrutural básico do ZIP antes de substituir/gravar o resultado.
        with zipfile.ZipFile(caminho_temp, "r") as teste:
            erro = teste.testzip()
            if erro:
                raise ValueError(f"Falha de integridade no XLSX gerado: {erro}")

        caminho_temp.replace(destino)
    except Exception:
        caminho_temp.unlink(missing_ok=True)
        raise


def obter_primeira_planilha(zf: zipfile.ZipFile) -> tuple[str, str]:
    """Retorna (nome_da_aba, caminho_xml_da_primeira_planilha)."""
    ns = {"a": NS_MAIN, "r": NS_REL_DOC, "p": NS_REL_PKG}

    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets = workbook.find("a:sheets", ns)
    if sheets is None or len(sheets) == 0:
        raise ValueError("O arquivo XLSX não possui planilhas.")

    primeira = sheets[0]
    nome_aba = primeira.attrib["name"]
    rid = primeira.attrib[f"{{{NS_REL_DOC}}}id"]

    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    alvo = None
    for rel in rels:
        if rel.attrib.get("Id") == rid:
            alvo = rel.attrib.get("Target")
            break

    if not alvo:
        raise ValueError("Não foi possível localizar o XML da primeira planilha.")

    if alvo.startswith("/"):
        caminho_xml = alvo.lstrip("/")
    elif alvo.startswith("xl/"):
        caminho_xml = alvo
    else:
        caminho_xml = "xl/" + alvo

    return nome_aba, caminho_xml


def estilo_celula(sheet_xml: str, referencia: str, padrao: str) -> str:
    padrao_regex = rf'<c(?=[^>]*\br="{re.escape(referencia)}")[^>]*>'
    encontrado = re.search(padrao_regex, sheet_xml)
    if not encontrado:
        return padrao
    estilo = re.search(r'\bs="([^"]+)"', encontrado.group(0))
    return estilo.group(1) if estilo else padrao


def celula_texto(ref: str, estilo: str, valor: str) -> str:
    texto = escape(str(valor))
    return (
        f'<c r="{ref}" s="{estilo}" t="inlineStr">'
        f'<is><t xml:space="preserve">{texto}</t></is></c>'
    )


def celula_vazia(ref: str, estilo: str) -> str:
    return f'<c r="{ref}" s="{estilo}"/>'


def celula_numero(ref: str, estilo: str, valor: int) -> str:
    return f'<c r="{ref}" s="{estilo}"><v>{valor}</v></c>'


def substituir_celula_por_texto(
    sheet_xml: str,
    referencia: str,
    texto: str,
    estilo_padrao: str = "1",
) -> str:
    """Troca uma célula existente por uma string inline, preservando o estilo."""
    estilo = estilo_celula(sheet_xml, referencia, estilo_padrao)
    nova = celula_texto(referencia, estilo, texto)
    regex = rf'<c(?=[^>]*\br="{re.escape(referencia)}")[^>]*(?:/>|>.*?</c>)'
    resultado, quantidade = re.subn(regex, nova, sheet_xml, count=1, flags=re.DOTALL)
    if quantidade != 1:
        raise ValueError(f"Célula {referencia} não localizada no arquivo.")
    return resultado


# -----------------------------------------------------------------------------
# ETAPA 1: ATUALIZAR TÍTULOS DOS XLSX ANTIGOS
# -----------------------------------------------------------------------------
def atualizar_titulos_xlsx(origem: Path, destino: Path) -> None:
    with zipfile.ZipFile(origem, "r") as zf:
        _, caminho_planilha = obter_primeira_planilha(zf)
        sheet_xml = zf.read(caminho_planilha).decode("utf-8")

    sheet_xml = substituir_celula_por_texto(sheet_xml, "A1", TITULO_1)
    sheet_xml = substituir_celula_por_texto(sheet_xml, "A2", TITULO_2)
    sheet_xml = substituir_celula_por_texto(sheet_xml, "A3", TITULO_3)

    copiar_zip_com_alteracoes(
        origem,
        destino,
        {caminho_planilha: sheet_xml.encode("utf-8")},
    )


# -----------------------------------------------------------------------------
# LEITURA DO CSV
# -----------------------------------------------------------------------------
def detectar_encoding_csv(caminho: Path) -> str:
    amostra = caminho.read_bytes()[:100_000]
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            amostra.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"


def normalizar_cabecalho(texto: str) -> str:
    return str(texto).strip().strip('"').upper()


def localizar_coluna(cabecalhos: Iterable[str], aliases: tuple[str, ...]) -> str:
    mapa = {normalizar_cabecalho(c): c for c in cabecalhos}
    for alias in aliases:
        achado = mapa.get(normalizar_cabecalho(alias))
        if achado is not None:
            return achado
    raise ValueError(
        "Coluna não encontrada. Esperado um destes nomes: " + ", ".join(aliases)
    )


def converter_inteiro(valor: object) -> int:
    texto = str(valor).strip()
    if not texto:
        return 0

    # Aceita números inteiros simples e também valores com separador de milhar.
    texto = texto.replace(" ", "")
    if re.fullmatch(r"-?\d+", texto):
        return int(texto)

    texto_br = texto.replace(".", "").replace(",", ".")
    numero = float(texto_br)
    if not numero.is_integer():
        raise ValueError(f"Quantidade não inteira encontrada: {valor!r}")
    return int(numero)


def ler_csv(caminho: Path) -> list[tuple[str, str, str, int]]:
    encoding = detectar_encoding_csv(caminho)

    with caminho.open("r", encoding=encoding, newline="") as arquivo:
        primeira_linha = arquivo.readline()
        arquivo.seek(0)
        delimitador = ";" if primeira_linha.count(";") >= primeira_linha.count(",") else ","

        leitor = csv.DictReader(arquivo, delimiter=delimitador)
        if not leitor.fieldnames:
            raise ValueError(f"CSV sem cabeçalho: {caminho.name}")

        col_uf = localizar_coluna(leitor.fieldnames, ("UF",))
        col_cid = localizar_coluna(leitor.fieldnames, ("CID_AJUSTADO", "CID"))
        col_desc = localizar_coluna(
            leitor.fieldnames,
            ("DS_DESCRICAO_AJUSTADA", "DESCRICAO", "DESCRIÇÃO"),
        )
        col_qtd = localizar_coluna(
            leitor.fieldnames,
            ("BPC_PCD_CID", "QUANTIDADE", "QTD"),
        )

        dados: list[tuple[str, str, str, int]] = []
        for numero_linha, linha in enumerate(leitor, start=2):
            try:
                uf = str(linha.get(col_uf, "")).strip()
                cid = str(linha.get(col_cid, "")).strip()
                descricao = str(linha.get(col_desc, "")).strip()
                quantidade = converter_inteiro(linha.get(col_qtd, 0))
            except Exception as erro:
                raise ValueError(
                    f"Erro no CSV {caminho.name}, linha {numero_linha}: {erro}"
                ) from erro

            # Ignora somente linhas completamente vazias.
            if not uf and not cid and not descricao and quantidade == 0:
                continue

            dados.append((uf, cid, descricao, quantidade))

    if not dados:
        raise ValueError(f"Nenhum dado encontrado em {caminho.name}")

    return dados


# -----------------------------------------------------------------------------
# ETAPA 2: GERAR XLSX FORMATADO A PARTIR DO CSV
# -----------------------------------------------------------------------------
def montar_linhas_planilha(
    dados: list[tuple[str, str, str, int]],
    ref: int,
    estilos: dict[str, str],
) -> tuple[str, int, int]:
    primeira_linha_dados = 8
    ultima_linha_dados = primeira_linha_dados + len(dados) - 1
    linha_fonte = ultima_linha_dados + 1
    linha_nota = ultima_linha_dados + 2
    total = sum(qtd for _, _, _, qtd in dados)

    saida = io.StringIO()

    # Títulos (linhas 1 a 5), mantendo as células mescladas do modelo.
    titulos = [TITULO_1, TITULO_2, TITULO_3, titulo_periodo(ref), TITULO_5]
    for numero, texto in enumerate(titulos, start=1):
        saida.write(f'<row r="{numero}" spans="1:4" x14ac:dyDescent="0.25">')
        saida.write(celula_texto(f"A{numero}", estilos[f"A{numero}"], texto))
        for coluna in "BCD":
            saida.write(celula_vazia(f"{coluna}{numero}", estilos[f"{coluna}{numero}"]))
        saida.write("</row>")

    # Cabeçalho da tabela.
    saida.write('<row r="6" spans="1:4" x14ac:dyDescent="0.25">')
    saida.write(celula_texto("A6", estilos["A6"], "UF"))
    saida.write(celula_texto("B6", estilos["B6"], "CID"))
    saida.write(celula_texto("C6", estilos["C6"], "DESCRICAO"))
    saida.write(celula_texto("D6", estilos["D6"], "QUANTIDADE"))
    saida.write("</row>")

    # Linha de total.
    saida.write('<row r="7" spans="1:4" x14ac:dyDescent="0.25">')
    saida.write(celula_texto("A7", estilos["A7"], "TOTAL"))
    saida.write(celula_vazia("B7", estilos["B7"]))
    saida.write(celula_vazia("C7", estilos["C7"]))
    saida.write(
        f'<c r="D7" s="{estilos["D7"]}">'
        f'<f>SUM(D8:D{ultima_linha_dados})</f><v>{total}</v></c>'
    )
    saida.write("</row>")

    # Dados do CSV.
    for numero_linha, (uf, cid, descricao, quantidade) in enumerate(
        dados, start=primeira_linha_dados
    ):
        saida.write(
            f'<row r="{numero_linha}" spans="1:4" x14ac:dyDescent="0.25">'
        )
        saida.write(celula_texto(f"A{numero_linha}", estilos["A8"], uf))
        saida.write(celula_texto(f"B{numero_linha}", estilos["B8"], cid))
        saida.write(
            celula_texto(f"C{numero_linha}", estilos["C8"], descricao)
        )
        saida.write(
            celula_numero(f"D{numero_linha}", estilos["D8"], quantidade)
        )
        saida.write("</row>")

    # Fonte e nota sempre ficam logo abaixo da última linha de dados.
    saida.write(
        f'<row r="{linha_fonte}" spans="1:4" x14ac:dyDescent="0.25">'
        + celula_texto(f"A{linha_fonte}", estilos["RODAPE"], FONTE)
        + "</row>"
    )
    saida.write(
        f'<row r="{linha_nota}" spans="1:4" x14ac:dyDescent="0.25">'
        + celula_texto(f"A{linha_nota}", estilos["RODAPE"], NOTA)
        + "</row>"
    )

    return saida.getvalue(), total, linha_nota


def alterar_nome_primeira_aba(workbook_xml: str, novo_nome: str) -> str:
    novo_nome_xml = escape(novo_nome[:31])
    regex = r'(<sheet\b[^>]*\bname=")[^"]*(")'
    resultado, quantidade = re.subn(
        regex,
        rf"\g<1>{novo_nome_xml}\g<2>",
        workbook_xml,
        count=1,
    )
    if quantidade != 1:
        raise ValueError("Não foi possível alterar o nome da aba no modelo.")
    return resultado


def gerar_xlsx_do_csv(
    csv_origem: Path,
    modelo_xlsx: Path,
    destino_xlsx: Path,
    ref: int,
) -> tuple[int, int]:
    dados = ler_csv(csv_origem)

    with zipfile.ZipFile(modelo_xlsx, "r") as zf:
        _, caminho_planilha = obter_primeira_planilha(zf)
        sheet_xml = zf.read(caminho_planilha).decode("utf-8")
        workbook_xml = zf.read("xl/workbook.xml").decode("utf-8")

    # Lê os IDs de estilo diretamente do modelo 202506.
    referencias_estilo = [
        *(f"{col}{linha}" for linha in range(1, 8) for col in "ABCD"),
        "A8",
        "B8",
        "C8",
        "D8",
    ]
    estilos = {
        ref_celula: estilo_celula(sheet_xml, ref_celula, "0")
        for ref_celula in referencias_estilo
    }

    dimensao = re.search(r'<dimension\s+ref="A1:D(\d+)"\s*/>', sheet_xml)
    ultima_linha_modelo = int(dimensao.group(1)) if dimensao else 84022
    estilos["RODAPE"] = estilo_celula(
        sheet_xml, f"A{ultima_linha_modelo - 1}", "7"
    )

    novas_linhas, total, ultima_linha_nova = montar_linhas_planilha(
        dados, ref, estilos
    )

    inicio = sheet_xml.find("<sheetData>")
    fim = sheet_xml.find("</sheetData>")
    if inicio < 0 or fim < 0:
        raise ValueError("O XML do modelo não possui a seção sheetData.")
    inicio_conteudo = inicio + len("<sheetData>")

    sheet_novo = (
        sheet_xml[:inicio_conteudo]
        + novas_linhas
        + sheet_xml[fim:]
    )
    sheet_novo, quantidade_dim = re.subn(
        r'<dimension\s+ref="[^"]+"\s*/>',
        f'<dimension ref="A1:D{ultima_linha_nova}"/>',
        sheet_novo,
        count=1,
    )
    if quantidade_dim != 1:
        raise ValueError("Não foi possível atualizar a dimensão da planilha.")

    nome_aba = f"BPC_CID_{ref}"
    workbook_novo = alterar_nome_primeira_aba(workbook_xml, nome_aba)

    # Solicita recálculo ao abrir, mantendo também o valor total já gravado em D7.
    if "<calcPr" in workbook_novo:
        workbook_novo = re.sub(
            r'<calcPr\b([^>]*)/?>',
            lambda m: _atualizar_calcpr(m.group(0)),
            workbook_novo,
            count=1,
        )

    copiar_zip_com_alteracoes(
        modelo_xlsx,
        destino_xlsx,
        {
            caminho_planilha: sheet_novo.encode("utf-8"),
            "xl/workbook.xml": workbook_novo.encode("utf-8"),
        },
    )

    return len(dados), total


def _atualizar_calcpr(tag: str) -> str:
    """Acrescenta opções de recálculo sem destruir outros atributos de calcPr."""
    tag = re.sub(r'\s*/>$', ">", tag)
    tag = re.sub(r'>$','', tag)
    for atributo, valor in (
        ("calcMode", "auto"),
        ("fullCalcOnLoad", "1"),
        ("forceFullCalc", "1"),
    ):
        if re.search(rf'\b{atributo}="[^"]*"', tag):
            tag = re.sub(rf'\b{atributo}="[^"]*"', f'{atributo}="{valor}"', tag)
        else:
            tag += f' {atributo}="{valor}"'
    return tag + "/>"


# -----------------------------------------------------------------------------
# PROCESSAMENTO EM LOTE
# -----------------------------------------------------------------------------
def listar_arquivos(
    pasta_entrada: Path,
    pasta_saida: Path,
    extensao: str,
) -> list[Path]:
    arquivos = []
    for caminho in pasta_entrada.rglob(f"*{extensao}"):
        if caminho_dentro_de(caminho, pasta_saida):
            continue
        if caminho.name.startswith("~$"):
            continue
        arquivos.append(caminho)
    return sorted(arquivos)


def localizar_modelo(modelo: Path) -> Path:
    """
    Localiza o arquivo modelo.

    Primeiro tenta o caminho informado. Caso ele não exista, procura arquivos
    como BPC_CID_202506.xlsx ou BPC_CID_202506(1).xlsx na mesma pasta.
    """
    if modelo.is_file():
        return modelo

    pasta = modelo.parent
    candidatos = sorted(
        caminho
        for caminho in pasta.glob("BPC_CID_202506*.xlsx")
        if not caminho.name.startswith("~$")
    )

    if len(candidatos) == 1:
        print(f"[AVISO] Modelo localizado automaticamente: {candidatos[0]}")
        return candidatos[0]

    if len(candidatos) > 1:
        nomes = "\n - ".join(str(c) for c in candidatos)
        raise FileNotFoundError(
            "O modelo informado não existe e foram encontrados vários "
            f"candidatos:\n - {nomes}\n"
            "Informe o correto usando --modelo."
        )

    raise FileNotFoundError(
        f"Arquivo modelo não encontrado: {modelo}\n"
        f"Também não foi encontrado BPC_CID_202506*.xlsx em: {pasta}"
    )


def processar(
    pasta_entrada: Path,
    modelo: Path,
    pasta_saida: Path,
    sobrescrever: bool,
) -> None:
    if not pasta_entrada.exists():
        raise FileNotFoundError(
            f"Pasta das extrações não encontrada: {pasta_entrada}"
        )

    modelo = localizar_modelo(modelo)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    arquivos_csv = []
    for arquivo in listar_arquivos(pasta_entrada, pasta_saida, ".csv"):
        ref = extrair_referencia(arquivo.name)
        if ref is None:
            continue
        if REF_INICIAL_NOVOS <= ref <= REF_FINAL_NOVOS:
            arquivos_csv.append((ref, arquivo))

    arquivos_csv.sort(key=lambda item: (item[0], str(item[1])))

    if not arquivos_csv:
        raise FileNotFoundError(
            "Nenhum CSV do período 202506 a 202607 foi encontrado em:\n"
            f"{pasta_entrada}"
        )

    print("=" * 80)
    print("FORMATAÇÃO DOS ARQUIVOS BPC POR UF E CID")
    print("=" * 80)
    print(f"Entrada : {pasta_entrada}")
    print(f"Modelo  : {modelo}")
    print(f"Saída   : {pasta_saida}")
    print(f"Período : {REF_INICIAL_NOVOS} a {REF_FINAL_NOVOS}")
    print(f"CSVs localizados: {len(arquivos_csv)}")
    print("=" * 80)

    gerados = 0
    ignorados = 0
    erros: list[str] = []

    for posicao, (ref, arquivo_csv) in enumerate(arquivos_csv, start=1):
        destino = pasta_saida / f"BPC_CID_{ref}.xlsx"

        if destino.exists() and not sobrescrever:
            ignorados += 1
            print(
                f"[{posicao}/{len(arquivos_csv)}] [IGNORADO] "
                f"{destino.name} já existe."
            )
            continue

        try:
            quantidade_linhas, total = gerar_xlsx_do_csv(
                arquivo_csv,
                modelo,
                destino,
                ref,
            )
            gerados += 1
            print(
                f"[{posicao}/{len(arquivos_csv)}] [OK] "
                f"{arquivo_csv.name} -> {destino.name} | "
                f"linhas={quantidade_linhas:,} | total={total:,}"
            )
        except Exception as erro:
            mensagem = f"{arquivo_csv}: {erro}"
            erros.append(mensagem)
            print(
                f"[{posicao}/{len(arquivos_csv)}] [ERRO] {mensagem}"
            )

    print("\n" + "=" * 80)
    print(f"XLSX gerados: {gerados}")
    print(f"Arquivos já existentes e ignorados: {ignorados}")
    print(f"Erros: {len(erros)}")
    print(f"Pasta final: {pasta_saida}")

    if erros:
        print("\nDetalhes dos erros:")
        for mensagem in erros:
            print(" -", mensagem)
        raise RuntimeError("O processamento terminou com erro(s).")


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Transforma os CSVs extraídos de 202506 a 202607 em arquivos "
            "XLSX com a mesma formatação do modelo BPC_CID_202506."
        )
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        default=PASTA_ENTRADA_PADRAO,
        help=(
            "Pasta que contém as novas extrações CSV. "
            f"Padrão: {PASTA_ENTRADA_PADRAO}"
        ),
    )
    parser.add_argument(
        "--modelo",
        type=Path,
        default=MODELO_PADRAO,
        help=(
            "Arquivo BPC_CID_202506.xlsx usado como modelo. "
            f"Padrão: {MODELO_PADRAO}"
        ),
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=PASTA_SAIDA_PADRAO,
        help=(
            "Pasta dos XLSX formatados. "
            f"Padrão: {PASTA_SAIDA_PADRAO}"
        ),
    )
    parser.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Refaz os XLSX que já existirem na pasta de saída.",
    )
    return parser.parse_args()


def main() -> int:
    args = argumentos()

    entrada = args.entrada.expanduser()
    modelo = args.modelo.expanduser()
    saida = args.saida.expanduser()

    try:
        processar(
            pasta_entrada=entrada,
            modelo=modelo,
            pasta_saida=saida,
            sobrescrever=args.sobrescrever,
        )
        return 0
    except KeyboardInterrupt:
        print("\nProcessamento interrompido pelo usuário.", file=sys.stderr)
        return 130
    except Exception as erro:
        print(f"\nFALHA: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())