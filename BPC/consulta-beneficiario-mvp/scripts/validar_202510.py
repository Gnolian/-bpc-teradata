from app.services.sqlite_service import get_connection

COMPETENCIA = 202409

with get_connection() as conn:
    print("\n=== CONTROLE_CARGAS ===")
    rows = conn.execute("""
        SELECT id, competencia, status, observacao, fase_atual, pagina_atual, total_paginas,
               registros_inseridos_parcial, inicio_carga, fim_carga
        FROM controle_cargas
        WHERE competencia = ?
        ORDER BY id DESC
    """, (COMPETENCIA,)).fetchall()

    for row in rows:
        print(dict(row))

    print("\n=== BUCKETS POR FASE / STATUS ===")
    rows = conn.execute("""
        SELECT fase, status, COUNT(*) as qtd, SUM(registros_bucket) as total_registros
        FROM controle_carga_buckets
        WHERE competencia = ?
        GROUP BY fase, status
        ORDER BY fase, status
    """, (COMPETENCIA,)).fetchall()

    for row in rows:
        print(dict(row))