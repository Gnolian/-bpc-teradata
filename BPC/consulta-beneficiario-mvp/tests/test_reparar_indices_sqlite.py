import sqlite3
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.reparar_indices_sqlite import (
    INDICES_REPARO,
    Registrador,
    atualizar_estado,
    garantir_controle,
    indice_catalogado,
    main,
    reconstruir_indice,
    remover_catalogo_corrompido,
    validar_indices_reconstruidos,
)


class RepararIndicesSQLiteTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.db = self.base / "principal.db"
        self.log = self.base / "reparo.log"

        conn = sqlite3.connect(self.db)
        conn.execute(
            """
            CREATE TABLE TABELA_EXEMPLO_001 (
                NU_NB INTEGER,
                NU_CPF_T TEXT,
                NUM_CPF_PESSOA TEXT,
                OUTRO TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO TABELA_EXEMPLO_001 VALUES (?, ?, ?, ?)",
            ((i, str(i), str(i + 1), "x") for i in range(1000)),
        )
        for indice in INDICES_REPARO:
            conn.execute(indice["sql"])
        conn.commit()
        conn.close()
        self.backup = self.base / "backup.db"
        shutil.copy2(self.db, self.backup)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_limpa_reconstroi_e_retoma_indices(self):
        registrador = Registrador(self.log)
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        garantir_controle(conn)

        for indice in INDICES_REPARO:
            remover_catalogo_corrompido(conn, indice["nome"], registrador)
            self.assertIsNone(indice_catalogado(conn, indice["nome"]))

        conn.close()
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        garantir_controle(conn)

        for etapa, indice in enumerate(INDICES_REPARO, start=1):
            reconstruir_indice(
                conn,
                indice,
                etapa,
                len(INDICES_REPARO),
                10,
                registrador,
            )
            self.assertIsNotNone(indice_catalogado(conn, indice["nome"]))

        # Uma nova execucao deve preservar todos os indices ja concluidos.
        for etapa, indice in enumerate(INDICES_REPARO, start=1):
            reconstruir_indice(
                conn,
                indice,
                etapa,
                len(INDICES_REPARO),
                10,
                registrador,
            )

        estados = dict(
            conn.execute(
                "SELECT nome_indice, status FROM _scb_reparo_indices"
            ).fetchall()
        )
        self.assertEqual(
            estados,
            {indice["nome"]: "CONCLUIDO" for indice in INDICES_REPARO},
        )
        self.assertEqual(
            conn.execute("PRAGMA integrity_check('TABELA_EXEMPLO_001')").fetchone()[0],
            "ok",
        )
        validar_indices_reconstruidos(conn)
        conn.close()

    def test_checkpoint_e_indice_sao_confirmados_na_mesma_transacao(self):
        registrador = Registrador(self.log)
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        garantir_controle(conn)

        indice = INDICES_REPARO[0]
        remover_catalogo_corrompido(conn, indice["nome"], registrador)

        conn.close()
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        garantir_controle(conn)

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(indice["sql"])
        atualizar_estado(conn, indice["nome"], "CONCLUIDO")
        conn.rollback()

        self.assertIsNone(indice_catalogado(conn, indice["nome"]))
        estado = conn.execute(
            "SELECT status FROM _scb_reparo_indices WHERE nome_indice = ?",
            (indice["nome"],),
        ).fetchone()
        self.assertEqual(estado["status"], "CATALOGO_LIMPO")
        conn.close()

    def test_modo_preparar_para_carga_e_retomar_reparo(self):
        argumentos_base = [
            "reparar_indices_sqlite.py",
            "--db",
            str(self.db),
            "--backup",
            str(self.backup),
            "--log",
            str(self.log),
            "--min-free-gb",
            "0",
            "--confirmar-reparo-principal",
        ]

        with patch.object(sys, "argv", argumentos_base + ["--somente-preparar"]):
            main()

        conn = sqlite3.connect(self.db)
        nomes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index'"
            ).fetchall()
        }
        self.assertTrue(
            all(indice["nome"] not in nomes for indice in INDICES_REPARO)
        )
        conn.close()

        with patch.object(sys, "argv", argumentos_base):
            main()

        conn = sqlite3.connect(self.db)
        nomes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index'"
            ).fetchall()
        }
        self.assertTrue(
            all(indice["nome"] in nomes for indice in INDICES_REPARO)
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
