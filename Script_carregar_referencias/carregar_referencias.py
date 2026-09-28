import os
import time
import teradatasql
from datetime import datetime
from dotenv import load_dotenv


# ============================================================
# CONFIGURAÇÕES
# ============================================================

load_dotenv()

TD_HOST = os.getenv("TD_HOST")
TD_USER = os.getenv("TD_USER")
TD_PASSWORD = os.getenv("TD_PASSWORD")
TD_LOGMECH = os.getenv("TD_LOGMECH", "LDAP")

ARQUIVO_SQL_MODELO = "consulta_modelo.sql"

TABELA_DESTINO = "BASE_EXEMPLO_01.TABELA_EXEMPLO_002"

# Como o erro parou em 202201, reinicie daqui até 202109.
REFERENCIA_INICIAL = 202605
REFERENCIA_FINAL = 202605

# Se True, apaga a referência na tabela destino antes de inserir novamente.
# Como 202201 deu rollback, pode deixar False.
# Se for refazer uma referência já carregada, coloque True.
APAGAR_ANTES_DE_INSERIR = False

# Se True, o script para no primeiro erro.
# Se False, ele pula a referência com erro e tenta continuar a próxima.
PARAR_NO_PRIMEIRO_ERRO = True


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def yyyymm_to_datetime(ref: int) -> datetime:
    return datetime.strptime(str(ref), "%Y%m")


def mes_anterior(ref: int) -> int:
    dt = yyyymm_to_datetime(ref)

    if dt.month == 1:
        return int(f"{dt.year - 1}12")

    return int(f"{dt.year}{dt.month - 1:02d}")


def mes_posterior(ref: int) -> int:
    dt = yyyymm_to_datetime(ref)

    if dt.month == 12:
        return int(f"{dt.year + 1}01")

    return int(f"{dt.year}{dt.month + 1:02d}")


def obter_ref_cadunico(ref_principal: int) -> int:
    """
    Define qual referência do CadÚnico será usada.

    Regra geral:
    - usa o mês posterior.
      Exemplo: Maciça 202507 com CadÚnico 202508.

    Exceções:
    - algumas views antigas usam CadÚnico do mesmo mês.
      Exemplo: TABELA_EXEMPLO_078.
    """

    excecoes_cadunico_mesmo_mes = {
        202201,
        202202,
    }

    if ref_principal in excecoes_cadunico_mesmo_mes:
        return ref_principal

    return mes_posterior(ref_principal)


def gerar_referencias(inicio: int, fim: int) -> list[int]:
    """
    Gera referências decrescentes no formato YYYYMM.
    Exemplo: 202201 até 202109.
    """
    refs = []
    atual = inicio

    while atual >= fim:
        refs.append(atual)
        atual = mes_anterior(atual)

    return refs


def carregar_sql_modelo(caminho: str) -> str:
    with open(caminho, "r", encoding="utf-8") as arquivo:
        return arquivo.read()


def preparar_sql(sql_modelo: str, referencia: int) -> str:
    """
    A SQL-modelo deve estar usando:
    - 202507 como referência principal
    - 202506 como referência anterior
    - 202508 como referência CadÚnico/posterior

    O script troca automaticamente:
    - 202507 pela referência processada
    - 202506 pela referência anterior
    - 202508 pela referência CadÚnico definida pela função obter_ref_cadunico()
    """

    ref_principal = referencia
    ref_anterior = mes_anterior(referencia)
    ref_cadunico = obter_ref_cadunico(referencia)

    sql = sql_modelo

    # Trocas mais específicas primeiro
    sql = sql.replace(
        "BASE_EXEMPLO_05",
        f"BASE_EXEMPLO_04{ref_cadunico}"
    )

    sql = sql.replace(
        "BASE_EXEMPLO_07.TABELA_EXEMPLO_079",
        f"BASE_EXEMPLO_07.TABELA_EXEMPLO_077{ref_principal}_CADUN_{ref_cadunico}"
    )

    # Trocas das referências numéricas
    sql = sql.replace("202506", str(ref_anterior))
    sql = sql.replace("202507", str(ref_principal))
    sql = sql.replace("202508", str(ref_cadunico))

    return sql


def dividir_comandos_sql(sql: str) -> list[str]:
    """
    Divide a SQL em comandos usando ponto e vírgula.
    """
    comandos = []

    for parte in sql.split(";"):
        comando = parte.strip()

        if comando:
            comandos.append(comando)

    return comandos


def executar_comando(cursor, comando: str, ignorar_erro: bool = False):
    try:
        cursor.execute(comando)

    except Exception as erro:
        if ignorar_erro:
            # Ignora silenciosamente erros esperados, como DROP de tabela volátil inexistente.
            return

        raise


def validar_objetos_referencia(cursor, referencia: int):
    """
    Valida se as tabelas/views necessárias para a referência existem.
    Isso evita começar a carga e quebrar no meio por objeto inexistente.
    """

    ref_cadunico = obter_ref_cadunico(referencia)

    objetos = [
        (
            "BASE_EXEMPLO_07",
            f"TABELA_EXEMPLO_077{referencia}_CADUN_{ref_cadunico}"
        ),
        (
            f"BASE_EXEMPLO_04{ref_cadunico}",
            "TABELA_EXEMPLO_072"
        ),
        (
            f"BASE_EXEMPLO_04{ref_cadunico}",
            "TABELA_EXEMPLO_071"
        ),
    ]

    objetos_inexistentes = []

    for database_name, table_name in objetos:
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM DBC.TablesV
            WHERE DatabaseName = '{database_name}'
              AND TableName = '{table_name}'
        """)

        qtd = cursor.fetchone()[0]

        if qtd == 0:
            objetos_inexistentes.append(f"{database_name}.{table_name}")

    if objetos_inexistentes:
        raise Exception(
            "Objetos não encontrados para a referência "
            f"{referencia}: {', '.join(objetos_inexistentes)}"
        )


def executar_referencia(cursor, sql_modelo: str, referencia: int):
    ref_anterior = mes_anterior(referencia)
    ref_cadunico = obter_ref_cadunico(referencia)

    print("\n" + "=" * 80)
    print(f"▶️ Processando referência: {referencia}")
    print(f"   Referência anterior : {ref_anterior}")
    print(f"   Referência CadÚnico : {ref_cadunico}")
    print(f"   View esperada       : BASE_EXEMPLO_07.TABELA_EXEMPLO_077{referencia}_CADUN_{ref_cadunico}")
    print("=" * 80)

    inicio = time.time()

    print("🔎 Validando objetos necessários...")
    validar_objetos_referencia(cursor, referencia)

    # Apaga temporárias, caso existam na sessão
    executar_comando(cursor, "DROP TABLE VT_CAMPANHA", ignorar_erro=True)
    executar_comando(cursor, "DROP TABLE VT_BEN_CAD", ignorar_erro=True)

    if APAGAR_ANTES_DE_INSERIR:
        print(f"🧹 Apagando registros existentes da referência {referencia}...")
        cursor.execute(f"""
            DELETE FROM {TABELA_DESTINO}
            WHERE NU_MES_REF = {referencia}
        """)

    sql_referencia = preparar_sql(sql_modelo, referencia)
    comandos = dividir_comandos_sql(sql_referencia)

    print(f"📌 Total de comandos SQL a executar: {len(comandos)}")

    for i, comando in enumerate(comandos, start=1):
        print(f"   Executando comando {i}/{len(comandos)}...")
        executar_comando(cursor, comando)

    # Validação final
    cursor.execute(f"""
        SELECT 
            NU_MES_REF,
            TIPO_REGISTRO,
            COUNT(*) AS QTD
        FROM {TABELA_DESTINO}
        WHERE NU_MES_REF = {referencia}
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)

    resultados = cursor.fetchall()

    print(f"\n✅ Resultado carregado para {referencia}:")

    if resultados:
        for linha in resultados:
            print(linha)
    else:
        print("⚠️ Nenhum registro encontrado após a carga.")

    fim = time.time()
    duracao_min = (fim - inicio) / 60

    print(f"⏱️ Tempo da referência {referencia}: {duracao_min:.2f} minutos")


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():
    referencias = gerar_referencias(
        inicio=REFERENCIA_INICIAL,
        fim=REFERENCIA_FINAL
    )

    print("Referências que serão processadas:")
    print(referencias)

    sql_modelo = carregar_sql_modelo(ARQUIVO_SQL_MODELO)

    conexao = teradatasql.connect(
        host=TD_HOST,
        user=TD_USER,
        password=TD_PASSWORD,
        logmech=TD_LOGMECH
    )

    try:
        cursor = conexao.cursor()

        for referencia in referencias:
            try:
                executar_referencia(cursor, sql_modelo, referencia)
                conexao.commit()
                print(f"✅ Commit realizado para {referencia}")

            except Exception as erro:
                conexao.rollback()
                print(f"❌ Erro ao processar referência {referencia}")
                print(erro)
                print("Rollback realizado para essa referência.")

                if PARAR_NO_PRIMEIRO_ERRO:
                    raise

                print("➡️ Continuando para a próxima referência...")

    finally:
        conexao.close()
        print("\n🔒 Conexão encerrada.")


if __name__ == "__main__":
    main()