from app.services.sqlite_service import criar_tabela_usuarios, criar_usuario, SQLiteServiceError


def main():
    criar_tabela_usuarios()

    username = input("Usuário: ").strip()
    nome = input("Nome completo: ").strip()
    senha = input("Senha: ").strip()
    perfil = input("Perfil [admin/usuario]: ").strip() or "usuario"

    try:
        criar_usuario(username, nome, senha, perfil)
        print("Usuário criado com sucesso.")
    except SQLiteServiceError as exc:
        print(f"Erro ao criar usuário: {exc}")


if __name__ == "__main__":
    main()