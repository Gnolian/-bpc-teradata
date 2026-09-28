from app.services.sqlite_service import (
    SQLiteServiceError,
    garantir_admin_padrao,
    inicializar_banco,
)


print("Inicializando banco...")
inicializar_banco()

print("Criando admin padrao...")
try:
    garantir_admin_padrao()
except SQLiteServiceError as exc:
    print(f"Admin padrao nao criado: {exc}")

print("OK!")
