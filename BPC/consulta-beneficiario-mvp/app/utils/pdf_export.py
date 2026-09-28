from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from app.utils.formatters import (
    descricao_especie,
    formatar_codigo_familiar_exibicao,
    formatar_competencia,
    formatar_cpf,
    formatar_data_br,
    formatar_numero_inteiro,
    normalizar_nb,
    valor_legivel,
)


class PDFExportError(Exception):
    pass


def _importar_reportlab():
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise PDFExportError(
            "A biblioteca reportlab não está instalada. Execute: pip install -r requirements.txt"
        ) from exc

    return {
        "colors": colors,
        "TA_CENTER": TA_CENTER,
        "TA_RIGHT": TA_RIGHT,
        "A4": A4,
        "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet,
        "cm": cm,
        "Image": Image,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
    }


def _texto(valor, vazio="Não informado"):
    return valor_legivel(valor, vazio=vazio)


def _paragrafo(texto, estilo, Paragraph):
    texto = "" if texto is None else str(texto)
    return Paragraph(escape(texto).replace("\n", "<br/>"), estilo)


def _tipo_registro_legivel(valor):
    mapa = {
        "BENEFICIARIO_CADUNICO": "Beneficiário no CadÚnico",
        "MEMBRO_FAMILIAR": "Membro familiar",
        "NAO_CADASTRADO": "Beneficiário não localizado no CadÚnico",
    }
    return mapa.get(str(valor or "").strip(), _texto(valor))


def _bool_legivel(valor):
    if str(valor) == "1":
        return "Sim"
    if str(valor) == "0":
        return "Não"
    return "Não informado"


def _formatar_nb(valor):
    texto = "" if valor is None else str(valor).strip()
    if texto.lower() in ("", "nan", "none"):
        return "Não possui"
    return normalizar_nb(valor)


def _nome_registro(registro):
    return _texto(registro.get("NOM_PESSOA") or registro.get("NM_TIT_BENEF_T"))


def _cpf_registro(registro):
    return registro.get("NUM_CPF_PESSOA") or registro.get("NU_CPF_T") or ""


def _nis_registro(registro):
    return registro.get("NUM_NIS_PESSOA_ATUAL") or registro.get("NU_NIS_T")


def _data_nascimento_registro(registro):
    return registro.get("DTA_NASC_PESSOA") or registro.get("DT_NASC_T")


def _idade_registro(registro):
    idade_pessoa = registro.get("IDADE_PESSOA")
    if idade_pessoa not in (None, "", "nan"):
        return idade_pessoa
    return registro.get("IDADE_T")


def _nome_mae_registro(registro):
    return registro.get("NOM_COMPLETO_MAE_PESSOA") or registro.get("NM_MAE_T") or ""


def _parentesco_registro(registro):
    return registro.get("DESC_PARENTESCO") or ""


def _campo_data(valor):
    return formatar_data_br(valor) or "Não informado"


def _competencia(valor):
    texto = "" if valor is None else str(valor).strip()
    if texto.lower() in ("", "nan", "none"):
        return "Não informado"
    return formatar_competencia(texto)


def campos_detalhamento_pessoa(registro):
    cs_especie = registro.get("CS_ESPECIE")
    especie = descricao_especie(cs_especie) if _texto(cs_especie, vazio="") else "Não se aplica"

    return {
        "Dados da pessoa": [
            ("Tipo de registro", _tipo_registro_legivel(registro.get("TIPO_REGISTRO"))),
            ("Nome", _nome_registro(registro)),
            ("CPF", formatar_cpf(_cpf_registro(registro))),
            ("Data de nascimento", _campo_data(_data_nascimento_registro(registro))),
            ("Idade", _texto(_idade_registro(registro))),
            ("Nome da mãe", _texto(_nome_mae_registro(registro))),
            ("Gênero", _texto(registro.get("GENERO"))),
            ("Raça/Cor", _texto(registro.get("RACA_COR"))),
            ("Número de Identificação Social", formatar_numero_inteiro(_nis_registro(registro))),
            ("Chave natural da pessoa", formatar_numero_inteiro(registro.get("CO_CHV_NATURAL_PESSOA"))),
            ("Código familiar", formatar_codigo_familiar_exibicao(registro.get("CO_FAMILIAR_FAM"))),
            ("Parentesco com o responsável familiar", _texto(_parentesco_registro(registro), vazio="Não se aplica")),
            ("Situação no CadÚnico", _texto(registro.get("SITUACAO_CAD_UNICO"))),
            ("Atualização do membro", _campo_data(registro.get("DTA_ATUAL_MEMB"))),
        ],
        "Dados do benefício": [
            ("Número do benefício", _formatar_nb(registro.get("NU_NB"))),
            ("Tipo do registro", _tipo_registro_legivel(registro.get("TIPO_REGISTRO"))),
            ("Espécie", especie),
            ("Código Internacional de Doenças (CID)", _texto(registro.get("CID"), vazio="Não se aplica")),
            ("Descrição do CID", _texto(registro.get("DESCRICAO_CID"), vazio="Não se aplica")),
            ("Tipo de despacho", _texto(registro.get("TIPO_DESPACHO"), vazio="Não se aplica")),
            ("Data do despacho", _campo_data(registro.get("DT_DESPACHO"))),
            ("Data de Entrada do Requerimento", _campo_data(registro.get("DT_ENTRADA_REQUERIMENTO"))),
            ("Data de Início do Benefício", _campo_data(registro.get("DT_INICIO_BENEFICIO"))),
            ("Participação em campanha", _texto(registro.get("PARTICIPACAO_CAMPANHA"))),
            ("Indicador CadÚnico", _bool_legivel(registro.get("FLAG_CADUNICO"))),
            ("Competência", _competencia(registro.get("NU_MES_REF", ""))),
        ],
    }


def nome_arquivo_pdf_detalhamento(registro):
    cpf = "".join(ch for ch in str(_cpf_registro(registro)) if ch.isdigit()) or "sem-cpf"
    beneficio = "".join(ch for ch in str(registro.get("NU_NB") or "") if ch.isdigit()) or "sem-beneficio"
    competencia = "".join(ch for ch in str(registro.get("NU_MES_REF") or "") if ch.isdigit()) or "sem-competencia"
    return f"SCB_detalhamento_{cpf}_{beneficio}_{competencia}.pdf"


def _logo_ou_texto(caminho, texto, largura, altura, estilo, Image, Paragraph):
    if caminho.exists():
        img = Image(str(caminho))
        img._restrictSize(largura, altura)
        return img
    return _paragrafo(texto, estilo, Paragraph)


def gerar_pdf_detalhamento_pessoa(registro, mensagem_resultado=None, usuario=None):
    rl = _importar_reportlab()
    colors = rl["colors"]
    Paragraph = rl["Paragraph"]
    SimpleDocTemplate = rl["SimpleDocTemplate"]
    Spacer = rl["Spacer"]
    Table = rl["Table"]
    TableStyle = rl["TableStyle"]
    ParagraphStyle = rl["ParagraphStyle"]
    getSampleStyleSheet = rl["getSampleStyleSheet"]
    Image = rl["Image"]
    cm = rl["cm"]
    A4 = rl["A4"]
    TA_CENTER = rl["TA_CENTER"]
    TA_RIGHT = rl["TA_RIGHT"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.6 * cm,
        leftMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.3 * cm,
        title="Sistema de Consulta de Beneficiários - SCB",
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "SCBNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827"),
    )
    label = ParagraphStyle(
        "SCBLabel",
        parent=normal,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1f2937"),
    )
    titulo = ParagraphStyle(
        "SCBTitulo",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    subtitulo = ParagraphStyle(
        "SCBSubtitulo",
        parent=normal,
        fontSize=8,
        leading=10,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#475569"),
    )
    orgao = ParagraphStyle(
        "SCBOrgao",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )
    secao = ParagraphStyle(
        "SCBSecao",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=10,
        spaceAfter=6,
    )

    base_assets = Path(__file__).resolve().parents[1] / "assets"
    logo_governo = base_assets / "logo_governo_federal.png"
    logo_projeto = base_assets / "logo_projeto.png"

    story = []
    header = Table(
        [
            [
                _logo_ou_texto(
                    logo_governo,
                    "GOVERNO FEDERAL\nMinistério do Desenvolvimento e Assistência Social, Família e Combate à Fome",
                    6.0 * cm,
                    1.4 * cm,
                    orgao,
                    Image,
                    Paragraph,
                ),
                _logo_ou_texto(
                    logo_projeto,
                    "Portfolio\nProjeto demonstrativo",
                    5.0 * cm,
                    1.4 * cm,
                    subtitulo,
                    Image,
                    Paragraph,
                ),
            ]
        ],
        colWidths=[10.2 * cm, 6.0 * cm],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#d1d5db")),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 0.35 * cm))
    story.append(_paragrafo("Sistema de Consulta de Beneficiários - SCB", titulo, Paragraph))
    story.append(_paragrafo("Documento de detalhamento de pessoa/benefício", normal, Paragraph))
    story.append(Spacer(1, 0.25 * cm))

    if mensagem_resultado:
        box = Table(
            [[_paragrafo(mensagem_resultado, normal, Paragraph)]],
            colWidths=[16.2 * cm],
        )
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef6ff")),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#93c5fd")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(box)
        story.append(Spacer(1, 0.25 * cm))

    for nome_secao, campos in campos_detalhamento_pessoa(registro).items():
        story.append(_paragrafo(nome_secao, secao, Paragraph))
        dados = [
            [_paragrafo(rotulo, label, Paragraph), _paragrafo(valor, normal, Paragraph)]
            for rotulo, valor in campos
        ]
        tabela = Table(dados, colWidths=[6.0 * cm, 10.2 * cm])
        tabela.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(tabela)

    emitido_em = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    usuario_txt = ""
    if usuario:
        usuario_txt = usuario.get("nome_completo") or usuario.get("username") or ""
    rodape = (
        f"Documento gerado em {emitido_em}"
        + (f" por {usuario_txt}." if usuario_txt else ".")
        + " Documento demonstrativo do portfolio."
    )
    story.append(Spacer(1, 0.35 * cm))
    story.append(_paragrafo(rodape, subtitulo, Paragraph))

    doc.build(story)
    return buffer.getvalue()
