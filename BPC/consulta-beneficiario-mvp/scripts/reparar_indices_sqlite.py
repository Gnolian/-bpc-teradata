import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path


INDICES_REPARO = (
    {
        "nome": "idx_estrutura_nb",
        "coluna": "NU_NB",
        "sql": "CREATE INDEX idx_estrutura_nb ON TABELA_EXEMPLO_001 (NU_NB)",
    },
    {
        "nome": "idx_estrutura_cpf_titular",
        "coluna": "NU_CPF_T",
        "sql": "CREATE INDEX idx_estrutura_cpf_titular ON TABELA_EXEMPLO_001 (NU_CPF_T)",
    },
    {
        "nome": "idx_estrutura_cpf_pessoa",
        "coluna": "NUM_CPF_PESSOA",
        "sql": "CREATE INDEX idx_estrutura_cpf_pessoa ON TABELA_EXEMPLO_001 (NUM_CPF_PESSOA)",
    },
)


def formatar_duracao(segundos):
    total = max(0, int(segundos))
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos:02d}min {segundos:02d}s"
    if minutos:
        return f"{minutos}min {segundos:02d}s"
    return f"{segundos}s"


class Registrador:
    def __init__(self, caminho):
        self.caminho = caminho
        caminho.parent.mkdir(parents=True, exist_ok=True)

    def escrever(self, mensagem):
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        linha = f"[{agora}] {mensagem}"
        print(linha, flush=True)
        with self.caminho.open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")
            arquivo.flush()


def argumentos():
    parser = argparse.ArgumentParser(
        description=(
            "Remove do catalogo e reconstroi, com seguranca e retomada, "
            "os tres indices de consulta comprovadamente corrompidos."
        )
    )
    parser.add_argument("--db", required=True, help="Banco SQLite principal a reparar.")
    parser.add_argument(
        "--backup",
        required=True,
        help="Copia fisica de seguranca criada antes do reparo.",
    )
    parser.add_argument(
        "--temp-dir",
        help="Diretorio para arquivos temporarios da ordenacao dos indices.",
    )
    parser.add_argument(
        "--log",
        help="Arquivo de log. Padrao: ao lado do banco principal.",
    )
    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=100.0,
        help="Espaco livre minimo exigido no disco do banco (padrao: 100 GB).",
    )
    parser.add_argument(
        "--progress-seconds",
        type=int,
        default=60,
        help="Intervalo entre mensagens de atividade (padrao: 60 segundos).",
    )
    parser.add_argument(
        "--confirmar-reparo-principal",
        action="store_true",
        help="Confirmacao obrigatoria para alterar o banco indicado em --db.",
    )
    parser.add_argument(
        "--somente-preparar",
        action="store_true",
        help=(
            "Remove os indices corrompidos do catalogo e encerra. "
            "Use antes de uma carga; depois, repita sem esta opcao para reconstruir."
        ),
    )
    return parser.parse_args()


def validar_arquivos(args):
    banco = Path(args.db).expanduser().resolve()
    backup = Path(args.backup).expanduser().resolve()

    if not args.confirmar_reparo_principal:
        raise RuntimeError(
            "Inclua --confirmar-reparo-principal depois de conferir os caminhos."
        )
    if not banco.is_file():
        raise FileNotFoundError(f"Banco principal nao encontrado: {banco}")
    if not backup.is_file():
        raise FileNotFoundError(f"Backup nao encontrado: {backup}")
    if banco == backup:
        raise RuntimeError("O banco principal e o backup nao podem ser o mesmo arquivo.")
    if banco.stat().st_size <= 0 or backup.stat().st_size <= 0:
        raise RuntimeError("O banco principal e o backup precisam ter conteudo.")

    proporcao = backup.stat().st_size / banco.stat().st_size
    if not 0.90 <= proporcao <= 1.10:
        raise RuntimeError(
            "O tamanho do backup difere mais de 10% do banco principal. "
            "Confirme se os caminhos estao corretos."
        )

    livre = shutil.disk_usage(banco.parent).free / (1024 ** 3)
    if livre < args.min_free_gb:
        raise RuntimeError(
            f"Espaco livre insuficiente: {livre:.1f} GB. "
            f"Minimo exigido: {args.min_free_gb:.1f} GB."
        )

    temp_dir = None
    if args.temp_dir:
        temp_dir = Path(args.temp_dir).expanduser().resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)
        os.environ["TEMP"] = str(temp_dir)
        os.environ["TMP"] = str(temp_dir)

    log = (
        Path(args.log).expanduser().resolve()
        if args.log
        else banco.with_suffix(banco.suffix + ".reparo_indices.log")
    )
    return banco, backup, temp_dir, log, livre


def abrir_banco(banco):
    conn = sqlite3.connect(str(banco), timeout=600)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=600000")
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA temp_store=FILE")
    conn.execute("PRAGMA mmap_size=536870912")
    conn.execute("PRAGMA cache_size=-524288")
    conn.execute("PRAGMA threads=4")
    conn.execute("PRAGMA locking_mode=EXCLUSIVE")
    return conn


def garantir_exclusividade(conn):
    conn.execute("BEGIN EXCLUSIVE")
    conn.rollback()


def garantir_controle(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _scb_reparo_indices (
            nome_indice TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            detalhe TEXT
        )
        """
    )
    conn.commit()


def colunas_estrutura(conn):
    return {
        row["name"]
        for row in conn.execute("PRAGMA table_info(TABELA_EXEMPLO_001)").fetchall()
    }


def estado_indice(conn, nome):
    row = conn.execute(
        "SELECT status FROM _scb_reparo_indices WHERE nome_indice = ?",
        (nome,),
    ).fetchone()
    return row["status"] if row else None


def indice_catalogado(conn, nome):
    return conn.execute(
        "SELECT rootpage FROM sqlite_schema WHERE type = 'index' AND name = ?",
        (nome,),
    ).fetchone()


def atualizar_estado(conn, nome, status, detalhe=""):
    conn.execute(
        """
        INSERT INTO _scb_reparo_indices (nome_indice, status, atualizado_em, detalhe)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(nome_indice) DO UPDATE SET
            status = excluded.status,
            atualizado_em = excluded.atualizado_em,
            detalhe = excluded.detalhe
        """,
        (nome, status, datetime.now().isoformat(timespec="seconds"), detalhe),
    )


def remover_catalogo_corrompido(conn, nome, registrador):
    catalogado = indice_catalogado(conn, nome)
    status = estado_indice(conn, nome)

    if status == "CONCLUIDO" and catalogado:
        registrador.escrever(f"{nome}: ja reconstruido. Pulando limpeza.")
        return
    if not catalogado:
        atualizar_estado(conn, nome, "CATALOGO_LIMPO")
        conn.commit()
        registrador.escrever(f"{nome}: nao esta no catalogo; pronto para reconstruir.")
        return

    rootpage = int(catalogado["rootpage"])
    registrador.escrever(
        f"{nome}: removendo apenas o registro corrompido do catalogo "
        f"(rootpage {rootpage})."
    )
    schema_version = conn.execute("PRAGMA schema_version").fetchone()[0]
    conn.execute("PRAGMA writable_schema=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM sqlite_schema WHERE type = 'index' AND name = ?",
            (nome,),
        )
        atualizar_estado(
            conn,
            nome,
            "CATALOGO_LIMPO",
            json.dumps({"rootpage_removida": rootpage}),
        )
        conn.execute(f"PRAGMA schema_version={int(schema_version) + 1}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA writable_schema=OFF")
    registrador.escrever(f"{nome}: registro corrompido removido do catalogo.")


def reconstruir_indice(conn, indice, etapa, total, intervalo, registrador):
    nome = indice["nome"]
    catalogado = indice_catalogado(conn, nome)
    status = estado_indice(conn, nome)
    if status == "CONCLUIDO" and catalogado:
        registrador.escrever(f"[INDICE {etapa}/{total}] {nome} ja concluido. Pulando.")
        return

    if catalogado:
        raise RuntimeError(
            f"{nome} reapareceu no catalogo sem checkpoint CONCLUIDO. "
            "Interrompa e preserve o log para analise."
        )

    inicio = time.perf_counter()
    ultimo = {"tempo": inicio}

    def progresso():
        agora = time.perf_counter()
        if agora - ultimo["tempo"] >= intervalo:
            registrador.escrever(
                f"[INDICE {etapa}/{total}] {nome} em construcao | "
                f"decorrido: {formatar_duracao(agora - inicio)}"
            )
            ultimo["tempo"] = agora
        return 0

    registrador.escrever(f"[INDICE {etapa}/{total}] Iniciando {nome}.")
    conn.set_progress_handler(progresso, 50000)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(indice["sql"])
        atualizar_estado(conn, nome, "CONCLUIDO")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.set_progress_handler(None, 0)

    registrador.escrever(
        f"[INDICE {etapa}/{total}] {nome} concluido em "
        f"{formatar_duracao(time.perf_counter() - inicio)}."
    )


def validar_indices_reconstruidos(conn):
    for indice in INDICES_REPARO:
        nome = indice["nome"]
        coluna = indice["coluna"]
        plano = conn.execute(
            f"EXPLAIN QUERY PLAN SELECT {coluna} FROM TABELA_EXEMPLO_001 "
            f"INDEXED BY {nome} WHERE {coluna} IS NOT NULL LIMIT 1"
        ).fetchall()
        if not any(nome in str(item) for row in plano for item in row):
            raise RuntimeError(f"O SQLite nao selecionou o indice reconstruido {nome}.")

        conn.execute(
            f"SELECT {coluna} FROM TABELA_EXEMPLO_001 "
            f"INDEXED BY {nome} WHERE {coluna} IS NOT NULL LIMIT 1"
        ).fetchone()


def main():
    args = argumentos()
    banco, backup, temp_dir, log, livre = validar_arquivos(args)
    registrador = Registrador(log)

    registrador.escrever("=" * 72)
    registrador.escrever(f"Banco principal: {banco}")
    registrador.escrever(f"Backup preservado: {backup}")
    registrador.escrever(f"Espaco livre no disco do banco: {livre:.1f} GB")
    registrador.escrever(f"Diretorio temporario: {temp_dir or 'padrao do Windows'}")
    registrador.escrever("Modo seguro: journal DELETE, synchronous FULL, lock EXCLUSIVE")

    conn = abrir_banco(banco)
    try:
        garantir_exclusividade(conn)
        garantir_controle(conn)

        tabela = conn.execute(
            "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'TABELA_EXEMPLO_001'"
        ).fetchone()
        if not tabela:
            raise RuntimeError("A tabela TABELA_EXEMPLO_001 nao foi encontrada.")

        colunas = colunas_estrutura(conn)
        ausentes = sorted(
            indice["coluna"]
            for indice in INDICES_REPARO
            if indice["coluna"] not in colunas
        )
        if ausentes:
            raise RuntimeError(f"Colunas obrigatorias ausentes: {', '.join(ausentes)}")

        registrador.escrever("Preparando catalogo dos tres indices comprovadamente corrompidos.")
        for indice in INDICES_REPARO:
            remover_catalogo_corrompido(conn, indice["nome"], registrador)

        if args.somente_preparar:
            registrador.escrever(
                "PREPARACAO CONCLUIDA: os tres indices corrompidos foram retirados "
                "do catalogo. A carga pode ser executada agora."
            )
            registrador.escrever(
                "Depois da carga, execute este reparo novamente sem "
                "--somente-preparar para reconstruir os indices."
            )
            return

        registrador.escrever(
            "Catalogo preparado. Fechando e reabrindo o SQLite para limpar "
            "o cache interno do schema."
        )
        conn.close()
        conn = abrir_banco(banco)
        garantir_exclusividade(conn)
        garantir_controle(conn)

        registrador.escrever("Iniciando reconstrucoes isoladas.")
        total = len(INDICES_REPARO)
        intervalo = max(10, int(args.progress_seconds))
        for etapa, indice in enumerate(INDICES_REPARO, start=1):
            reconstruir_indice(conn, indice, etapa, total, intervalo, registrador)

        presentes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index'"
            ).fetchall()
        }
        faltantes = [
            indice["nome"]
            for indice in INDICES_REPARO
            if indice["nome"] not in presentes
        ]
        if faltantes:
            raise RuntimeError(
                "Reparo terminou com indices ausentes: " + ", ".join(faltantes)
            )

        registrador.escrever("Validando o uso dos tres indices reconstruidos.")
        validar_indices_reconstruidos(conn)

        registrador.escrever("REPARO CONCLUIDO: os tres indices estao presentes.")
        registrador.escrever(
            "O banco pode voltar a ser usado. Preserve o backup ate a validacao funcional."
        )
    except KeyboardInterrupt:
        registrador.escrever(
            "Interrupcao solicitada. A transacao do indice atual sera revertida; "
            "execute o mesmo comando para retomar."
        )
        raise
    except Exception as exc:
        registrador.escrever(f"ERRO: {type(exc).__name__}: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)
