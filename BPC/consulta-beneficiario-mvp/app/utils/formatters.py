import pandas as pd


def normalizar_cpf(valor) -> str:
    valor = "" if valor is None else str(valor).strip()
    if valor.endswith(".0"):
        valor = valor[:-2]
    valor = "".join(ch for ch in valor if ch.isdigit())
    return valor.zfill(11) if valor else ""


def formatar_cpf(cpf: str) -> str:
    cpf = normalizar_cpf(cpf)
    if len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def normalizar_nb(valor) -> str:
    valor = "" if valor is None else str(valor).strip()
    if valor.endswith(".0"):
        valor = valor[:-2]
    valor = "".join(ch for ch in valor if ch.isdigit())
    return valor.zfill(10) if valor else ""


def formatar_nb_exibicao(valor):
    if valor in (None, "", "nan"):
        return "Não possui"
    return normalizar_nb(valor)


def normalizar_codigo_familiar(valor) -> str:
    valor = "" if valor is None else str(valor).strip()

    if valor.lower() in ("", "nan", "none"):
        return ""

    if valor.endswith(".0"):
        valor = valor[:-2]

    valor = "".join(ch for ch in valor if ch.isdigit())
    return valor


def formatar_codigo_familiar_exibicao(valor) -> str:
    codigo = normalizar_codigo_familiar(valor)
    return codigo if codigo else "Não informado"


def formatar_competencia(comp):
    comp = str(comp).strip()
    if comp.endswith(".0"):
        comp = comp[:-2]
    if len(comp) == 6 and comp.isdigit():
        return f"{comp[4:6]}/{comp[:4]}"
    return comp


def formatar_data_br(valor):
    if valor in [None, "", "nan", "NaT"]:
        return ""
    dt = pd.to_datetime(valor, errors="coerce")
    if pd.isna(dt):
        return ""
    return dt.strftime("%d/%m/%Y")


def descricao_especie(cs_especie):
    if cs_especie is None:
        return "Não informado"

    valor = str(cs_especie).strip()

    if valor.endswith(".0"):
        valor = valor[:-2]

    mapa = {
        "87": "BPC Pessoa com Deficiência",
        "88": "BPC Idoso",
        "18": "Auxílio-Inclusão",
        "11": "RMV por Invalidez",
        "12": "RMV por Idade",
        "30": "RMV por Invalidez",
        "40": "RMV por Idade",
        "60": "Benefício relacionado à Síndrome Congênita do Zika Vírus",
    }

    return mapa.get(valor, f"Espécie {valor}" if valor else "Não informado")


def valor_legivel(valor, vazio="Não informado"):
    if pd.isna(valor):
        return vazio
    valor = str(valor).strip()
    return valor if valor else vazio


def formatar_numero(valor):
    try:
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        return str(valor)


def formatar_numero_inteiro(valor, vazio="Não informado"):
    if valor is None:
        return vazio

    texto = str(valor).strip()
    if texto.lower() in ("", "nan", "none"):
        return vazio

    if texto.endswith(".0"):
        texto = texto[:-2]

    digitos = "".join(ch for ch in texto if ch.isdigit())
    return digitos if digitos else vazio
