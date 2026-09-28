import sys
import types
import unittest
from unittest.mock import Mock, call, patch

try:
    import teradatasql  # noqa: F401
except ModuleNotFoundError:
    sys.modules["teradatasql"] = types.SimpleNamespace(connect=None)

from app.services import teradata_service


class TeradataConnectionRetryTest(unittest.TestCase):
    def setUp(self):
        teradata_service._CONEXAO_TERADATA_JA_REALIZADA = False
        self.env = {
            "TD_HOST": "teradata.test",
            "TD_USER": "usuario",
            "TD_PASSWORD": "senha",
            "TD_LOGMECH": "LDAP",
            "TD_AUTH_MAX_RETRIES": "3",
            "TD_AUTH_RETRY_BASE_SECONDS": "2",
        }

    def tearDown(self):
        teradata_service._CONEXAO_TERADATA_JA_REALIZADA = False

    def test_primeira_autenticacao_invalida_nao_e_repetida(self):
        erro = RuntimeError("Error 8017: credenciais invalidas")
        with (
            patch.dict("os.environ", self.env, clear=False),
            patch.object(
                teradata_service.teradatasql,
                "connect",
                side_effect=erro,
            ) as conectar,
            patch.object(teradata_service.time, "sleep") as dormir,
        ):
            with self.assertRaisesRegex(RuntimeError, "8017"):
                teradata_service._conectar_teradata_com_retry()

        conectar.assert_called_once()
        dormir.assert_not_called()

    def test_8017_intermitente_e_repetido_apos_conexao_valida(self):
        teradata_service._CONEXAO_TERADATA_JA_REALIZADA = True
        conexao = Mock()
        erro = RuntimeError("Error 8017: sessao LDAP recusada")

        with (
            patch.dict("os.environ", self.env, clear=False),
            patch.object(
                teradata_service.teradatasql,
                "connect",
                side_effect=[erro, erro, conexao],
            ) as conectar,
            patch.object(teradata_service.time, "sleep") as dormir,
        ):
            resultado = teradata_service._conectar_teradata_com_retry()

        self.assertIs(resultado, conexao)
        self.assertEqual(conectar.call_count, 3)
        self.assertEqual(dormir.call_args_list, [call(2), call(4)])

    def test_contexto_fecha_conexao(self):
        conexao = Mock()
        with patch.object(
            teradata_service,
            "_conectar_teradata_com_retry",
            return_value=conexao,
        ):
            with teradata_service.get_td_connection() as resultado:
                self.assertIs(resultado, conexao)

        conexao.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
