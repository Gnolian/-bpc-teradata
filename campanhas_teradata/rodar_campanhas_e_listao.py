import os
import re
import shutil
import logging
from datetime import datetime
from pathlib import Path

import teradatasql
from dotenv import load_dotenv


# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================

ARQUIVO_CAMPANHAS = "campanhas.sql"
ARQUIVO_MERGES = "atualizar_listao.sql"

RODAR_CAMPANHAS = True
RODAR_ATUALIZACAO_LISTAO = True

# Se True, apenas gera os SQLs finais e NÃO executa no Teradata.
DRY_RUN = True

# Se True, apaga as tabelas das campanhas do dia antes de criar novamente.
DROP_EXISTING = False

PASTA_LOGS = "logs"
PASTA_SQL_GERADO = "sql_gerado"

# Pasta da rede onde serão criadas as evidências diárias.
# Use string raw r"..." para o Windows não interpretar as barras.
PASTA_DEMANDAS_REDE = "outputs/evidencias"

# Nome fixo do assunto da pasta diária.
ASSUNTO_PASTA_DEMANDA = "Atualizacao_campanhas_listao"


# Variável global para guardar o caminho exato do log do dia.
CAMINHO_LOG_ATUAL = None


# ============================================================
# LOG, DATA E PASTA DE DEMANDA
# ============================================================

def obter_data_referencia() -> str:
    """
    Usa a data de hoje no formato AAAAMMDD.
    Para forçar uma data:
    set DATA_REFERENCIA=20260609
    python rodar_campanhas_e_listao.py
    """
    data_env = os.getenv("DATA_REFERENCIA")

    if data_env:
        if not re.fullmatch(r"\d{8}", data_env):
            raise ValueError("DATA_REFERENCIA deve estar no formato AAAAMMDD. Exemplo: 20260609")
        return data_env

    return datetime.now().strftime("%Y%m%d")


def formatar_data_pasta(data_ref: str) -> str:
    """
    Converte 20260609 para 2026_06_09.
    """
    return f"{data_ref[0:4]}_{data_ref[4:6]}_{data_ref[6:8]}"


def obter_nome_pasta_demanda(data_ref: str) -> str:
    """
    Exemplo:
    2026_06_09_Atualizacao_campanhas_listao_20260609
    """
    data_formatada = formatar_data_pasta(data_ref)
    return f"{data_formatada}_{ASSUNTO_PASTA_DEMANDA}_{data_ref}"


def obter_caminho_pasta_demanda(data_ref: str) -> Path:
    return Path(PASTA_DEMANDAS_REDE) / obter_nome_pasta_demanda(data_ref)


def configurar_logs(data_ref: str) -> Path:
    """
    Configura log em arquivo local e também no console.
    Retorna o caminho do arquivo de log local.
    """
    global CAMINHO_LOG_ATUAL

    Path(PASTA_LOGS).mkdir(exist_ok=True)

    caminho_log = Path(PASTA_LOGS) / f"rotina_campanhas_e_listao_{data_ref}.log"
    CAMINHO_LOG_ATUAL = caminho_log

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Limpa handlers anteriores para evitar duplicidade quando rodar em ambiente interativo.
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    file_handler = logging.FileHandler(caminho_log, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return caminho_log


# ============================================================
# CONEXÃO
# ============================================================

def conectar_teradata():
    load_dotenv()

    host = os.getenv("TD_HOST")
    user = os.getenv("TD_USER")
    password = os.getenv("TD_PASSWORD")
    logmech = os.getenv("TD_LOGMECH")

    if not host or not user or not password:
        raise ValueError("Configure TD_HOST, TD_USER e TD_PASSWORD no arquivo .env")

    parametros = {
        "host": host,
        "user": user,
        "password": password
    }

    if logmech:
        parametros["logmech"] = logmech

    return teradatasql.connect(**parametros)


# ============================================================
# UTILITÁRIOS
# ============================================================

def carregar_sql(caminho: str) -> str:
    path = Path(caminho)

    if not path.exists():
        raise FileNotFoundError(f"Arquivo SQL não encontrado: {caminho}")

    return path.read_text(encoding="utf-8")


def salvar_sql_gerado(nome: str, sql_final: str, data_ref: str) -> Path:
    Path(PASTA_SQL_GERADO).mkdir(exist_ok=True)

    caminho_saida = Path(PASTA_SQL_GERADO) / f"{nome}_{data_ref}.sql"
    caminho_saida.write_text(sql_final, encoding="utf-8")

    return caminho_saida


def limpar_comentarios_linha(sql_texto: str) -> str:
    linhas_limpas = []

    for linha in sql_texto.splitlines():
        linha_sem_comentario = re.sub(r"--.*$", "", linha).rstrip()
        if linha_sem_comentario.strip():
            linhas_limpas.append(linha_sem_comentario)

    return "\n".join(linhas_limpas)


def copiar_arquivo_se_existir(origem: Path, destino: Path) -> None:
    if origem.exists():
        shutil.copy2(origem, destino)
        logging.info(f"Arquivo copiado para pasta da demanda: {destino}")
    else:
        logging.warning(f"Arquivo não encontrado para copiar: {origem}")


def gerar_resumo_execucao(data_ref: str, pasta_demanda: Path, status: str, erro: str | None = None) -> Path:
    """
    Cria um TXT simples na pasta da demanda com o resumo da execução.
    """
    caminho_resumo = pasta_demanda / f"resumo_execucao_{data_ref}.txt"

    linhas = [
        "Resumo da execução - Atualização campanhas e listão",
        "",
        f"Data de referência: {data_ref}",
        f"Pasta da demanda: {pasta_demanda}",
        f"Status: {status}",
        "",
        "Arquivos esperados nesta pasta:",
        f"- campanhas_gerado_{data_ref}.sql",
        f"- atualizar_listao_gerado_{data_ref}.sql",
        f"- rotina_campanhas_e_listao_{data_ref}.log",
    ]

    if erro:
        linhas.extend([
            "",
            "Erro registrado:",
            erro
        ])

    caminho_resumo.write_text("\n".join(linhas), encoding="utf-8")
    return caminho_resumo


def copiar_evidencias_para_pasta_demanda(data_ref: str, status: str, erro: str | None = None) -> None:
    """
    Cria a pasta diária no W: e copia:
    - SQL das campanhas gerado;
    - SQL dos MERGEs gerado;
    - log da execução;
    - resumo da execução.
    """
    pasta_demanda = obter_caminho_pasta_demanda(data_ref)

    try:
        pasta_demanda.mkdir(parents=True, exist_ok=True)

        logging.info("=" * 80)
        logging.info(f"Pasta da demanda criada/verificada: {pasta_demanda}")

        arquivos_para_copiar = [
            Path(PASTA_SQL_GERADO) / f"campanhas_gerado_{data_ref}.sql",
            Path(PASTA_SQL_GERADO) / f"atualizar_listao_gerado_{data_ref}.sql",
        ]

        if CAMINHO_LOG_ATUAL:
            # Força flush dos handlers antes de copiar o log.
            for handler in logging.getLogger().handlers:
                handler.flush()

            arquivos_para_copiar.append(Path(CAMINHO_LOG_ATUAL))

        for arquivo in arquivos_para_copiar:
            copiar_arquivo_se_existir(arquivo, pasta_demanda / arquivo.name)

        caminho_resumo = gerar_resumo_execucao(data_ref, pasta_demanda, status, erro)
        logging.info(f"Resumo da execução salvo em: {caminho_resumo}")

        logging.info("Evidências copiadas para a pasta da demanda com sucesso.")

    except Exception as erro_copia:
        logging.error("Não foi possível copiar as evidências para a pasta da demanda.")
        logging.error(str(erro_copia))
        logging.error("A execução principal pode ter sido concluída, mas a cópia para o W: falhou.")


# ============================================================
# CAMPANHAS - CREATE TABLE
# ============================================================

def separar_comandos_create(sql_texto: str) -> list[str]:
    partes = re.split(
        r"(?=CREATE\s+MULTISET\s+TABLE\s+)",
        sql_texto,
        flags=re.IGNORECASE
    )

    comandos = []

    for parte in partes:
        parte = parte.strip()

        if not parte:
            continue

        if re.match(r"CREATE\s+MULTISET\s+TABLE\s+", parte, flags=re.IGNORECASE):
            comandos.append(parte.rstrip(";") + ";")

    return comandos


def extrair_tabela_destino_create(sql: str) -> str:
    match = re.search(
        r"CREATE\s+MULTISET\s+TABLE\s+([A-Za-z0-9_]+\.[A-Za-z0-9_]+)",
        sql,
        flags=re.IGNORECASE
    )

    if not match:
        raise ValueError("Não foi possível identificar a tabela destino do CREATE.")

    return match.group(1)


def atualizar_data_tabela_destino_create(sql: str, data_ref: str) -> tuple[str, str, str]:
    tabela_antiga = extrair_tabela_destino_create(sql)

    if re.search(r"_20\d{6}$", tabela_antiga):
        tabela_nova = re.sub(r"_20\d{6}$", f"_{data_ref}", tabela_antiga)
    else:
        tabela_nova = tabela_antiga
        logging.warning(f"Tabela destino não termina com data AAAAMMDD: {tabela_antiga}")

    sql_atualizado = sql.replace(tabela_antiga, tabela_nova, 1)

    return sql_atualizado, tabela_antiga, tabela_nova


def dropar_tabela_se_existir(cursor, tabela: str) -> None:
    try:
        cursor.execute(f"DROP TABLE {tabela};")
        logging.info(f"Tabela apagada: {tabela}")
    except Exception as erro:
        erro_texto = str(erro)

        if "3807" in erro_texto or "does not exist" in erro_texto.lower():
            logging.info(f"Tabela ainda não existia: {tabela}")
        else:
            raise


def contar_registros(cursor, tabela: str) -> int | None:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {tabela};")
        return cursor.fetchone()[0]
    except Exception as erro:
        logging.warning(f"Não foi possível contar registros da tabela {tabela}: {erro}")
        return None


def preparar_campanhas(data_ref: str) -> list[dict]:
    sql_original = carregar_sql(ARQUIVO_CAMPANHAS)
    comandos = separar_comandos_create(sql_original)

    if not comandos:
        raise ValueError("Nenhum CREATE MULTISET TABLE encontrado em campanhas.sql.")

    processados = []

    for i, comando in enumerate(comandos, start=1):
        sql_atualizado, tabela_antiga, tabela_nova = atualizar_data_tabela_destino_create(
            comando,
            data_ref
        )

        processados.append({
            "ordem": i,
            "tabela_antiga": tabela_antiga,
            "tabela_nova": tabela_nova,
            "sql": sql_atualizado
        })

    sql_final = "\n\n".join(item["sql"].rstrip(";") + ";" for item in processados)
    caminho = salvar_sql_gerado("campanhas_gerado", sql_final, data_ref)
    logging.info(f"SQL das campanhas salvo em: {caminho}")

    return processados


def executar_campanhas(cursor, campanhas: list[dict]) -> None:
    total = len(campanhas)

    for item in campanhas:
        ordem = item["ordem"]
        tabela_nova = item["tabela_nova"]
        sql = item["sql"]

        logging.info("=" * 80)
        logging.info(f"Executando campanha {ordem}/{total}")
        logging.info(f"Tabela destino: {tabela_nova}")

        if DROP_EXISTING:
            dropar_tabela_se_existir(cursor, tabela_nova)

        cursor.execute(sql)

        qtd = contar_registros(cursor, tabela_nova)

        if qtd is not None:
            logging.info(f"Campanha {ordem}/{total} concluída. Registros: {qtd:,}".replace(",", "."))
        else:
            logging.info(f"Campanha {ordem}/{total} concluída.")


# ============================================================
# LISTÃO - MERGE
# ============================================================

def atualizar_datas_bases_diarias(sql: str, data_ref: str) -> str:
    padroes = [
        r"(_BASE_DIARIA_CAD_)20\d{6}",
        r"(_BSE_DIARIA_CAD_)20\d{6}",
        r"(_CAMPANHA_A_)20\d{6}",
        r"(_CAMPANHA_B_)20\d{6}",
        r"(_CAMPANHA_)20\d{6}",
    ]

    sql_atualizado = sql

    for padrao in padroes:
        sql_atualizado = re.sub(
            padrao,
            rf"\g<1>{data_ref}",
            sql_atualizado,
            flags=re.IGNORECASE
        )

    return sql_atualizado


def separar_merges(sql_texto: str) -> list[str]:
    sql_limpo = limpar_comentarios_linha(sql_texto)

    return [
        parte.strip() + ";"
        for parte in sql_limpo.split(";")
        if parte.strip()
    ]


def extrair_tabela_origem_merge(merge_sql: str) -> str:
    match = re.search(
        r"FROM\s+(BASE_EXEMPLO_01\.[A-Za-z0-9_]+)",
        merge_sql,
        flags=re.IGNORECASE
    )

    return match.group(1) if match else "NÃO_IDENTIFICADA"


def extrair_campanha_merge(merge_sql: str) -> str:
    match = re.search(
        r"CAMPANHA\s*=\s*'([^']+)'",
        merge_sql,
        flags=re.IGNORECASE
    )

    return match.group(1) if match else "NÃO_IDENTIFICADA"


def preparar_merges(data_ref: str) -> list[str]:
    sql_original = carregar_sql(ARQUIVO_MERGES)
    sql_final = atualizar_datas_bases_diarias(sql_original, data_ref)

    caminho = salvar_sql_gerado("atualizar_listao_gerado", sql_final, data_ref)
    logging.info(f"SQL dos MERGEs salvo em: {caminho}")

    comandos = separar_merges(sql_final)

    if not comandos:
        raise ValueError("Nenhum MERGE encontrado em atualizar_listao.sql.")

    return comandos


def executar_merges(cursor, merges: list[str]) -> None:
    total = len(merges)

    for i, merge_sql in enumerate(merges, start=1):
        tabela_origem = extrair_tabela_origem_merge(merge_sql)
        campanha = extrair_campanha_merge(merge_sql)

        logging.info("=" * 80)
        logging.info(f"Executando MERGE {i}/{total}")
        logging.info(f"Campanha: {campanha}")
        logging.info(f"Tabela origem: {tabela_origem}")

        if tabela_origem != "NÃO_IDENTIFICADA":
            cursor.execute(f"SELECT COUNT(*) FROM {tabela_origem};")

        cursor.execute(merge_sql)

        logging.info(f"MERGE {i}/{total} concluído.")


# ============================================================
# MAIN
# ============================================================

def main():
    data_ref = obter_data_referencia()
    configurar_logs(data_ref)

    erro_execucao = None

    try:
        logging.info("Iniciando rotina de campanhas e atualização do listão.")
        logging.info(f"Data de referência: {data_ref}")

        campanhas = preparar_campanhas(data_ref) if RODAR_CAMPANHAS else []
        merges = preparar_merges(data_ref) if RODAR_ATUALIZACAO_LISTAO else []

        if DRY_RUN:
            logging.info("DRY_RUN=True. Os SQLs foram gerados, mas nada foi executado no Teradata.")
            copiar_evidencias_para_pasta_demanda(data_ref, status="DRY_RUN")
            return

        with conectar_teradata() as conn:
            with conn.cursor() as cursor:
                if RODAR_CAMPANHAS:
                    executar_campanhas(cursor, campanhas)

                if RODAR_ATUALIZACAO_LISTAO:
                    executar_merges(cursor, merges)

        logging.info("Rotina concluída com sucesso.")
        copiar_evidencias_para_pasta_demanda(data_ref, status="SUCESSO")

    except Exception as erro:
        erro_execucao = str(erro)
        logging.error("Rotina finalizada com erro.")
        logging.error(erro_execucao)

        # Mesmo com erro, copia o que foi gerado até o momento para a pasta da demanda.
        copiar_evidencias_para_pasta_demanda(data_ref, status="ERRO", erro=erro_execucao)

        raise


if __name__ == "__main__":
    main()
