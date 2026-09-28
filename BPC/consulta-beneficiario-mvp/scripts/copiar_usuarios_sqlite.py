import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


COLUNAS_USUARIOS = [
    "username",
    "nome_completo",
    "senha_hash",
    "perfil",
    "ativo",
    "precisa_trocar_senha",
    "senha_alterada_em",
    "inativado_em",
    "motivo_inativacao",
    "reativado_em",
    "created_at",
]


def conectar(caminho: Path):
    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row
    return conn


def tabela_existe(conn, nome: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (nome,),
    ).fetchone()
    return row is not None


def colunas_tabela(conn, tabela: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def garantir_tabela_usuarios(conn):
    conn.execute(
        """
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
        """
    )

    colunas = colunas_tabela(conn, "usuarios")
    novas_colunas = {
        "precisa_trocar_senha": "INTEGER NOT NULL DEFAULT 0",
        "senha_alterada_em": "TEXT",
        "inativado_em": "TEXT",
        "motivo_inativacao": "TEXT",
        "reativado_em": "TEXT",
    }
    for coluna, definicao in novas_colunas.items():
        if coluna not in colunas:
            conn.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} {definicao}")


def ler_usuarios(conn):
    if not tabela_existe(conn, "usuarios"):
        raise RuntimeError("A base de origem nao possui tabela usuarios.")

    colunas_origem = colunas_tabela(conn, "usuarios")
    colunas_select = [col for col in COLUNAS_USUARIOS if col in colunas_origem]
    rows = conn.execute(
        f"SELECT {', '.join(colunas_select)} FROM usuarios ORDER BY username"
    ).fetchall()

    usuarios = []
    for row in rows:
        usuario = {col: row[col] if col in row.keys() else None for col in COLUNAS_USUARIOS}
        usuario["ativo"] = 1 if usuario["ativo"] is None else int(usuario["ativo"])
        usuario["precisa_trocar_senha"] = (
            0
            if usuario["precisa_trocar_senha"] is None
            else int(usuario["precisa_trocar_senha"])
        )
        usuario["perfil"] = usuario["perfil"] or "usuario"
        usuarios.append(usuario)

    return usuarios


def backup_destino(destino: Path) -> Path:
    sufixo = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = destino.with_suffix(destino.suffix + f".usuarios_backup_{sufixo}.json")

    with conectar(destino) as conn:
        if tabela_existe(conn, "usuarios"):
            rows = conn.execute("SELECT * FROM usuarios ORDER BY username").fetchall()
            conteudo = [dict(row) for row in rows]
        else:
            conteudo = []

    backup.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup


def copiar_usuarios(origem: Path, destino: Path, sobrescrever: bool, sem_backup: bool):
    if not origem.exists():
        raise FileNotFoundError(f"Base de origem nao encontrada: {origem}")
    if not destino.exists():
        raise FileNotFoundError(f"Base de destino nao encontrada: {destino}")

    backup = None if sem_backup else backup_destino(destino)

    with conectar(origem) as conn_origem, conectar(destino) as conn_destino:
        garantir_tabela_usuarios(conn_destino)
        usuarios = ler_usuarios(conn_origem)

        inseridos = 0
        atualizados = 0
        ignorados = 0

        for usuario in usuarios:
            existente = conn_destino.execute(
                "SELECT id FROM usuarios WHERE username = ?",
                (usuario["username"],),
            ).fetchone()

            valores = tuple(usuario[col] for col in COLUNAS_USUARIOS)

            if existente and not sobrescrever:
                ignorados += 1
                continue

            if existente and sobrescrever:
                conn_destino.execute(
                    """
                    UPDATE usuarios
                       SET nome_completo = ?,
                           senha_hash = ?,
                           perfil = ?,
                           ativo = ?,
                           precisa_trocar_senha = ?,
                           senha_alterada_em = ?,
                           inativado_em = ?,
                           motivo_inativacao = ?,
                           reativado_em = ?
                     WHERE username = ?
                    """,
                    (
                        usuario["nome_completo"],
                        usuario["senha_hash"],
                        usuario["perfil"],
                        usuario["ativo"],
                        usuario["precisa_trocar_senha"],
                        usuario["senha_alterada_em"],
                        usuario["inativado_em"],
                        usuario["motivo_inativacao"],
                        usuario["reativado_em"],
                        usuario["username"],
                    ),
                )
                atualizados += 1
                continue

            conn_destino.execute(
                f"""
                INSERT INTO usuarios ({', '.join(COLUNAS_USUARIOS)})
                VALUES ({', '.join(['?'] * len(COLUNAS_USUARIOS))})
                """,
                valores,
            )
            inseridos += 1

        conn_destino.commit()

    print("Migracao de usuarios concluida.")
    if backup:
        print(f"Backup criado: {backup}")
    print(f"Usuarios lidos na origem: {len(usuarios)}")
    print(f"Inseridos na principal: {inseridos}")
    print(f"Atualizados na principal: {atualizados}")
    print(f"Ignorados por ja existirem: {ignorados}")


def main():
    parser = argparse.ArgumentParser(
        description="Copia usuarios de uma base SQLite do SCB para outra."
    )
    parser.add_argument("--origem", required=True, help="SQLite da copia com usuarios cadastrados.")
    parser.add_argument("--destino", required=True, help="SQLite principal que recebera usuarios.")
    parser.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Atualiza usuarios existentes na principal com os dados da copia.",
    )
    parser.add_argument(
        "--sem-backup",
        action="store_true",
        help="Nao cria backup da base de destino antes da migracao.",
    )
    args = parser.parse_args()

    copiar_usuarios(
        origem=Path(args.origem).expanduser(),
        destino=Path(args.destino).expanduser(),
        sobrescrever=args.sobrescrever,
        sem_backup=args.sem_backup,
    )


if __name__ == "__main__":
    main()
