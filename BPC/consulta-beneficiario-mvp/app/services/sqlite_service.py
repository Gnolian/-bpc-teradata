import base64
import hashlib
import hmac
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from app.config.env_loader import load_app_env

BASE_DIR = Path(__file__).resolve().parents[2]
load_app_env(BASE_DIR)

DB_PATH = Path(os.getenv("SQLITE_DB_PATH", "data/beneficiarios.db")).expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class SQLiteServiceError(Exception):
    pass


MOTIVO_SENHA_INICIAL_EXPIRADA = "Senha inicial nao alterada em ate 3 dias."


def obter_caminho_banco():
    return DB_PATH


def verificar_espaco_sqlite(min_free_gb: float | None = None):
    if min_free_gb is None:
        min_free_gb = float(os.getenv("SQLITE_MIN_FREE_GB", "10"))

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(DB_PATH.parent)
    livre_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)

    if livre_gb < min_free_gb:
        raise SQLiteServiceError(
            "Espaço insuficiente no disco do SQLite. "
            f"Caminho: {DB_PATH}. Livre: {livre_gb:.1f} GB de {total_gb:.1f} GB. "
            f"Mínimo configurado: {min_free_gb:.1f} GB. "
            "Libere espaço ou configure SQLITE_DB_PATH para um disco maior."
        )

    return {
        "path": str(DB_PATH),
        "free_gb": livre_gb,
        "total_gb": total_gb,
        "min_free_gb": min_free_gb,
    }


def _str_para_bool(valor: str | None, padrao: bool = False) -> bool:
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "sim", "yes", "y")


def _sqlite_erro_retentavel(exc: Exception) -> bool:
    mensagem = str(exc).lower()
    return any(
        trecho in mensagem
        for trecho in (
            "database is locked",
            "database is busy",
            "disk i/o error",
            "unable to open database file",
        )
    )


def _executar_sqlite_com_retry(descricao: str, func):
    tentativas = int(os.getenv("SQLITE_WRITE_RETRIES", "8"))
    espera_base = float(os.getenv("SQLITE_WRITE_RETRY_SECONDS", "2"))
    ultima_excecao = None

    for tentativa in range(1, tentativas + 1):
        try:
            return func()
        except sqlite3.OperationalError as exc:
            ultima_excecao = exc
            if not _sqlite_erro_retentavel(exc) or tentativa == tentativas:
                raise

            espera = espera_base * tentativa
            print(
                f"[SQLITE RETRY] {descricao} falhou na tentativa "
                f"{tentativa}/{tentativas}: {exc}. Nova tentativa em {espera:.0f}s.",
                flush=True,
            )
            time.sleep(espera)

    raise ultima_excecao


@contextmanager
def get_connection():
    timeout = float(os.getenv("SQLITE_TIMEOUT_SECONDS", "60"))
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)};")
    try:
        yield conn
        if conn.in_transaction:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def configurar_pragmas(conn):
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA cache_size = -200000;")
    conn.execute("PRAGMA mmap_size = 268435456;")
    conn.execute("PRAGMA journal_size_limit = 67108864;")


def configurar_pragmas_carga(conn):
    journal_mode = os.getenv("SQLITE_LOAD_JOURNAL_MODE", "WAL").strip().upper()
    journal_modes_validos = {"WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"}
    if journal_mode not in journal_modes_validos:
        journal_mode = "WAL"

    if journal_mode == "WAL":
        configurar_pragmas(conn)
    else:
        conn.execute(f"PRAGMA journal_mode={journal_mode};")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA cache_size = -400000;")
        conn.execute("PRAGMA mmap_size = 268435456;")

    conn.execute("PRAGMA wal_autocheckpoint = 5000;")
    conn.execute("PRAGMA cache_size = -400000;")

    fast_load = _str_para_bool(os.getenv("SQLITE_FAST_LOAD", "false"), False)
    permitir_off = _str_para_bool(
        os.getenv("SQLITE_ALLOW_UNSAFE_SYNCHRONOUS_OFF", "false"),
        False,
    )
    if fast_load and permitir_off:
        conn.execute("PRAGMA synchronous=OFF;")

    if _str_para_bool(os.getenv("SQLITE_LOAD_EXCLUSIVE", "false"), False):
        conn.execute("PRAGMA locking_mode=EXCLUSIVE;")


def checkpoint_wal(truncate: bool = False):
    modo = "TRUNCATE" if truncate else "PASSIVE"

    def _run():
        with get_connection() as conn:
            return conn.execute(f"PRAGMA wal_checkpoint({modo});").fetchall()

    return _executar_sqlite_com_retry(f"checkpoint WAL {modo}", _run)


# =========================================================
# SENHAS / AUTENTICAÇÃO
# =========================================================

def gerar_hash_senha(senha: str) -> str:
    if not senha or not senha.strip():
        raise SQLiteServiceError("A senha não pode estar vazia.")

    salt = os.urandom(16)
    chave = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt,
        100_000
    )
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(chave).decode()}"


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        salt_b64, hash_b64 = senha_hash.split("$", 1)
        salt = base64.b64decode(salt_b64.encode())
        hash_original = base64.b64decode(hash_b64.encode())

        hash_teste = hashlib.pbkdf2_hmac(
            "sha256",
            senha.encode("utf-8"),
            salt,
            100_000
        )
        return hmac.compare_digest(hash_original, hash_teste)
    except Exception:
        return False


def _senha_padrao_usuarios() -> str:
    return os.getenv("USUARIO_SENHA_PADRAO", "")


def _senha_e_padrao(senha: str) -> bool:
    return senha == _senha_padrao_usuarios()


def _marcar_senha_padrao_pendente(conn):
    senha_padrao = _senha_padrao_usuarios()
    if not senha_padrao:
        return

    rows = conn.execute("""
        SELECT id, senha_hash
        FROM usuarios
        WHERE precisa_trocar_senha = 0
          AND senha_alterada_em IS NULL
    """).fetchall()

    for row in rows:
        if verificar_senha(senha_padrao, row["senha_hash"]):
            conn.execute("""
                UPDATE usuarios
                   SET precisa_trocar_senha = 1
                 WHERE id = ?
            """, (row["id"],))


def _inativar_usuarios_senha_inicial_expirada(conn):
    conn.execute("""
        UPDATE usuarios
           SET ativo = 0,
               inativado_em = CURRENT_TIMESTAMP,
               motivo_inativacao = ?
         WHERE ativo = 1
           AND precisa_trocar_senha = 1
           AND senha_alterada_em IS NULL
           AND datetime(COALESCE(reativado_em, created_at, CURRENT_TIMESTAMP), '+3 days') <= datetime('now')
           AND (
                perfil <> 'admin'
                OR EXISTS (
                    SELECT 1
                    FROM usuarios AS admin_ativo
                    WHERE admin_ativo.perfil = 'admin'
                      AND admin_ativo.ativo = 1
                      AND admin_ativo.id <> usuarios.id
                )
           )
    """, (MOTIVO_SENHA_INICIAL_EXPIRADA,))


def _executar_sqlite_sem_bloquear_app(conn, descricao: str, func) -> bool:
    busy_timeout_anterior = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    timeout_curto_ms = int(float(os.getenv("SQLITE_APP_WRITE_TIMEOUT_SECONDS", "1")) * 1000)

    try:
        conn.execute(f"PRAGMA busy_timeout = {timeout_curto_ms};")
        func()
        return True
    except sqlite3.OperationalError as exc:
        if _sqlite_erro_retentavel(exc):
            print(
                f"[AVISO] {descricao} ignorado temporariamente: "
                f"SQLite ocupado pela carga ({exc}).",
                flush=True,
            )
            return False
        raise
    finally:
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_anterior};")


def _executar_manutencao_usuarios_sem_bloquear(conn) -> bool:
    def _run():
        _marcar_senha_padrao_pendente(conn)
        _inativar_usuarios_senha_inicial_expirada(conn)

    return _executar_sqlite_sem_bloquear_app(
        conn,
        "Manutencao de usuarios",
        _run,
    )


# =========================================================
# CRIAÇÃO DE TABELAS
# =========================================================

def criar_tabela_usuarios(executar_manutencao: bool = False):
    with get_connection() as conn:
        configurar_pragmas(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                nome_completo TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL CHECK (perfil IN ('usuario', 'admin')),
                ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
                precisa_trocar_senha INTEGER NOT NULL DEFAULT 0 CHECK (precisa_trocar_senha IN (0, 1)),
                senha_alterada_em TEXT,
                inativado_em TEXT,
                motivo_inativacao TEXT,
                reativado_em TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        colunas_existentes = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(usuarios)").fetchall()
        }

        novas_colunas = {
            "precisa_trocar_senha": "INTEGER NOT NULL DEFAULT 0",
            "senha_alterada_em": "TEXT",
            "inativado_em": "TEXT",
            "motivo_inativacao": "TEXT",
            "reativado_em": "TEXT",
        }

        for coluna, tipo_sql in novas_colunas.items():
            if coluna not in colunas_existentes:
                conn.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} {tipo_sql}")

        if executar_manutencao:
            _executar_manutencao_usuarios_sem_bloquear(conn)


def criar_tabela_log_consultas():
    with get_connection() as conn:
        configurar_pragmas(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS log_consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                nome_completo TEXT,
                tipo_consulta TEXT,
                valor_pesquisado TEXT,
                quantidade_resultados INTEGER,
                data_hora TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


def criar_tabela_controle_cargas():
    with get_connection() as conn:
        configurar_pragmas(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS controle_cargas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competencia INTEGER NOT NULL,
                competencia_referencia INTEGER,
                nome_origem TEXT,
                data_arquivo TEXT,
                inicio_carga TEXT,
                fim_carga TEXT,
                total_registros INTEGER DEFAULT 0,
                qtd_bpc_pcd INTEGER DEFAULT 0,
                qtd_bpc_idoso INTEGER DEFAULT 0,
                qtd_auxilio_inclusao INTEGER DEFAULT 0,
                qtd_rmv_total INTEGER DEFAULT 0,
                qtd_zika_virus INTEGER DEFAULT 0,
                total_beneficios INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                observacao TEXT
            )
        """)

        colunas_existentes = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(controle_cargas)").fetchall()
        }

        novas_colunas = {
            "competencia_referencia": "INTEGER",
            "nome_origem": "TEXT",
            "data_arquivo": "TEXT",
            "inicio_carga": "TEXT",
            "fim_carga": "TEXT",
            "total_registros": "INTEGER DEFAULT 0",
            "qtd_bpc_pcd": "INTEGER DEFAULT 0",
            "qtd_bpc_idoso": "INTEGER DEFAULT 0",
            "qtd_auxilio_inclusao": "INTEGER DEFAULT 0",
            "qtd_rmv_total": "INTEGER DEFAULT 0",
            "qtd_zika_virus": "INTEGER DEFAULT 0",
            "total_beneficios": "INTEGER DEFAULT 0",
            "status": "TEXT",
            "observacao": "TEXT",
        }

        for coluna, definicao in novas_colunas.items():
            if coluna not in colunas_existentes:
                print(f"Adicionando coluna ausente em controle_cargas: {coluna}", flush=True)
                conn.execute(f"ALTER TABLE controle_cargas ADD COLUMN {coluna} {definicao}")

def criar_tabela_controle_carga_buckets():
    with get_connection() as conn:
        configurar_pragmas(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS controle_carga_buckets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carga_id INTEGER NOT NULL,
                competencia INTEGER NOT NULL,
                fase TEXT NOT NULL,
                bucket INTEGER NOT NULL,
                total_buckets INTEGER NOT NULL,
                status TEXT NOT NULL,
                registros_bucket INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(carga_id, fase, bucket)
            )
        """)

        colunas_existentes = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(controle_carga_buckets)").fetchall()
        }
        novas_colunas = {
            "chave_inicio": "TEXT",
            "chave_fim": "TEXT",
        }

        for coluna, definicao in novas_colunas.items():
            if coluna not in colunas_existentes:
                print(f"Adicionando coluna ausente em controle_carga_buckets: {coluna}", flush=True)
                conn.execute(f"ALTER TABLE controle_carga_buckets ADD COLUMN {coluna} {definicao}")

def marcar_bucket_status(
    carga_id: int,
    competencia: int,
    fase: str,
    bucket: int,
    total_buckets: int,
    status: str,
    registros_bucket: int = 0,
    chave_inicio: int | str | None = None,
    chave_fim: int | str | None = None,
):
    def _run():
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO controle_carga_buckets (
                    carga_id, competencia, fase, bucket, total_buckets, status,
                    registros_bucket, chave_inicio, chave_fim, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                ON CONFLICT(carga_id, fase, bucket)
                DO UPDATE SET
                    status = excluded.status,
                    registros_bucket = excluded.registros_bucket,
                    chave_inicio = COALESCE(excluded.chave_inicio, controle_carga_buckets.chave_inicio),
                    chave_fim = COALESCE(excluded.chave_fim, controle_carga_buckets.chave_fim),
                    updated_at = datetime('now', 'localtime')
            """, (
                carga_id,
                competencia,
                fase,
                bucket,
                total_buckets,
                status,
                registros_bucket,
                None if chave_inicio is None else str(chave_inicio),
                None if chave_fim is None else str(chave_fim),
            ))

    return _executar_sqlite_com_retry("checkpoint do lote", _run)

def listar_buckets_concluidos(carga_id: int):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT fase, bucket
            FROM controle_carga_buckets
            WHERE carga_id = ?
              AND status = 'SUCESSO'
        """, (carga_id,)).fetchall()

        return {(row["fase"], row["bucket"]) for row in rows}                


def listar_fases_concluidas(carga_id: int):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT fase
            FROM controle_carga_buckets
            WHERE carga_id = ?
              AND bucket = -1
              AND status = 'SUCESSO'
        """, (carga_id,)).fetchall()

        return {row["fase"] for row in rows}


def obter_ultimo_lote_sucesso(carga_id: int, fase: str):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT bucket, chave_fim
            FROM controle_carga_buckets
            WHERE carga_id = ?
              AND fase = ?
              AND bucket >= 0
              AND status = 'SUCESSO'
            ORDER BY bucket DESC
            LIMIT 1
        """, (carga_id, fase)).fetchone()

        if not row:
            return None

        return {
            "bucket": row["bucket"],
            "chave_fim": row["chave_fim"],
        }


def filtrar_registros_nao_carregados(
    df: pd.DataFrame,
    competencia: int,
    fase: str,
    chave_sql: str,
) -> pd.DataFrame:
    if df.empty or chave_sql not in df.columns:
        return df

    chaves = pd.to_numeric(df[chave_sql], errors="coerce")
    chaves_validas = sorted({int(chave) for chave in chaves.dropna()})

    if not chaves_validas:
        return df

    chaves_existentes = set()

    with get_connection() as conn:
        for inicio in range(0, len(chaves_validas), 900):
            parte = chaves_validas[inicio:inicio + 900]
            placeholders = ", ".join(["?"] * len(parte))
            rows = conn.execute(f"""
                SELECT CAST({chave_sql} AS INTEGER) AS chave
                FROM TABELA_EXEMPLO_001
                WHERE NU_MES_REF = ?
                  AND TIPO_REGISTRO = ?
                  AND CAST({chave_sql} AS INTEGER) IN ({placeholders})
            """, (str(competencia), fase, *parte)).fetchall()
            chaves_existentes.update(int(row["chave"]) for row in rows if row["chave"] is not None)

    if not chaves_existentes:
        return df

    mascara = ~chaves.fillna(-1).astype(int).isin(chaves_existentes)
    return df.loc[mascara].copy()


def limpar_buckets_carga_fase(carga_id: int, fase: str):
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM controle_carga_buckets
            WHERE carga_id = ?
              AND fase = ?
        """, (carga_id, fase))

def recriar_tabela_estrutura_api():
    with get_connection() as conn:
        configurar_pragmas(conn)
        conn.execute("DROP TABLE IF EXISTS TABELA_EXEMPLO_001")
        conn.execute("""
            CREATE TABLE TABELA_EXEMPLO_001 (
                TIPO_REGISTRO TEXT,
                NU_NB TEXT,
                CO_FAMILIAR_FAM TEXT,
                NU_CPF_T TEXT,
                NUM_CPF_PESSOA TEXT,
                CO_CHV_NATURAL_PESSOA TEXT,
                NU_NIS_T TEXT,
                NUM_NIS_PESSOA_ATUAL TEXT,
                NM_TIT_BENEF_T TEXT,
                NOM_PESSOA TEXT,
                DESC_PARENTESCO TEXT,
                FLAG_CADUNICO TEXT,
                FLAG_REF_MACICA_ANTERIOR TEXT,
                UF_MACICA TEXT,
                MUNICIPIO_MACICA TEXT,
                UF_CAD TEXT,
                MUNICIPIO_CAD TEXT,
                UF_AG_PGD TEXT,
                MUNICIPIO_AG_PGD TEXT,
                DT_NASC_T TEXT,
                DTA_NASC_PESSOA TEXT,
                IDADE_T INTEGER,
                IDADE_PESSOA INTEGER,
                NM_MAE_T TEXT,
                NOM_COMPLETO_MAE_PESSOA TEXT,
                GENERO TEXT,
                RACA_COR TEXT,
                IND_DORMIR_RUA_MEMB TEXT,
                FAMILIA_INDIGENA TEXT,
                FAMILIA_QUILOMBOLA TEXT,
                CS_ESPECIE TEXT,
                CID TEXT,
                DESCRICAO_CID TEXT,
                TIPO_DESPACHO TEXT,
                DT_DESPACHO TEXT,
                DT_ENTRADA_REQUERIMENTO TEXT,
                DT_INICIO_BENEFICIO TEXT,
                SITUACAO_CAD_UNICO TEXT,
                PARTICIPACAO_CAMPANHA TEXT,
                DTA_ATUAL_MEMB TEXT,
                NU_MES_REF INTEGER
            )
        """)


def criar_tabela_estrutura_api():
    with get_connection() as conn:
        configurar_pragmas(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS TABELA_EXEMPLO_001 (
                TIPO_REGISTRO TEXT,
                NU_NB TEXT,
                CO_FAMILIAR_FAM TEXT,
                NU_CPF_T TEXT,
                NUM_CPF_PESSOA TEXT,
                CO_CHV_NATURAL_PESSOA TEXT,
                NU_NIS_T TEXT,
                NUM_NIS_PESSOA_ATUAL TEXT,
                NM_TIT_BENEF_T TEXT,
                NOM_PESSOA TEXT,
                DESC_PARENTESCO TEXT,
                FLAG_CADUNICO TEXT,
                FLAG_REF_MACICA_ANTERIOR TEXT,
                UF_MACICA TEXT,
                MUNICIPIO_MACICA TEXT,
                UF_CAD TEXT,
                MUNICIPIO_CAD TEXT,
                UF_AG_PGD TEXT,
                MUNICIPIO_AG_PGD TEXT,
                DT_NASC_T TEXT,
                DTA_NASC_PESSOA TEXT,
                IDADE_T INTEGER,
                IDADE_PESSOA INTEGER,
                NM_MAE_T TEXT,
                NOM_COMPLETO_MAE_PESSOA TEXT,
                GENERO TEXT,
                RACA_COR TEXT,
                IND_DORMIR_RUA_MEMB TEXT,
                FAMILIA_INDIGENA TEXT,
                FAMILIA_QUILOMBOLA TEXT,
                CS_ESPECIE TEXT,
                CID TEXT,
                DESCRICAO_CID TEXT,
                TIPO_DESPACHO TEXT,
                DT_DESPACHO TEXT,
                DT_ENTRADA_REQUERIMENTO TEXT,
                DT_INICIO_BENEFICIO TEXT,
                SITUACAO_CAD_UNICO TEXT,
                PARTICIPACAO_CAMPANHA TEXT,
                DTA_ATUAL_MEMB TEXT,
                NU_MES_REF INTEGER
            )
        """)


def configurar_pragmas_indices(conn):
    def env_int(nome: str, padrao: int) -> int:
        try:
            return int(os.getenv(nome, str(padrao)))
        except (TypeError, ValueError):
            return padrao

    journal_mode = os.getenv("SQLITE_INDEX_JOURNAL_MODE", "WAL").strip().upper()
    journal_modes_validos = {"WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"}
    if journal_mode not in journal_modes_validos:
        journal_mode = "WAL"

    conn.execute(f"PRAGMA journal_mode={journal_mode};")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA mmap_size = 536870912;")

    cache_mb = env_int("SQLITE_INDEX_CACHE_MB", 1024)
    conn.execute(f"PRAGMA cache_size = -{max(cache_mb, 64) * 1024};")

    synchronous = os.getenv("SQLITE_INDEX_SYNCHRONOUS", "FULL").strip().upper()
    if synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
        synchronous = "FULL"
    permitir_off = _str_para_bool(
        os.getenv("SQLITE_ALLOW_UNSAFE_INDEX_SYNCHRONOUS_OFF", "false"),
        False,
    )
    if synchronous == "OFF" and not permitir_off:
        synchronous = "FULL"
    conn.execute(f"PRAGMA synchronous={synchronous};")

    threads = env_int("SQLITE_INDEX_THREADS", 4)
    if threads > 0:
        conn.execute(f"PRAGMA threads={threads};")

    if _str_para_bool(os.getenv("SQLITE_INDEX_EXCLUSIVE", "true"), True):
        conn.execute("PRAGMA locking_mode=EXCLUSIVE;")


def _formatar_duracao_segundos(segundos: float | int | None) -> str:
    try:
        total = int(round(float(segundos or 0)))
    except (TypeError, ValueError):
        total = 0

    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)

    if horas:
        return f"{horas}h {minutos:02d}min {segundos:02d}s"
    if minutos:
        return f"{minutos}min {segundos:02d}s"
    return f"{segundos}s"


def _callback_indice(progress_callback, evento: str, dados: dict):
    if progress_callback:
        progress_callback(evento, dados)
        return

    if not _str_para_bool(os.getenv("SQLITE_INDEX_VERBOSE", "true"), True):
        return

    nome = dados.get("nome", "")
    etapa = dados.get("etapa", 0)
    total = dados.get("total", 0)

    if evento == "inicio":
        print(
            f"[INDICE {etapa}/{total}] Criando {nome}: {dados.get('descricao', '')}",
            flush=True,
        )
    elif evento == "batimento":
        print(
            f"[INDICE {etapa}/{total}] {nome} ainda em construcao "
            f"| decorrido: {_formatar_duracao_segundos(dados.get('decorrido', 0))}",
            flush=True,
        )
    elif evento == "fim":
        print(
            f"[INDICE {etapa}/{total}] {nome} concluido "
            f"em {_formatar_duracao_segundos(dados.get('duracao', 0))}",
            flush=True,
        )
    elif evento == "pulado":
        print(
            f"[INDICE {etapa}/{total}] {nome} ja existe. Pulando.",
            flush=True,
        )
    elif evento == "ignorado":
        print(
            f"[INDICE {etapa}/{total}] {nome} ignorado. "
            f"Colunas ausentes: {', '.join(dados.get('colunas_ausentes', []))}",
            flush=True,
        )


def _criar_indice_com_progresso(conn, indice: dict, etapa: int, total: int, progress_callback=None):
    nome = indice["nome"]
    existentes = indice["existentes"]

    dados_base = {
        "nome": nome,
        "descricao": indice.get("descricao", ""),
        "etapa": etapa,
        "total": total,
    }

    if nome in existentes:
        _callback_indice(progress_callback, "pulado", dados_base)
        return False

    colunas_ausentes = sorted(indice["colunas"] - indice["colunas_estrutura"])
    if colunas_ausentes:
        dados = dict(dados_base)
        dados["colunas_ausentes"] = colunas_ausentes
        _callback_indice(progress_callback, "ignorado", dados)
        return False

    inicio = time.perf_counter()
    ultimo_batimento = {"valor": inicio}
    try:
        intervalo = int(os.getenv("SQLITE_INDEX_PROGRESS_SECONDS", "60"))
    except (TypeError, ValueError):
        intervalo = 60
    intervalo = max(10, intervalo)

    def progress_handler():
        agora = time.perf_counter()
        if agora - ultimo_batimento["valor"] >= intervalo:
            dados = dict(dados_base)
            dados["decorrido"] = agora - inicio
            _callback_indice(progress_callback, "batimento", dados)
            ultimo_batimento["valor"] = agora
        return 0

    _callback_indice(progress_callback, "inicio", dados_base)
    try:
        progress_ops = int(os.getenv("SQLITE_INDEX_PROGRESS_OPS", "50000"))
    except (TypeError, ValueError):
        progress_ops = 50000
    progress_ops = max(1, progress_ops)
    conn.set_progress_handler(progress_handler, progress_ops)
    try:
        conn.execute(indice["sql"])
        conn.commit()
        existentes.add(nome)
    finally:
        conn.set_progress_handler(None, 0)

    dados = dict(dados_base)
    dados["duracao"] = time.perf_counter() - inicio
    _callback_indice(progress_callback, "fim", dados)
    return True


def criar_indices(incluir_opcionais: bool | None = None, progress_callback=None):
    if incluir_opcionais is None:
        incluir_opcionais = str(os.getenv("SQLITE_CREATE_OPTIONAL_INDEXES", "false")).strip().lower() in {
            "1",
            "true",
            "t",
            "sim",
            "yes",
            "y",
        }

    with get_connection() as conn:
        configurar_pragmas_indices(conn)

        colunas_estrutura = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(TABELA_EXEMPLO_001)").fetchall()
        }
        indices_existentes = {
            row["name"]
            for row in conn.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                  AND name NOT LIKE 'sqlite_autoindex%'
            """).fetchall()
        }

        indices = [
            {
                "nome": "idx_estrutura_nb",
                "colunas": {"NU_NB"},
                "descricao": "busca por numero do beneficio",
                "sql": "CREATE INDEX idx_estrutura_nb ON TABELA_EXEMPLO_001 (NU_NB)",
            },
            {
                "nome": "idx_estrutura_cpf_titular",
                "colunas": {"NU_CPF_T"},
                "descricao": "busca por CPF do titular",
                "sql": "CREATE INDEX idx_estrutura_cpf_titular ON TABELA_EXEMPLO_001 (NU_CPF_T)",
            },
            {
                "nome": "idx_estrutura_cpf_pessoa",
                "colunas": {"NUM_CPF_PESSOA"},
                "descricao": "busca por CPF da pessoa",
                "sql": "CREATE INDEX idx_estrutura_cpf_pessoa ON TABELA_EXEMPLO_001 (NUM_CPF_PESSOA)",
            },
            {
                "nome": "idx_estrutura_familia",
                "colunas": {"CO_FAMILIAR_FAM"},
                "descricao": "busca por codigo familiar",
                "sql": "CREATE INDEX idx_estrutura_familia ON TABELA_EXEMPLO_001 (CO_FAMILIAR_FAM)",
            },
            {
                "nome": "idx_estrutura_competencia",
                "colunas": {"NU_MES_REF"},
                "descricao": "filtros por competencia/referencia",
                "sql": "CREATE INDEX idx_estrutura_competencia ON TABELA_EXEMPLO_001 (NU_MES_REF)",
            },
            {
                "nome": "idx_logs_data_hora",
                "colunas": set(),
                "descricao": "ordenacao dos logs de consulta",
                "sql": "CREATE INDEX idx_logs_data_hora ON log_consultas (data_hora DESC)",
            },
            {
                "nome": "idx_usuarios_username",
                "colunas": set(),
                "descricao": "login de usuarios",
                "sql": "CREATE INDEX idx_usuarios_username ON usuarios (username)",
            },
        ]

        if incluir_opcionais:
            indices.extend([
                {
                    "nome": "idx_estrutura_chave_pessoa",
                    "colunas": {"CO_CHV_NATURAL_PESSOA"},
                    "descricao": "retomada/analise por chave natural da pessoa",
                    "sql": "CREATE INDEX idx_estrutura_chave_pessoa ON TABELA_EXEMPLO_001 (CO_CHV_NATURAL_PESSOA)",
                },
                {
                    "nome": "idx_estrutura_tipo_registro",
                    "colunas": {"TIPO_REGISTRO"},
                    "descricao": "filtros por tipo de registro",
                    "sql": "CREATE INDEX idx_estrutura_tipo_registro ON TABELA_EXEMPLO_001 (TIPO_REGISTRO)",
                },
                {
                    "nome": "idx_estrutura_cpf_titular_comp",
                    "colunas": {"NU_CPF_T", "NU_MES_REF"},
                    "descricao": "busca por CPF do titular com ordenacao por referencia",
                    "sql": "CREATE INDEX idx_estrutura_cpf_titular_comp ON TABELA_EXEMPLO_001 (NU_CPF_T, NU_MES_REF)",
                },
                {
                    "nome": "idx_estrutura_cpf_pessoa_comp",
                    "colunas": {"NUM_CPF_PESSOA", "NU_MES_REF"},
                    "descricao": "busca por CPF da pessoa com ordenacao por referencia",
                    "sql": "CREATE INDEX idx_estrutura_cpf_pessoa_comp ON TABELA_EXEMPLO_001 (NUM_CPF_PESSOA, NU_MES_REF)",
                },
                {
                    "nome": "idx_estrutura_nb_comp",
                    "colunas": {"NU_NB", "NU_MES_REF"},
                    "descricao": "busca por NB com ordenacao por referencia",
                    "sql": "CREATE INDEX idx_estrutura_nb_comp ON TABELA_EXEMPLO_001 (NU_NB, NU_MES_REF)",
                },
                {
                    "nome": "idx_estrutura_familia_ref",
                    "colunas": {"CO_FAMILIAR_FAM", "NU_MES_REF"},
                    "descricao": "linha do tempo do grupo familiar",
                    "sql": "CREATE INDEX idx_estrutura_familia_ref ON TABELA_EXEMPLO_001 (CO_FAMILIAR_FAM, NU_MES_REF DESC)",
                },
                {
                    "nome": "idx_estrutura_familia_comp",
                    "colunas": {"CO_FAMILIAR_FAM", "TIPO_REGISTRO", "NOM_PESSOA"},
                    "descricao": "composicao do grupo familiar",
                    "sql": "CREATE INDEX idx_estrutura_familia_comp ON TABELA_EXEMPLO_001 (CO_FAMILIAR_FAM, TIPO_REGISTRO, NOM_PESSOA)",
                },
                {
                    "nome": "idx_estrutura_tipo_ref",
                    "colunas": {"TIPO_REGISTRO", "NU_MES_REF"},
                    "descricao": "filtros por tipo e referencia",
                    "sql": "CREATE INDEX idx_estrutura_tipo_ref ON TABELA_EXEMPLO_001 (TIPO_REGISTRO, NU_MES_REF DESC)",
                },
            ])

        total = len(indices)
        inicio_total = time.perf_counter()
        for etapa, indice in enumerate(indices, start=1):
            indice["existentes"] = indices_existentes
            indice["colunas_estrutura"] = colunas_estrutura
            _criar_indice_com_progresso(conn, indice, etapa, total, progress_callback)

        if _str_para_bool(os.getenv("SQLITE_ANALYZE_AFTER_INDEXES", "false"), False):
            print("Atualizando estatisticas do SQLite (ANALYZE)...", flush=True)
            conn.execute("ANALYZE")
            conn.commit()

        print(
            "Construcao de indices finalizada em "
            f"{_formatar_duracao_segundos(time.perf_counter() - inicio_total)}.",
            flush=True,
        )


def contar_indices_estrutura_api():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = 'TABELA_EXEMPLO_001'
              AND name NOT LIKE 'sqlite_autoindex%'
        """).fetchone()
        return int(row["total"]) if row and row["total"] is not None else 0


def listar_indices_estrutura_api():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = 'TABELA_EXEMPLO_001'
              AND name NOT LIKE 'sqlite_autoindex%'
        """).fetchall()
        return {row["name"] for row in rows}


def listar_indices_consulta_ausentes():
    with get_connection() as conn:
        colunas = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(TABELA_EXEMPLO_001)").fetchall()
        }
        indices_existentes = {
            row["name"]
            for row in conn.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                  AND tbl_name = 'TABELA_EXEMPLO_001'
                  AND name NOT LIKE 'sqlite_autoindex%'
            """).fetchall()
        }

    indices_por_colunas = {
        "idx_estrutura_nb": {"NU_NB"},
        "idx_estrutura_cpf_titular": {"NU_CPF_T"},
        "idx_estrutura_cpf_pessoa": {"NUM_CPF_PESSOA"},
        "idx_estrutura_familia": {"CO_FAMILIAR_FAM"},
        "idx_estrutura_competencia": {"NU_MES_REF"},
    }
    indices_esperados = {
        nome
        for nome, colunas_necessarias in indices_por_colunas.items()
        if colunas_necessarias.issubset(colunas)
    }
    return sorted(indices_esperados - indices_existentes)


def verificar_prontidao_consulta():
    with get_connection() as conn:
        tabela_controle = conn.execute("""
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'controle_cargas'
        """).fetchone()

        carga = None
        if tabela_controle:
            carga = conn.execute("""
                SELECT competencia, status, fase_atual, inicio_carga
                FROM controle_cargas
                WHERE status = 'EM_ANDAMENTO'
                ORDER BY id DESC
                LIMIT 1
            """).fetchone()

    total_indices = contar_indices_estrutura_api()
    indices_ausentes = listar_indices_consulta_ausentes()
    return {
        "indices_estrutura_api": total_indices,
        "indices_ausentes": indices_ausentes,
        "carga_em_andamento": dict(carga) if carga else None,
        "consulta_bloqueada": bool(indices_ausentes) and carga is not None,
        "precisa_recriar_indices": bool(indices_ausentes) and carga is None,
    }


def remover_indices_estrutura_api():
    with get_connection() as conn:
        indices = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = 'TABELA_EXEMPLO_001'
              AND name NOT LIKE 'sqlite_autoindex%'
        """).fetchall()

        for indice in indices:
            conn.execute(f"DROP INDEX IF EXISTS {indice['name']}")


def calcular_metricas_competencia(competencia: int):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                ? AS competencia_referencia,

                COUNT(DISTINCT CASE
                    WHEN TIPO_REGISTRO IN ('BENEFICIARIO_CADUNICO', 'NAO_CADASTRADO')
                     AND REPLACE(TRIM(COALESCE(CS_ESPECIE, '')), '.0', '') = '87'
                     AND NU_NB IS NOT NULL
                    THEN NU_NB
                END) AS qtd_bpc_pcd,

                COUNT(DISTINCT CASE
                    WHEN TIPO_REGISTRO IN ('BENEFICIARIO_CADUNICO', 'NAO_CADASTRADO')
                     AND REPLACE(TRIM(COALESCE(CS_ESPECIE, '')), '.0', '') = '88'
                     AND NU_NB IS NOT NULL
                    THEN NU_NB
                END) AS qtd_bpc_idoso,

                COUNT(DISTINCT CASE
                    WHEN TIPO_REGISTRO IN ('BENEFICIARIO_CADUNICO', 'NAO_CADASTRADO')
                     AND REPLACE(TRIM(COALESCE(CS_ESPECIE, '')), '.0', '') = '18'
                     AND NU_NB IS NOT NULL
                    THEN NU_NB
                END) AS qtd_auxilio_inclusao,

                COUNT(DISTINCT CASE
                    WHEN TIPO_REGISTRO IN ('BENEFICIARIO_CADUNICO', 'NAO_CADASTRADO')
                     AND REPLACE(TRIM(COALESCE(CS_ESPECIE, '')), '.0', '') IN ('11', '12', '30', '40')
                     AND NU_NB IS NOT NULL
                    THEN NU_NB
                END) AS qtd_rmv_total,

                COUNT(DISTINCT CASE
                    WHEN TIPO_REGISTRO IN ('BENEFICIARIO_CADUNICO', 'NAO_CADASTRADO')
                     AND REPLACE(TRIM(COALESCE(CS_ESPECIE, '')), '.0', '') = '60'
                     AND NU_NB IS NOT NULL
                    THEN NU_NB
                END) AS qtd_zika_virus,

                COUNT(DISTINCT CASE
                    WHEN TIPO_REGISTRO IN ('BENEFICIARIO_CADUNICO', 'NAO_CADASTRADO')
                     AND REPLACE(TRIM(COALESCE(CS_ESPECIE, '')), '.0', '') IN ('87', '88')
                     AND NU_NB IS NOT NULL
                    THEN NU_NB
                END) AS total_beneficios,

                COUNT(*) AS total_registros
            FROM TABELA_EXEMPLO_001
            WHERE NU_MES_REF = ?
        """, (competencia, competencia)).fetchone()

        return {
            "competencia_referencia": row["competencia_referencia"] if row else competencia,
            "qtd_bpc_pcd": row["qtd_bpc_pcd"] if row else 0,
            "qtd_bpc_idoso": row["qtd_bpc_idoso"] if row else 0,
            "qtd_auxilio_inclusao": row["qtd_auxilio_inclusao"] if row else 0,
            "qtd_rmv_total": row["qtd_rmv_total"] if row else 0,
            "qtd_zika_virus": row["qtd_zika_virus"] if row else 0,
            "total_beneficios": row["total_beneficios"] if row else 0,
            "total_registros": row["total_registros"] if row else 0,
        }


# =========================================================
# CONTROLE DE CARGA
# =========================================================

def obter_carga_sucesso(competencia: int):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT *
            FROM controle_cargas
            WHERE competencia = ?
              AND status = 'SUCESSO'
            ORDER BY id DESC
            LIMIT 1
        """, (competencia,)).fetchone()
        return dict(row) if row else None


def registrar_inicio_carga(
    competencia: int,
    nome_origem: str = None,
    data_arquivo: str = None,
    observacao: str = None
):
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO controle_cargas (
                competencia, nome_origem, data_arquivo, inicio_carga, status, observacao
            ) VALUES (
                ?, ?, ?, datetime('now', 'localtime'), 'EM_ANDAMENTO', ?
            )
        """, (competencia, nome_origem, data_arquivo, observacao))
        return cursor.lastrowid


def registrar_fim_carga(carga_id: int, total_registros: int, status: str, observacao: str = None):
    def _run():
        with get_connection() as conn:
            conn.execute("""
                UPDATE controle_cargas
                   SET fim_carga = datetime('now', 'localtime'),
                       total_registros = ?,
                       status = ?,
                       observacao = ?
                 WHERE id = ?
            """, (total_registros, status, observacao, carga_id))

    return _executar_sqlite_com_retry("finalizacao da carga", _run)


def encerrar_cargas_em_andamento(observacao: str = None):
    with get_connection() as conn:
        conn.execute("""
            UPDATE controle_cargas
               SET fim_carga = datetime('now', 'localtime'),
                   status = 'ERRO',
                   observacao = COALESCE(?, observacao, 'Carga encerrada manualmente para liberar consultas.')
             WHERE status = 'EM_ANDAMENTO'
        """, (observacao,))


def excluir_competencia(competencia: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM TABELA_EXEMPLO_001 WHERE NU_MES_REF = ?", (competencia,))


def limpar_controle_competencia(competencia: int):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM controle_carga_buckets WHERE competencia = ?",
            (competencia,),
        )
        conn.execute(
            "DELETE FROM controle_cargas WHERE competencia = ?",
            (competencia,),
        )


def _normalizar_documento(valor, tamanho=None):
    if pd.isna(valor) or valor is None:
        return None

    texto = str(valor).strip()

    if texto.lower() in ("", "nan", "none"):
        return None

    if texto.endswith(".0"):
        texto = texto[:-2]

    texto = "".join(ch for ch in texto if ch.isdigit())

    if not texto:
        return None

    if tamanho:
        texto = texto.zfill(tamanho)

    return texto


def inserir_lote(df: pd.DataFrame):
    if df.empty:
        return 0

    df = df.copy()

    if "NU_CPF_T" in df.columns:
        df["NU_CPF_T"] = df["NU_CPF_T"].apply(lambda x: _normalizar_documento(x, 11))

    if "NUM_CPF_PESSOA" in df.columns:
        df["NUM_CPF_PESSOA"] = df["NUM_CPF_PESSOA"].apply(lambda x: _normalizar_documento(x, 11))

    if "NU_NIS_T" in df.columns:
        df["NU_NIS_T"] = df["NU_NIS_T"].apply(_normalizar_documento)

    if "NUM_NIS_PESSOA_ATUAL" in df.columns:
        df["NUM_NIS_PESSOA_ATUAL"] = df["NUM_NIS_PESSOA_ATUAL"].apply(_normalizar_documento)

    if "NU_NB" in df.columns:
        df["NU_NB"] = df["NU_NB"].apply(lambda x: _normalizar_documento(x, 10))

    if "CO_FAMILIAR_FAM" in df.columns:
        df["CO_FAMILIAR_FAM"] = df["CO_FAMILIAR_FAM"].apply(_normalizar_documento)

    if "CO_CHV_NATURAL_PESSOA" in df.columns:
        df["CO_CHV_NATURAL_PESSOA"] = df["CO_CHV_NATURAL_PESSOA"].apply(_normalizar_documento)

    colunas = list(df.columns)
    placeholders = ", ".join(["?"] * len(colunas))
    sql = f"""
        INSERT INTO TABELA_EXEMPLO_001 ({", ".join(colunas)})
        VALUES ({placeholders})
    """

    registros = [
        tuple(None if pd.isna(value) else value for value in row)
        for row in df.itertuples(index=False, name=None)
    ]

    with get_connection() as conn:
        configurar_pragmas_carga(conn)
        conn.executemany(sql, registros)

    return len(registros)


def contar_registros_competencia(competencia: int):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total
            FROM TABELA_EXEMPLO_001
            WHERE NU_MES_REF = ?
        """, (competencia,)).fetchone()
        return row["total"] if row else 0


def contar_registros_competencia_fase(competencia: int, fase: str):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total
            FROM TABELA_EXEMPLO_001
            WHERE NU_MES_REF = ?
              AND TIPO_REGISTRO = ?
        """, (competencia, fase)).fetchone()
        return row["total"] if row else 0


def atualizar_metricas_carga(
    carga_id: int,
    competencia_referencia: int,
    qtd_bpc_pcd: int,
    qtd_bpc_idoso: int,
    qtd_auxilio_inclusao: int,
    qtd_rmv_total: int,
    qtd_zika_virus: int,
    total_beneficios: int,
    total_registros: int
):
    with get_connection() as conn:
        conn.execute("""
            UPDATE controle_cargas
               SET competencia_referencia = ?,
                   qtd_bpc_pcd = ?,
                   qtd_bpc_idoso = ?,
                   qtd_auxilio_inclusao = ?,
                   qtd_rmv_total = ?,
                   qtd_zika_virus = ?,
                   total_beneficios = ?,
                   total_registros = ?
             WHERE id = ?
        """, (
            competencia_referencia,
            qtd_bpc_pcd,
            qtd_bpc_idoso,
            qtd_auxilio_inclusao,
            qtd_rmv_total,
            qtd_zika_virus,
            total_beneficios,
            total_registros,
            carga_id
        ))


def listar_competencias_disponiveis():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT NU_MES_REF
            FROM TABELA_EXEMPLO_001
            WHERE NU_MES_REF IS NOT NULL
            ORDER BY NU_MES_REF DESC
        """).fetchall()
        return [row["NU_MES_REF"] for row in rows]


def obter_periodo_competencias_disponiveis():
    with get_connection() as conn:
        tabela_controle = conn.execute("""
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'controle_cargas'
        """).fetchone()

        if tabela_controle:
            row = conn.execute("""
                SELECT
                    MIN(CAST(competencia AS INTEGER)) AS primeira_ref,
                    MAX(CAST(competencia AS INTEGER)) AS ultima_ref
                FROM controle_cargas
                WHERE status = 'SUCESSO'
                  AND competencia IS NOT NULL
            """).fetchone()
            if row and row["primeira_ref"] is not None and row["ultima_ref"] is not None:
                return int(row["primeira_ref"]), int(row["ultima_ref"])

        row = conn.execute("""
            SELECT
                MIN(NU_MES_REF) AS primeira_ref,
                MAX(NU_MES_REF) AS ultima_ref
            FROM TABELA_EXEMPLO_001
            WHERE NU_MES_REF IS NOT NULL
        """).fetchone()
        if row and row["primeira_ref"] is not None and row["ultima_ref"] is not None:
            return int(row["primeira_ref"]), int(row["ultima_ref"])

    competencia_padrao = os.getenv("TD_COMPETENCIA", "202601")
    try:
        referencia = int(str(competencia_padrao).strip())
    except ValueError:
        referencia = 202601
    return referencia, referencia


def criar_colunas_checkpoint_controle_cargas():
    with get_connection() as conn:
        configurar_pragmas(conn)

        colunas_existentes = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(controle_cargas)").fetchall()
        }

        novas_colunas = {
            "pagina_atual": "INTEGER DEFAULT 0",
            "total_paginas": "INTEGER DEFAULT 0",
            "registros_inseridos_parcial": "INTEGER DEFAULT 0",
            "fase_atual": "TEXT",
        }

        for coluna, definicao in novas_colunas.items():
            if coluna not in colunas_existentes:
                print(f"Adicionando coluna de checkpoint em controle_cargas: {coluna}", flush=True)
                conn.execute(f"ALTER TABLE controle_cargas ADD COLUMN {coluna} {definicao}")

def obter_carga_em_andamento(competencia: int):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT *
            FROM controle_cargas
            WHERE competencia = ?
              AND status IN ('EM_ANDAMENTO', 'ERRO')
            ORDER BY id DESC
            LIMIT 1
        """, (competencia,)).fetchone()
        return dict(row) if row else None


def atualizar_checkpoint_carga(
    carga_id: int,
    fase_atual: str,
    pagina_atual: int,
    total_paginas: int,
    registros_inseridos_parcial: int,
    observacao: str = None
):
    def _run():
        with get_connection() as conn:
            conn.execute("""
                UPDATE controle_cargas
                   SET fase_atual = ?,
                       pagina_atual = ?,
                       total_paginas = ?,
                       registros_inseridos_parcial = ?,
                       observacao = COALESCE(?, observacao)
                 WHERE id = ?
            """, (
                fase_atual,
                pagina_atual,
                total_paginas,
                registros_inseridos_parcial,
                observacao,
                carga_id
            ))

    return _executar_sqlite_com_retry("checkpoint da carga", _run)


def excluir_competencia_tipo_registro(competencia: int, tipo_registro: str):
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM TABELA_EXEMPLO_001
            WHERE NU_MES_REF = ?
              AND TIPO_REGISTRO = ?
        """, (competencia, tipo_registro))


def obter_ultima_carga(competencia: int):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT *
            FROM controle_cargas
            WHERE competencia = ?
            ORDER BY id DESC
            LIMIT 1
        """, (competencia,)).fetchone()
        return dict(row) if row else None


def contar_registros_estrutura_api(competencia: int):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total
            FROM TABELA_EXEMPLO_001
            WHERE NU_MES_REF = ?
        """, (competencia,)).fetchone()
        return row["total"] if row else 0

# =========================================================
# USUÁRIOS
# =========================================================

def listar_usuarios() -> pd.DataFrame:
    criar_tabela_usuarios(executar_manutencao=True)
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT
                id,
                username,
                nome_completo,
                perfil,
                ativo,
                precisa_trocar_senha,
                senha_alterada_em,
                inativado_em,
                motivo_inativacao,
                created_at
            FROM usuarios
            ORDER BY nome_completo
        """, conn)


def buscar_usuario_por_id(user_id: int):
    criar_tabela_usuarios()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                id,
                username,
                nome_completo,
                perfil,
                ativo,
                precisa_trocar_senha,
                senha_alterada_em,
                inativado_em,
                motivo_inativacao,
                created_at
            FROM usuarios
            WHERE id = ?
        """, (user_id,)).fetchone()
        return dict(row) if row else None


def buscar_usuario_por_username(username: str):
    username = (username or "").strip()

    criar_tabela_usuarios()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT *
            FROM usuarios
            WHERE username = ?
        """, (username,)).fetchone()
        return dict(row) if row else None


def criar_usuario(username: str, nome_completo: str, senha: str, perfil: str = "usuario"):
    username = (username or "").strip()
    nome_completo = (nome_completo or "").strip()
    perfil = (perfil or "").strip().lower()

    if not username:
        raise SQLiteServiceError("Informe o usuário.")
    if not nome_completo:
        raise SQLiteServiceError("Informe o nome completo.")
    if not senha:
        raise SQLiteServiceError("Informe a senha.")
    if perfil not in {"usuario", "admin"}:
        raise SQLiteServiceError("Perfil inválido.")

    if buscar_usuario_por_username(username):
        raise SQLiteServiceError("Já existe um usuário com esse login.")

    senha_hash = gerar_hash_senha(senha)

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO usuarios (
                username,
                nome_completo,
                senha_hash,
                perfil,
                ativo,
                precisa_trocar_senha
            )
            VALUES (?, ?, ?, ?, 1, 1)
        """, (username, nome_completo, senha_hash, perfil))


def alterar_status_usuario(user_id: int, ativo: int):
    if ativo not in (0, 1):
        raise SQLiteServiceError("Status inválido.")

    with get_connection() as conn:
        if ativo == 1:
            cursor = conn.execute("""
                UPDATE usuarios
                   SET ativo = 1,
                       inativado_em = NULL,
                       motivo_inativacao = NULL,
                       reativado_em = CURRENT_TIMESTAMP
                 WHERE id = ?
            """, (user_id,))
        else:
            cursor = conn.execute("""
                UPDATE usuarios
                   SET ativo = 0,
                       inativado_em = CURRENT_TIMESTAMP,
                       motivo_inativacao = COALESCE(motivo_inativacao, 'Inativado manualmente por administrador.')
                 WHERE id = ?
            """, (user_id,))

        if cursor.rowcount == 0:
            raise SQLiteServiceError("Usuário não encontrado.")


def alterar_perfil_usuario(user_id: int, perfil: str):
    perfil = (perfil or "").strip().lower()
    if perfil not in {"usuario", "admin"}:
        raise SQLiteServiceError("Perfil inválido.")

    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE usuarios
               SET perfil = ?
             WHERE id = ?
        """, (perfil, user_id))

        if cursor.rowcount == 0:
            raise SQLiteServiceError("Usuário não encontrado.")


def redefinir_senha_usuario(user_id: int, nova_senha: str):
    if not nova_senha or not nova_senha.strip():
        raise SQLiteServiceError("A nova senha não pode estar vazia.")

    senha_hash = gerar_hash_senha(nova_senha)

    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE usuarios
               SET senha_hash = ?,
                   ativo = 1,
                   precisa_trocar_senha = 1,
                   senha_alterada_em = NULL,
                   inativado_em = NULL,
                   motivo_inativacao = NULL,
                   reativado_em = CURRENT_TIMESTAMP
             WHERE id = ?
        """, (senha_hash, user_id))

        if cursor.rowcount == 0:
            raise SQLiteServiceError("Usuário não encontrado.")

def alterar_propria_senha(user_id: int, senha_atual: str, nova_senha: str, confirmar_nova_senha: str):
    if not senha_atual or not senha_atual.strip():
        raise SQLiteServiceError("Informe a senha atual.")
    if not nova_senha or not nova_senha.strip():
        raise SQLiteServiceError("Informe a nova senha.")
    if nova_senha != confirmar_nova_senha:
        raise SQLiteServiceError("A confirmação da nova senha não confere.")
    if len(nova_senha.strip()) < 8:
        raise SQLiteServiceError("A nova senha deve ter pelo menos 8 caracteres.")
    if _senha_e_padrao(nova_senha):
        raise SQLiteServiceError("A nova senha não pode ser a senha padrão.")

    with get_connection() as conn:
        row = conn.execute("""
            SELECT senha_hash
            FROM usuarios
            WHERE id = ?
        """, (user_id,)).fetchone()

        if not row:
            raise SQLiteServiceError("Usuário não encontrado.")

        if not verificar_senha(senha_atual, row["senha_hash"]):
            raise SQLiteServiceError("A senha atual informada está incorreta.")

        if verificar_senha(nova_senha, row["senha_hash"]):
            raise SQLiteServiceError("A nova senha deve ser diferente da senha atual.")

        senha_hash = gerar_hash_senha(nova_senha)
        cursor = conn.execute("""
            UPDATE usuarios
               SET senha_hash = ?,
                   precisa_trocar_senha = 0,
                   senha_alterada_em = CURRENT_TIMESTAMP,
                   ativo = 1,
                   inativado_em = NULL,
                   motivo_inativacao = NULL
             WHERE id = ?
        """, (senha_hash, user_id))

        if cursor.rowcount == 0:
            raise SQLiteServiceError("Usuário não encontrado.")


def alterar_senha_por_login(
    username: str,
    senha_atual: str,
    nova_senha: str,
    confirmar_nova_senha: str,
):
    username = (username or "").strip()

    if not username:
        raise SQLiteServiceError("Informe o usuário.")

    usuario = buscar_usuario_por_username(username)
    if not usuario:
        raise SQLiteServiceError("Usuário não encontrado.")

    if int(usuario.get("ativo", 0)) != 1:
        raise SQLiteServiceError("Usuário inativo.")

    alterar_propria_senha(
        user_id=usuario["id"],
        senha_atual=senha_atual,
        nova_senha=nova_senha,
        confirmar_nova_senha=confirmar_nova_senha,
    )

def autenticar_usuario(username: str, senha: str):
    criar_tabela_usuarios()
    usuario = buscar_usuario_por_username(username)
    if not usuario:
        return None

    if int(usuario.get("ativo", 0)) != 1:
        if usuario.get("motivo_inativacao") == MOTIVO_SENHA_INICIAL_EXPIRADA:
            raise SQLiteServiceError(
                "Usuário inativado porque a senha inicial não foi alterada em até 3 dias. "
                "Solicite a reativação ao administrador."
            )
        raise SQLiteServiceError(
            "Usuário inativo. Solicite a reativação ao administrador."
        )

    if not verificar_senha(senha, usuario.get("senha_hash", "")):
        return None

    with get_connection() as conn:
        _executar_manutencao_usuarios_sem_bloquear(conn)

    usuario = buscar_usuario_por_username(username)
    if int(usuario.get("ativo", 0)) != 1:
        raise SQLiteServiceError(
            "Usuário inativado porque a senha inicial não foi alterada em até 3 dias. "
            "Solicite a reativação ao administrador."
        )

    return {
        "id": usuario["id"],
        "username": usuario["username"],
        "nome_completo": usuario["nome_completo"],
        "perfil": usuario["perfil"],
        "ativo": usuario["ativo"],
        "precisa_trocar_senha": usuario.get("precisa_trocar_senha", 0),
        "senha_alterada_em": usuario.get("senha_alterada_em"),
    }


# =========================================================
# LOGS
# =========================================================

def registrar_log_consulta(
    user_id: int,
    username: str,
    nome_completo: str,
    tipo_consulta: str,
    valor_pesquisado: str,
    quantidade_resultados: int
):
    with get_connection() as conn:
        def _run():
            conn.execute("""
                INSERT INTO log_consultas (
                    user_id,
                    username,
                    nome_completo,
                    tipo_consulta,
                    valor_pesquisado,
                    quantidade_resultados,
                    data_hora
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            """, (
                user_id,
                username,
                nome_completo,
                tipo_consulta,
                valor_pesquisado,
                quantidade_resultados
            ))

        _executar_sqlite_sem_bloquear_app(conn, "Registro de log da consulta", _run)


def recriar_tabela_log_consultas():
    with get_connection() as conn:
        configurar_pragmas(conn)
        conn.execute("DROP TABLE IF EXISTS log_consultas")
        conn.execute("""
            CREATE TABLE log_consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                nome_completo TEXT,
                tipo_consulta TEXT,
                valor_pesquisado TEXT,
                quantidade_resultados INTEGER,
                data_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_data_hora ON log_consultas (data_hora DESC)")


def mascarar_valor(tipo: str, valor: str) -> str:
    valor = str(valor or "")

    if tipo == "CPF":
        digitos = "".join(ch for ch in valor if ch.isdigit())
        if len(digitos) == 11:
            return f"{digitos[:3]}.***.***-{digitos[-2:]}"
        return "***"

    if tipo == "NB":
        digitos = "".join(ch for ch in valor if ch.isdigit())
        if len(digitos) >= 5:
            return f"{digitos[:3]}***{digitos[-2:]}"
        return "***"

    if tipo == "CODIGO_FAMILIAR":
        digitos = "".join(ch for ch in valor if ch.isdigit())
        if len(digitos) >= 4:
            return f"{digitos[:3]}***"
        return "***"

    return "***"


def listar_logs_consultas_mascarados(limit: int = 100) -> pd.DataFrame:
    with get_connection() as conn:
        df = pd.read_sql_query("""
            SELECT
                id,
                data_hora,
                nome_completo,
                username,
                tipo_consulta,
                valor_pesquisado,
                quantidade_resultados
            FROM log_consultas
            ORDER BY data_hora DESC
            LIMIT ?
        """, conn, params=(limit,))

    if not df.empty:
        df["valor_pesquisado"] = df.apply(
            lambda row: mascarar_valor(row["tipo_consulta"], row["valor_pesquisado"]),
            axis=1
        )

    return df


# =========================================================
# CONSULTAS DA BASE
# =========================================================

def _executar_consulta_df(sql: str, params=()) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _executar_consulta_um(sql: str, params=()):
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def _ordenar_resultado_consulta(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    ordenado = df.copy()
    ordenado["__ord_ref"] = pd.to_numeric(ordenado.get("NU_MES_REF"), errors="coerce")
    tipo_ordem = {
        "BENEFICIARIO_CADUNICO": 0,
        "MEMBRO_FAMILIAR": 1,
        "NAO_CADASTRADO": 2,
    }
    ordenado["__ord_tipo"] = ordenado.get("TIPO_REGISTRO", "").map(tipo_ordem).fillna(9)

    nome_pessoa = ordenado.get("NOM_PESSOA")
    nome_titular = ordenado.get("NM_TIT_BENEF_T")
    if nome_pessoa is None:
        nome_pessoa = pd.Series("", index=ordenado.index, dtype="object")
    else:
        nome_pessoa = nome_pessoa.fillna("").astype(str)
    if nome_titular is None:
        nome_titular = pd.Series("", index=ordenado.index, dtype="object")
    else:
        nome_titular = nome_titular.fillna("").astype(str)

    ordenado["__ord_nome"] = nome_pessoa.mask(
        nome_pessoa.str.strip().isin(["", "nan", "None"]),
        nome_titular,
    )

    ordenado = ordenado.sort_values(
        by=["__ord_ref", "__ord_tipo", "__ord_nome"],
        ascending=[False, True, True],
        kind="stable",
    )
    return ordenado.drop(columns=["__ord_ref", "__ord_tipo", "__ord_nome"], errors="ignore")


def buscar_pessoa_por_cpf(cpf: str) -> pd.DataFrame:
    cpf = _normalizar_documento(cpf, 11)
    sql_titular = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NU_CPF_T = ?
    """
    sql_pessoa = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NUM_CPF_PESSOA = ?
    """

    partes = []
    df_titular = _executar_consulta_df(sql_titular, (cpf,))
    if not df_titular.empty:
        partes.append(df_titular)

    df_pessoa = _executar_consulta_df(sql_pessoa, (cpf,))
    if not df_pessoa.empty:
        partes.append(df_pessoa)

    if not partes:
        return pd.DataFrame()

    resultado = pd.concat(partes, ignore_index=True).drop_duplicates()
    return _ordenar_resultado_consulta(resultado)


def _melhor_registro_consulta(registros):
    candidatos = [registro for registro in registros if registro]
    if not candidatos:
        return None

    prioridade_tipo = {
        "BENEFICIARIO_CADUNICO": 0,
        "NAO_CADASTRADO": 1,
        "MEMBRO_FAMILIAR": 2,
    }

    def chave(registro):
        try:
            referencia = int(float(registro.get("NU_MES_REF") or 0))
        except (TypeError, ValueError):
            referencia = 0

        tipo = str(registro.get("TIPO_REGISTRO") or "").strip()
        nome = str(registro.get("NOM_PESSOA") or registro.get("NM_TIT_BENEF_T") or "")
        return (-referencia, prioridade_tipo.get(tipo, 9), nome)

    return sorted(candidatos, key=chave)[0]


def buscar_registro_pessoa_por_cpf(cpf: str):
    cpf = _normalizar_documento(cpf, 11)
    if not cpf:
        return None

    sql_beneficiario_titular = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NU_CPF_T = ?
          AND TIPO_REGISTRO IN ('BENEFICIARIO_CADUNICO', 'NAO_CADASTRADO')
        ORDER BY
            NU_MES_REF DESC,
            CASE
                WHEN TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO' THEN 0
                WHEN TIPO_REGISTRO = 'NAO_CADASTRADO' THEN 1
                ELSE 2
            END,
            COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
        LIMIT 1
    """

    sql_beneficiario_pessoa = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NUM_CPF_PESSOA = ?
          AND TIPO_REGISTRO IN ('BENEFICIARIO_CADUNICO', 'NAO_CADASTRADO')
        ORDER BY
            NU_MES_REF DESC,
            CASE
                WHEN TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO' THEN 0
                WHEN TIPO_REGISTRO = 'NAO_CADASTRADO' THEN 1
                ELSE 2
            END,
            COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
        LIMIT 1
    """

    registro = _melhor_registro_consulta([
        _executar_consulta_um(sql_beneficiario_titular, (cpf,)),
        _executar_consulta_um(sql_beneficiario_pessoa, (cpf,)),
    ])
    if registro:
        return registro

    sql_titular = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NU_CPF_T = ?
        ORDER BY
            NU_MES_REF DESC,
            CASE
                WHEN TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO' THEN 0
                WHEN TIPO_REGISTRO = 'MEMBRO_FAMILIAR' THEN 1
                ELSE 2
            END,
            COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
        LIMIT 1
    """

    sql_pessoa = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NUM_CPF_PESSOA = ?
        ORDER BY
            NU_MES_REF DESC,
            CASE
                WHEN TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO' THEN 0
                WHEN TIPO_REGISTRO = 'MEMBRO_FAMILIAR' THEN 1
                ELSE 2
            END,
            COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
        LIMIT 1
    """

    return _melhor_registro_consulta([
        _executar_consulta_um(sql_titular, (cpf,)),
        _executar_consulta_um(sql_pessoa, (cpf,)),
    ])


def buscar_registro_cadunico_por_cpf(cpf: str):
    cpf = _normalizar_documento(cpf, 11)
    if not cpf:
        return None

    sql_titular = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NU_CPF_T = ?
          AND TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO'
        ORDER BY NU_MES_REF DESC, COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
        LIMIT 1
    """

    sql_pessoa = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NUM_CPF_PESSOA = ?
          AND TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO'
        ORDER BY NU_MES_REF DESC, COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
        LIMIT 1
    """

    return _melhor_registro_consulta([
        _executar_consulta_um(sql_titular, (cpf,)),
        _executar_consulta_um(sql_pessoa, (cpf,)),
    ])


def buscar_por_cpf(cpf: str) -> pd.DataFrame:
    cpf = _normalizar_documento(cpf, 11)

    sql = """
        WITH pessoa_encontrada AS (
            SELECT *
            FROM TABELA_EXEMPLO_001
            WHERE NU_CPF_T = ?
               OR NUM_CPF_PESSOA = ?
        )
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE CO_FAMILIAR_FAM IN (
            SELECT DISTINCT CO_FAMILIAR_FAM
            FROM pessoa_encontrada
            WHERE CO_FAMILIAR_FAM IS NOT NULL
        )
        OR NU_CPF_T = ?
        OR NUM_CPF_PESSOA = ?
        ORDER BY
            NU_MES_REF DESC,
            CASE
                WHEN TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO' THEN 0
                WHEN TIPO_REGISTRO = 'MEMBRO_FAMILIAR' THEN 1
                ELSE 2
            END,
            COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
    """
    return _executar_consulta_df(sql, (cpf, cpf, cpf, cpf))


def buscar_por_nb(nb: str) -> pd.DataFrame:
    nb = _normalizar_documento(nb, 10)

    sql = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NU_NB = ?
    """
    return _ordenar_resultado_consulta(_executar_consulta_df(sql, (nb,)))


def buscar_registro_por_nb(nb: str):
    nb = _normalizar_documento(nb, 10)
    if not nb:
        return None

    sql = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NU_NB = ?
        ORDER BY
            NU_MES_REF DESC,
            CASE
                WHEN TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO' THEN 0
                WHEN TIPO_REGISTRO = 'NAO_CADASTRADO' THEN 1
                WHEN TIPO_REGISTRO = 'MEMBRO_FAMILIAR' THEN 2
                ELSE 3
            END,
            COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
        LIMIT 1
    """
    return _executar_consulta_um(sql, (nb,))


def buscar_registro_cadunico_por_nb(nb: str):
    nb = _normalizar_documento(nb, 10)
    if not nb:
        return None

    sql = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE NU_NB = ?
          AND TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO'
        ORDER BY NU_MES_REF DESC, COALESCE(NOM_PESSOA, NM_TIT_BENEF_T)
        LIMIT 1
    """
    return _executar_consulta_um(sql, (nb,))


def buscar_por_codigo_familiar(codigo_familiar: str) -> pd.DataFrame:
    codigo_familiar = _normalizar_documento(codigo_familiar)

    sql = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE CO_FAMILIAR_FAM = ?
    """
    return _ordenar_resultado_consulta(_executar_consulta_df(sql, (codigo_familiar,)))


def buscar_titular_mais_recente_por_codigo_familiar(codigo_familiar: str) -> pd.DataFrame:
    codigo_familiar = _normalizar_documento(codigo_familiar)

    sql = """
        SELECT *
        FROM TABELA_EXEMPLO_001
        WHERE CO_FAMILIAR_FAM = ?
          AND TIPO_REGISTRO = 'BENEFICIARIO_CADUNICO'
    """
    resultado = _ordenar_resultado_consulta(_executar_consulta_df(sql, (codigo_familiar,)))
    if resultado.empty:
        return resultado
    return resultado.head(1)


def buscar_familia_do_nb(nb: str) -> pd.DataFrame:
    registros = buscar_por_nb(nb)
    if registros.empty:
        return registros

    for _, row in registros.iterrows():
        codigo_familiar = row.get("CO_FAMILIAR_FAM")
        if codigo_familiar not in (None, "", "nan"):
            return buscar_por_codigo_familiar(str(codigo_familiar))

    return registros


# =========================================================
# MÉTRICAS DA MAIN
# =========================================================

def carregar_metricas():
    with get_connection() as conn:
        carga = conn.execute("""
            SELECT
                competencia,
                competencia_referencia,
                nome_origem,
                data_arquivo,
                fim_carga,
                total_registros,
                qtd_bpc_pcd,
                qtd_bpc_idoso,
                qtd_auxilio_inclusao,
                qtd_rmv_total,
                qtd_zika_virus,
                total_beneficios
            FROM controle_cargas
            WHERE status = 'SUCESSO'
            ORDER BY competencia_referencia DESC, id DESC
            LIMIT 1
        """).fetchone()

    if not carga:
        return {
            "competencia": 0,
            "qtd_bpc_pcd": 0,
            "qtd_bpc_idoso": 0,
            "qtd_auxilio_inclusao": 0,
            "qtd_rmv_total": 0,
            "qtd_zika_virus": 0,
            "total_beneficios": 0,
            "total_registros": 0,
            "nome_arquivo": "Não informado",
            "data_modificacao": "Não informado",
        }

    return {
        "competencia": carga["competencia_referencia"] or carga["competencia"],
        "qtd_bpc_pcd": carga["qtd_bpc_pcd"] or 0,
        "qtd_bpc_idoso": carga["qtd_bpc_idoso"] or 0,
        "qtd_auxilio_inclusao": carga["qtd_auxilio_inclusao"] or 0,
        "qtd_rmv_total": carga["qtd_rmv_total"] or 0,
        "qtd_zika_virus": carga["qtd_zika_virus"] or 0,
        "total_beneficios": carga["total_beneficios"] or 0,
        "total_registros": carga["total_registros"] or 0,
        "nome_arquivo": carga["nome_origem"] if carga["nome_origem"] else "Carga direta do Teradata",
        "data_modificacao": carga["fim_carga"] if carga["fim_carga"] else "Não informado",
    }


# =========================================================
# APOIO
# =========================================================

def inicializar_banco():
    criar_tabela_usuarios()
    criar_tabela_log_consultas()
    criar_tabela_controle_cargas()
    criar_tabela_controle_carga_buckets()
    criar_tabela_estrutura_api()
    criar_indices()


def garantir_admin_padrao(username: str = "admin", nome_completo: str = "Administrador", senha: str = None):
    usuario = buscar_usuario_por_username(username)
    if usuario:
        return

    senha = senha or os.getenv("ADMIN_DEFAULT_PASSWORD")
    if not senha:
        raise SQLiteServiceError(
            "Defina ADMIN_DEFAULT_PASSWORD no .env para criar o administrador padrao."
        )

    criar_usuario(
        username=username,
        nome_completo=nome_completo,
        senha=senha,
        perfil="admin"
    )
