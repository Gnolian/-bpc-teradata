import teradatasql
from src.config import TD_HOST, TD_USER, TD_PASSWORD, TD_LOGMECH


def get_connection():
    if not TD_HOST or not TD_USER or not TD_PASSWORD:
        raise ValueError(
            "Credenciais do Teradata não configuradas. "
            "Preencha TD_HOST, TD_USER e TD_PASSWORD no arquivo .env."
        )

    conn_args = {
        "host": TD_HOST,
        "user": TD_USER,
        "password": TD_PASSWORD,
    }

    if TD_LOGMECH:
        conn_args["logmech"] = TD_LOGMECH

    return teradatasql.connect(**conn_args)