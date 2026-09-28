from app.services.teradata_service import get_td_connection


def main():
    sql = "SELECT 1 AS ok"

    try:
        with get_td_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            row = cursor.fetchone()

        print("Conexao realizada com sucesso.")
        print(f"Resultado do teste: {row[0] if row else 'sem retorno'}")
    except Exception as exc:
        print(f"Erro ao testar a conexao: {exc}")


if __name__ == "__main__":
    main()
