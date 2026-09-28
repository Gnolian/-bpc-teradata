import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

from app.config.env_loader import load_app_env

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE_USADO = load_app_env(BASE_DIR)

from app.services.base_loader import montar_tarefas_competencia_buckets
from app.services.teradata_service import (
    buscar_bucket_competencia_tipo,
    buscar_lote_competencia_tipo_keyset,
    contar_registros_competencia_tipo,
    erro_retentavel,
)
from app.services.sqlite_service import (
    criar_tabela_usuarios,
    criar_tabela_log_consultas,
    criar_tabela_controle_cargas,
    criar_tabela_controle_carga_buckets,
    criar_tabela_estrutura_api,
    recriar_tabela_estrutura_api,
    criar_indices,
    remover_indices_estrutura_api,
    obter_carga_sucesso,
    obter_carga_em_andamento,
    registrar_inicio_carga,
    criar_colunas_checkpoint_controle_cargas,
    registrar_fim_carga,
    atualizar_checkpoint_carga,
    excluir_competencia,
    excluir_competencia_tipo_registro,
    inserir_lote,
    calcular_metricas_competencia,
    atualizar_metricas_carga,
    contar_registros_competencia,
    contar_registros_competencia_fase,
    contar_indices_estrutura_api,
    marcar_bucket_status,
    listar_buckets_concluidos,
    listar_fases_concluidas,
    obter_ultimo_lote_sucesso,
    filtrar_registros_nao_carregados,
    checkpoint_wal,
    verificar_espaco_sqlite,
    listar_indices_consulta_ausentes,
)


def str_para_bool(valor: str, padrao: bool = False) -> bool:
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "sim", "yes", "y")


def parse_competencias():
    competencias_env = os.getenv("TD_COMPETENCIAS", "").strip()
    if competencias_env:
        return [int(c.strip()) for c in competencias_env.split(",") if c.strip()]
    return [int(os.getenv("TD_COMPETENCIA", "202601"))]


def parse_fases_forcadas():
    fases_env = os.getenv("FORCAR_FASES", "").strip()
    if not fases_env:
        return []
    return [f.strip().upper() for f in fases_env.split(",") if f.strip()]


def _fetch_tarefa(tarefa: dict):
    df = buscar_bucket_competencia_tipo(
        competencia=tarefa["competencia"],
        tipo_registro=tarefa["fase"],
        bucket=tarefa["bucket"],
        total_buckets=tarefa["total_buckets"],
        chave_sql=tarefa["chave_sql"],
    )
    return tarefa, df


def decidir_estrategia_indices(total_previsto: int, mode: str, indices_ativos: bool) -> tuple[bool, str]:
    modo = (mode or "preserve").strip().lower()

    if modo in {"true", "1", "sim", "yes", "y", "rebuild"}:
        if not str_para_bool(os.getenv("SQLITE_ALLOW_INDEX_REBUILD", "false"), False):
            return False, "rebuild-bloqueado"
        return indices_ativos, "rebuild"

    if modo in {"false", "0", "nao", "não", "no", "n", "preserve"}:
        return False, "preserve"

    if modo == "auto":
        return False, "preserve"

    threshold = int(os.getenv("SQLITE_REBUILD_INDEX_THRESHOLD_ROWS", "2000000"))
    deve_rebuild = indices_ativos and total_previsto >= threshold
    return deve_rebuild, "legacy-auto"


def _abrir_barra_progresso_fase(competencia_atual: int, fase: str, chave_sql: str, total_fase_previsto: int | None = None):
    usar_total_fase = str_para_bool(os.getenv("TD_PROGRESS_COUNT_PHASES", "true"), True)
    usar_contagem_local = str_para_bool(os.getenv("SQLITE_PROGRESS_COUNT_LOCAL", "true"), True)
    registros_preservados = (
        contar_registros_competencia_fase(competencia_atual, fase)
        if usar_contagem_local
        else 0
    )

    total_fase = total_fase_previsto
    if usar_total_fase and total_fase is None:
        try:
            total_fase = contar_registros_competencia_tipo(
                competencia=competencia_atual,
                tipo_registro=fase,
                chave_sql=chave_sql,
            )
        except Exception as exc:
            print(
                f"Nao foi possivel contar o total da fase {fase} para a barra: {exc}",
                flush=True,
            )

    if total_fase:
        inicial = min(registros_preservados, total_fase)
        return tqdm(
            total=total_fase,
            initial=inicial,
            desc=f"{competencia_atual} | {fase}",
            unit="reg",
            dynamic_ncols=True,
            bar_format=(
                "{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} {unit} "
                "[decorrido: {elapsed} | restante: {remaining} | {rate_fmt}]"
            ),
        )

    return tqdm(
        initial=registros_preservados,
        desc=f"{competencia_atual} | {fase}",
        unit="reg",
        dynamic_ncols=True,
        bar_format="{desc}: {n_fmt} {unit} [decorrido: {elapsed} | {rate_fmt}]",
    )


def processar_streaming_competencia(
    competencia_atual: int,
    carga_id: int,
    tarefas: list[dict],
    fetch_size: int,
    total_inserido: int,
):
    fases_concluidas = listar_fases_concluidas(carga_id)
    tarefas = [t for t in tarefas if t["fase"] not in fases_concluidas]

    print(
        f"Modo streaming por lotes independentes: {len(tarefas)} fase(s) pendente(s), "
        f"ate {fetch_size} registros por consulta.",
        flush=True,
    )

    if not tarefas:
        return total_inserido

    max_retries = int(os.getenv("TD_STREAM_MAX_RETRIES", os.getenv("TD_MAX_RETRIES", "4")))
    base_wait = int(os.getenv("TD_STREAM_RETRY_BASE_SECONDS", os.getenv("TD_RETRY_BASE_SECONDS", "5")))
    wal_checkpoint_lotes = int(os.getenv("SQLITE_WAL_CHECKPOINT_LOTES", "10"))
    wal_truncate_lotes = int(os.getenv("SQLITE_WAL_TRUNCATE_LOTES", "50"))
    space_check_lotes = int(os.getenv("SQLITE_SPACE_CHECK_LOTES", "5"))
    deduplicar_primeiro_resume = str_para_bool(os.getenv("SQLITE_DEDUP_FIRST_RESUME_LOTE", "false"))
    log_tempos_lote = str_para_bool(os.getenv("SQLITE_LOG_LOTE_TIMING", "true"), True)

    for tarefa in tarefas:
        fase = tarefa["fase"]
        chave_sql = tarefa["chave_sql"]
        barra_fase = _abrir_barra_progresso_fase(
            competencia_atual,
            fase,
            chave_sql,
            tarefa.get("total_registros_fase"),
        )

        try:
            for tentativa in range(1, max_retries + 1):
                try:
                    ultimo_lote = obter_ultimo_lote_sucesso(carga_id, fase)
                    lote_atual = 0
                    ultima_chave = None
                    registros_fase = 0
                    deduplicar_checkpoint_antigo = False
                    deduplicar_primeiro_lote_retomado = False

                    if ultimo_lote:
                        lote_atual = int(ultimo_lote["bucket"]) + 1
                        ultima_chave = ultimo_lote["chave_fim"]
                        deduplicar_primeiro_lote_retomado = deduplicar_primeiro_resume

                        if ultima_chave is None:
                            deduplicar_checkpoint_antigo = True
                            print(
                                f"Checkpoint antigo da fase {fase} sem chave final. "
                                "Reprocessando a fase em ordem de chave e pulando registros ja gravados.",
                                flush=True,
                            )

                        print(
                            f"Retomando fase {fase} a partir do lote {lote_atual}, "
                            f"chave > {ultima_chave}.",
                            flush=True,
                        )

                    marcar_bucket_status(
                        carga_id=carga_id,
                        competencia=competencia_atual,
                        fase=fase,
                        bucket=-2,
                        total_buckets=0,
                        status="EM_ANDAMENTO",
                        registros_bucket=0,
                    )

                    while True:
                        inicio_lote = time.perf_counter()
                        chave_inicio = ultima_chave
                        if log_tempos_lote:
                            tqdm.write(
                                f"Consultando lote: competencia {competencia_atual} | fase {fase} | "
                                f"lote {lote_atual} | chave > {ultima_chave}"
                            )
                        df, chave_fim = buscar_lote_competencia_tipo_keyset(
                            competencia=competencia_atual,
                            tipo_registro=fase,
                            chave_sql=chave_sql,
                            fetch_size=fetch_size,
                            ultima_chave=ultima_chave,
                        )
                        tempo_consulta = time.perf_counter() - inicio_lote

                        if df.empty:
                            break

                        inicio_dedup = time.perf_counter()
                        deduplicar_lote_atual = (
                            deduplicar_checkpoint_antigo
                            or deduplicar_primeiro_lote_retomado
                        )

                        df_para_inserir = (
                            filtrar_registros_nao_carregados(
                                df=df,
                                competencia=competencia_atual,
                                fase=fase,
                                chave_sql=chave_sql,
                            )
                            if deduplicar_lote_atual
                            else df
                        )
                        deduplicar_primeiro_lote_retomado = False
                        tempo_dedup = time.perf_counter() - inicio_dedup

                        inicio_insercao = time.perf_counter()
                        qtd = inserir_lote(df_para_inserir)
                        tempo_insercao = time.perf_counter() - inicio_insercao
                        total_inserido += qtd
                        registros_fase += qtd
                        if qtd:
                            barra_fase.update(qtd)
                        if chave_fim is not None:
                            ultima_chave = chave_fim

                        inicio_checkpoint = time.perf_counter()
                        marcar_bucket_status(
                            carga_id=carga_id,
                            competencia=competencia_atual,
                            fase=fase,
                            bucket=lote_atual,
                            total_buckets=0,
                            status="SUCESSO",
                            registros_bucket=qtd,
                            chave_inicio=chave_inicio,
                            chave_fim=chave_fim,
                        )

                        atualizar_checkpoint_carga(
                            carga_id=carga_id,
                            fase_atual=fase,
                            pagina_atual=lote_atual,
                            total_paginas=0,
                            registros_inseridos_parcial=total_inserido,
                            observacao=(
                                f"Carga streaming em andamento. Fase {fase}, "
                                f"lote {lote_atual}."
                            ),
                        )
                        tempo_checkpoint = time.perf_counter() - inicio_checkpoint

                        proximo_lote = lote_atual + 1
                        if space_check_lotes > 0 and proximo_lote % space_check_lotes == 0:
                            verificar_espaco_sqlite()
                        inicio_wal = time.perf_counter()
                        if wal_checkpoint_lotes > 0 and proximo_lote % wal_checkpoint_lotes == 0:
                            checkpoint_wal(truncate=False)
                        if wal_truncate_lotes > 0 and proximo_lote % wal_truncate_lotes == 0:
                            checkpoint_wal(truncate=True)
                        tempo_wal = time.perf_counter() - inicio_wal

                        mensagem_lote = (
                            f"Lote concluido: competencia {competencia_atual} | fase {fase} | "
                            f"lote {lote_atual} com {qtd} registros. "
                            f"chave fim: {chave_fim}. Total acumulado: {total_inserido}"
                        )
                        if log_tempos_lote:
                            mensagem_lote += (
                                f" | tempos: consulta {tempo_consulta:.1f}s, "
                                f"dedup {tempo_dedup:.1f}s, insercao {tempo_insercao:.1f}s, "
                                f"checkpoint {tempo_checkpoint:.1f}s, wal {tempo_wal:.1f}s"
                            )
                        tqdm.write(mensagem_lote)

                        lote_atual += 1

                    marcar_bucket_status(
                        carga_id=carga_id,
                        competencia=competencia_atual,
                        fase=fase,
                        bucket=-1,
                        total_buckets=lote_atual,
                        status="SUCESSO",
                        registros_bucket=registros_fase,
                        chave_fim=ultima_chave,
                    )

                    atualizar_checkpoint_carga(
                        carga_id=carga_id,
                        fase_atual=fase,
                        pagina_atual=lote_atual,
                        total_paginas=lote_atual,
                        registros_inseridos_parcial=total_inserido,
                        observacao=f"Fase {fase} concluida em modo streaming.",
                    )

                    tqdm.write(
                        f"Fase concluida: competencia {competencia_atual} | fase {fase} | "
                        f"{registros_fase} registros inseridos nesta execucao."
                    )
                    break

                except Exception as exc:
                    if not erro_retentavel(exc) or tentativa == max_retries:
                        raise

                    espera = base_wait * tentativa
                    tqdm.write(f"[RETRY] Fase {fase} caiu na tentativa {tentativa}/{max_retries}: {exc}")
                    tqdm.write(
                        f"Mantendo lotes ja concluidos da fase {fase}; "
                        f"nova consulta curta em {espera}s..."
                    )
                    time.sleep(espera)
        finally:
            barra_fase.close()

    return total_inserido


def processar_competencia(
    competencia_atual: int,
    origem: str,
    total_buckets: int,
    forcar_recarga: bool,
    max_workers: int,
    modo_carga: str,
    fetch_size: int,
    otimizar_insercao: bool,
    indice_mode: str,
    indices_estrutura_ativos: bool,
    fases_forcadas: list[str] | None = None,
):
    fases_forcadas = fases_forcadas or []

    print("\n==================================================", flush=True)
    print(f"Iniciando carga da competência {competencia_atual}", flush=True)
    print(f"Origem: {origem}", flush=True)
    print(f"Buckets por fase: {total_buckets}", flush=True)
    print(f"Workers paralelos: {max_workers}", flush=True)
    print(f"Modo de carga: {modo_carga}", flush=True)
    if modo_carga == "streaming":
        print(f"Tamanho do lote de leitura: {fetch_size}", flush=True)

    carga_em_andamento = obter_carga_em_andamento(competencia_atual)
    carga_existente = obter_carga_sucesso(competencia_atual)
    if (
        carga_em_andamento
        and carga_existente
        and int(carga_existente["id"]) > int(carga_em_andamento["id"])
    ):
        carga_em_andamento = None

    fase_inicial = None
    bucket_inicial = 0
    total_inserido = 0

    if carga_em_andamento and not forcar_recarga and not fases_forcadas:
        carga_id = carga_em_andamento["id"]
        fase_inicial = carga_em_andamento.get("fase_atual")
        bucket_inicial = int(carga_em_andamento.get("pagina_atual") or 0) + 1

        print(
            f"Retomando competência {competencia_atual} a partir da fase "
            f"{fase_inicial}, bucket {bucket_inicial}...",
            flush=True,
        )

        total_inserido = int(carga_em_andamento.get("registros_inseridos_parcial") or 0)
        if str_para_bool(os.getenv("SQLITE_RESUME_COUNT_LOCAL", "false")):
            print(
                "Contando registros locais para retomada "
                "(SQLITE_RESUME_COUNT_LOCAL=true)...",
                flush=True,
            )
            total_inserido = contar_registros_competencia(competencia_atual)

        print(f"Registros preservados pelo checkpoint: {total_inserido}", flush=True)
    elif forcar_recarga:
        print(f"Recarga total solicitada para a competência {competencia_atual}.", flush=True)
        carga_id = registrar_inicio_carga(
            competencia=competencia_atual,
            nome_origem=origem,
            data_arquivo=None,
            observacao="Recarga total solicitada.",
        )

        print(f"Excluindo todos os registros da competência {competencia_atual} no SQLite...", flush=True)
        excluir_competencia(competencia_atual)
        total_inserido = 0
    elif fases_forcadas:
        print(
            f"Reprocessamento parcial solicitado para a competência {competencia_atual}. "
            f"Fases: {', '.join(fases_forcadas)}",
            flush=True,
        )

        carga_id = registrar_inicio_carga(
            competencia=competencia_atual,
            nome_origem=origem,
            data_arquivo=None,
            observacao=f"Recarga parcial das fases: {', '.join(fases_forcadas)}",
        )

        for fase in fases_forcadas:
            print(
                f"Excluindo registros da competência {competencia_atual} para a fase {fase}...",
                flush=True,
            )
            excluir_competencia_tipo_registro(competencia_atual, fase)

        total_inserido = contar_registros_competencia(competencia_atual)
        print(f"Registros preservados após exclusão parcial: {total_inserido}", flush=True)
    elif carga_existente:
        print(f"Competência {competencia_atual} já carregada com sucesso. Nada a fazer.", flush=True)
        return False
    else:
        carga_id = registrar_inicio_carga(
            competencia=competencia_atual,
            nome_origem=origem,
            data_arquivo=None,
            observacao="Nova carga iniciada.",
        )

        print(
            f"Competencia {competencia_atual} sem carga anterior. "
            "Pulando exclusao no SQLite.",
            flush=True,
        )
        total_inserido = 0

    try:
        tarefas = montar_tarefas_competencia_buckets(
            competencia_atual=competencia_atual,
            total_buckets=1 if modo_carga == "streaming" else total_buckets,
            fase_inicial=fase_inicial,
            bucket_inicial=0 if modo_carga == "streaming" else bucket_inicial,
        )

        if fases_forcadas:
            tarefas = [t for t in tarefas if t["fase"] in fases_forcadas]

        total_previsto_competencia = max(
            (int(t.get("total_competencia", 0)) for t in tarefas),
            default=0,
        )
        removeu_indices_nesta_competencia = False

        if otimizar_insercao and total_previsto_competencia > 0:
            deve_rebuild_indices, estrategia_indices = decidir_estrategia_indices(
                total_previsto=total_previsto_competencia,
                mode=indice_mode,
                indices_ativos=indices_estrutura_ativos,
            )

            if deve_rebuild_indices:
                print(
                    f"Competencia {competencia_atual}: estrategia de indices = {estrategia_indices}. "
                    "Removendo indices da TABELA_EXEMPLO_001 antes da insercao...",
                    flush=True,
                )
                remover_indices_estrutura_api()
                removeu_indices_nesta_competencia = True
                indices_estrutura_ativos = False
            else:
                print(
                    f"Competencia {competencia_atual}: estrategia de indices = {estrategia_indices}. "
                    "Mantendo indices existentes durante a carga.",
                    flush=True,
                )

        if modo_carga == "streaming":
            total_inserido = processar_streaming_competencia(
                competencia_atual=competencia_atual,
                carga_id=carga_id,
                tarefas=tarefas,
                fetch_size=fetch_size,
                total_inserido=total_inserido,
            )
            tarefas = []

        concluidos = listar_buckets_concluidos(carga_id)
        tarefas = [t for t in tarefas if (t["fase"], t["bucket"]) not in concluidos]

        if fases_forcadas:
            tarefas = [t for t in tarefas if t["fase"] in fases_forcadas]

        concluidos = listar_buckets_concluidos(carga_id)
        tarefas = [t for t in tarefas if (t["fase"], t["bucket"]) not in concluidos]

        print(f"Tarefas pendentes após checkpoint: {len(tarefas)}", flush=True)

        if not tarefas:
            print("Nenhuma tarefa pendente. Indo para cálculo de métricas...", flush=True)

        total_tarefas = len(tarefas)
        buckets_processados = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futuros = {
                executor.submit(_fetch_tarefa, tarefa): tarefa
                for tarefa in tarefas
            }

            for future in tqdm(
                as_completed(futuros),
                total=len(futuros),
                desc=f"Carregando competência {competencia_atual}",
                unit="bucket",
            ):
                tarefa = futuros[future]
                fase = tarefa["fase"]
                bucket = tarefa["bucket"]

                marcar_bucket_status(
                    carga_id=carga_id,
                    competencia=competencia_atual,
                    fase=fase,
                    bucket=bucket,
                    total_buckets=tarefa["total_buckets"],
                    status="EM_ANDAMENTO",
                    registros_bucket=0,
                )

                tarefa_resultado, df = future.result()

                print(
                    f"Gravando competência {competencia_atual} | fase {fase} | "
                    f"bucket {bucket} com {len(df)} registros...",
                    flush=True,
                )

                qtd = inserir_lote(df)
                total_inserido += qtd

                marcar_bucket_status(
                    carga_id=carga_id,
                    competencia=competencia_atual,
                    fase=fase,
                    bucket=bucket,
                    total_buckets=tarefa_resultado["total_buckets"],
                    status="SUCESSO",
                    registros_bucket=qtd,
                )

                buckets_processados += 1

                if buckets_processados % 10 == 0 or buckets_processados == total_tarefas:
                    atualizar_checkpoint_carga(
                        carga_id=carga_id,
                        fase_atual=fase,
                        pagina_atual=bucket,
                        total_paginas=tarefa_resultado["total_buckets"],
                        registros_inseridos_parcial=total_inserido,
                        observacao=(
                            f"Carga em andamento. Fase {fase}, bucket "
                            f"{bucket}/{tarefa_resultado['total_buckets'] - 1}."
                        ),
                    )

                print(
                    f"Bucket concluído: competência {competencia_atual} | fase {fase} | "
                    f"bucket {bucket}. Total acumulado: {total_inserido}",
                    flush=True,
                )

        calcular_metricas = str_para_bool(os.getenv("SQLITE_CALCULATE_METRICS_ON_LOAD", "false"))
        if calcular_metricas:
            print(f"Calculando métricas da competência {competencia_atual}...", flush=True)
            metricas = calcular_metricas_competencia(competencia_atual)
            total_final = metricas["total_registros"]

            print(f"Atualizando métricas salvas da competência {competencia_atual}...", flush=True)
            atualizar_metricas_carga(
                carga_id=carga_id,
                competencia_referencia=metricas["competencia_referencia"],
                qtd_bpc_pcd=metricas["qtd_bpc_pcd"],
                qtd_bpc_idoso=metricas["qtd_bpc_idoso"],
                qtd_auxilio_inclusao=metricas["qtd_auxilio_inclusao"],
                qtd_rmv_total=metricas["qtd_rmv_total"],
                qtd_zika_virus=metricas["qtd_zika_virus"],
                total_beneficios=metricas["total_beneficios"],
                total_registros=metricas["total_registros"],
            )
        else:
            print(
                "Pulando cálculo completo de métricas da competência "
                "(SQLITE_CALCULATE_METRICS_ON_LOAD=false).",
                flush=True,
            )
            total_final = total_inserido

        registrar_fim_carga(
            carga_id=carga_id,
            total_registros=total_final,
            status="SUCESSO",
            observacao=f"Carga concluída. Inseridos {total_inserido} registros.",
        )

        try:
            checkpoint_wal(truncate=True)
        except Exception as exc:
            print(f"AVISO: nao foi possivel compactar o WAL apos a carga: {exc}", flush=True)

        print("Carga concluída com sucesso.", flush=True)
        print(f"Competência: {competencia_atual}", flush=True)
        print(f"Origem: {origem}", flush=True)
        print(f"Total inserido no processo: {total_inserido}", flush=True)
        print(f"Total gravado no SQLite: {total_final}", flush=True)
        return removeu_indices_nesta_competencia

    except Exception as e:
        try:
            registrar_fim_carga(
                carga_id=carga_id,
                total_registros=total_inserido,
                status="ERRO",
                observacao=f"Erro durante a carga: {e}",
            )
        except Exception as erro_finalizacao:
            print(
                "AVISO: nao foi possivel registrar o erro da carga no SQLite: "
                f"{erro_finalizacao}",
                flush=True,
            )
        print(f"Erro na competência {competencia_atual}: {e}", flush=True)
        raise


def main():
    if ENV_FILE_USADO:
        print(f"Arquivo de ambiente complementar: {ENV_FILE_USADO}", flush=True)

    origem = f"{os.getenv('TD_DATABASE', 'BASE_EXEMPLO_01')}.{os.getenv('TD_TABLE', 'TABELA_EXEMPLO_002')}"
    total_buckets = int(os.getenv("CHUNK_SIZE", "100"))
    max_workers = int(os.getenv("MAX_WORKERS", "3"))
    modo_carga = os.getenv("MODO_CARGA", "streaming").strip().lower()
    fetch_size = int(os.getenv("TD_FETCH_SIZE", "5000"))
    forcar_recarga = str_para_bool(os.getenv("FORCAR_RECARGA", "false"))
    recriar_estrutura = str_para_bool(os.getenv("RECRIAR_ESTRUTURA_API", "false"))
    otimizar_insercao = str_para_bool(os.getenv("OTIMIZAR_INSERCAO_SQLITE", "true"), True)
    indice_mode = os.getenv("SQLITE_REBUILD_INDEXES_ON_LOAD", "preserve").strip().lower()
    fases_forcadas = parse_fases_forcadas()

    espaco = verificar_espaco_sqlite()
    print(
        "SQLite: "
        f"{espaco['path']} | espaco livre: {espaco['free_gb']:.1f} GB "
        f"de {espaco['total_gb']:.1f} GB.",
        flush=True,
    )

    print("Inicializando estruturas locais...", flush=True)
    criar_tabela_usuarios()
    criar_tabela_log_consultas()
    criar_tabela_controle_cargas()
    criar_tabela_controle_carga_buckets()
    criar_colunas_checkpoint_controle_cargas()

    if recriar_estrutura:
        print("Recriando TABELA_EXEMPLO_001 para refletir o novo schema...", flush=True)
        recriar_tabela_estrutura_api()
    else:
        print("Garantindo exist?ncia da TABELA_EXEMPLO_001...", flush=True)
        criar_tabela_estrutura_api()

    indices_estrutura_existentes = contar_indices_estrutura_api()
    indices_consulta_ausentes = listar_indices_consulta_ausentes()
    precisa_recriar_indices_no_final = recriar_estrutura or bool(indices_consulta_ausentes)
    if indices_consulta_ausentes:
        print(
            "Indices essenciais ausentes: "
            f"{', '.join(indices_consulta_ausentes)}.",
            flush=True,
        )

    competencias = parse_competencias()
    print(f"Compet?ncias configuradas para carga: {competencias}", flush=True)
    print(f"Fases for?adas: {fases_forcadas}", flush=True)

    try:
        for competencia_atual in competencias:
            removeu_indices = processar_competencia(
                competencia_atual=competencia_atual,
                origem=origem,
                total_buckets=total_buckets,
                forcar_recarga=forcar_recarga,
                max_workers=max_workers,
                modo_carga=modo_carga,
                fetch_size=fetch_size,
                otimizar_insercao=otimizar_insercao,
                indice_mode=indice_mode,
                indices_estrutura_ativos=indices_estrutura_existentes > 0,
                fases_forcadas=fases_forcadas,
            )
            if removeu_indices:
                precisa_recriar_indices_no_final = True
                indices_estrutura_existentes = 0
    finally:
        recriar_indices_final = str_para_bool(os.getenv("SQLITE_RECREATE_INDEXES_AFTER_LOAD", "true"), True)
        if otimizar_insercao and precisa_recriar_indices_no_final and recriar_indices_final:
            print("Recriando indices do SQLite apos a carga...", flush=True)
            try:
                criar_indices()
            except Exception as exc:
                print(
                    "AVISO: a carga terminou, mas nao foi possivel recriar os indices "
                    f"automaticamente: {exc}",
                    flush=True,
                )
                print(
                    "A base permanece gravada. Libere espaco em disco e reabra a "
                    "aplicacao para recriar os indices essenciais quando necessario.",
                    flush=True,
                )
        elif otimizar_insercao and precisa_recriar_indices_no_final:
            print(
                "Indices da TABELA_EXEMPLO_001 foram removidos e nao serao recriados agora "
                "(SQLITE_RECREATE_INDEXES_AFTER_LOAD=false).",
                flush=True,
            )

    print("\nTodas as compet?ncias foram processadas.", flush=True)


if __name__ == "__main__":
    main()
