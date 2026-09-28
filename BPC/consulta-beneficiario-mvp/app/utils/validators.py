def _somente_digitos(valor: str) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def validar_cpf_input(valor: str):
    if not valor:
        return False, "Informe um CPF para realizar a busca."

    digitos = _somente_digitos(valor)

    if len(digitos) != 11:
        return False, "O CPF deve conter exatamente 11 dígitos."

    return True, ""


def validar_nb_input(valor: str):
    if not valor:
        return False, "Informe um Número do Benefício para realizar a busca."

    digitos = _somente_digitos(valor)

    if len(digitos) != 10:
        return False, "O Número do Benefício deve conter exatamente 10 dígitos."

    return True, ""


def validar_codigo_familiar_input(valor: str):
    digitos = _somente_digitos(valor)

    if not digitos:
        return False, "Informe o código familiar."

    if len(digitos) < 4:
        return False, "O código familiar informado parece inválido."

    return True, ""
