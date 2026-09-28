import sqlite3
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

try:
    import teradatasql  # noqa: F401
except ModuleNotFoundError:
    sys.modules["teradatasql"] = types.SimpleNamespace(connect=None)

from scripts import carregar_macica_direto_sqlite


class CarregarMacicaDiretoSQLiteTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE controle_cargas (
                id INTEGER PRIMARY KEY,
                competencia INTEGER,
                nome_origem TEXT,
                status TEXT,
                total_registros INTEGER,
                observacao TEXT
            );
            CREATE TABLE TABELA_EXEMPLO_001 (
                NU_NB TEXT,
                NU_MES_REF INTEGER,
                TIPO_REGISTRO TEXT,
                FLAG_CADUNICO TEXT,
                SITUACAO_CAD_UNICO TEXT
            );
            """
        )

        @contextmanager
        def conexao_teste():
            yield self.conn

        self.get_connection_patch = patch.object(
            carregar_macica_direto_sqlite,
            "get_connection",
            conexao_teste,
        )
        self.get_connection_patch.start()

    def tearDown(self):
        self.get_connection_patch.stop()
        self.conn.close()

    def test_obtem_checkpoint_da_ultima_carga_macica(self):
        self.conn.executemany(
            "INSERT INTO controle_cargas VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 202608, "BASE_EXEMPLO_06.TABELA_EXEMPLO_073", "ERRO", 10, "antiga"),
                (2, 202608, "BASE_EXEMPLO_06.TABELA_EXEMPLO_073", "EM_ANDAMENTO", 20, "atual"),
            ],
        )

        carga = carregar_macica_direto_sqlite.obter_ultima_carga_macica(202608)

        self.assertEqual(carga["id"], 2)
        self.assertEqual(carga["status"], "EM_ANDAMENTO")

    def test_progresso_considera_somente_macica_provisoria_da_referencia(self):
        self.conn.executemany(
            "INSERT INTO TABELA_EXEMPLO_001 VALUES (?, ?, ?, ?, ?)",
            [
                ("100", 202608, "NAO_CADASTRADO", "PENDENTE_CADUNICO", None),
                ("300", 202608, "NAO_CADASTRADO", None, "MACICA_PROVISORIA_CADUNICO_PENDENTE"),
                ("900", 202607, "NAO_CADASTRADO", "PENDENTE_CADUNICO", None),
                ("950", 202608, "BENEFICIARIO_CADUNICO", None, None),
            ],
        )

        total, ultima_chave = (
            carregar_macica_direto_sqlite.obter_progresso_local(202608)
        )

        self.assertEqual(total, 2)
        self.assertEqual(ultima_chave, 300)

    def test_mes_anterior_trata_virada_de_ano(self):
        self.assertEqual(carregar_macica_direto_sqlite.mes_anterior(202601), 202512)
        self.assertEqual(carregar_macica_direto_sqlite.mes_anterior(202608), 202607)


if __name__ == "__main__":
    unittest.main()
