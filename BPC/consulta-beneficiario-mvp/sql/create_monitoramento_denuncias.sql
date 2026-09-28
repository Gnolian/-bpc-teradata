CREATE TABLE IF NOT EXISTS monitoramento_denuncias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_processo TEXT,
    numero_beneficio TEXT,
    cpf_beneficiario TEXT,
    nome_beneficiario TEXT NOT NULL,
    especie_beneficio TEXT,
    situacao_atual_consulta TEXT,
    referencia_ultima_consulta INTEGER,
    demandante_denuncia TEXT,
    orgao_demandante TEXT,
    data_recebimento_denuncia TEXT,
    data_envio_inss TEXT,
    inss_respondeu INTEGER NOT NULL DEFAULT 0 CHECK (inss_respondeu IN (0, 1)),
    data_resposta_inss TEXT,
    resposta_inss TEXT,
    situacao_encaminhamento TEXT NOT NULL DEFAULT 'Pendente de envio ao INSS',
    data_requerimento_beneficio TEXT,
    data_despacho_concessao TEXT,
    tipo_beneficio TEXT,
    deficiencia_informada TEXT,
    cid_diagnostico TEXT,
    municipio TEXT,
    uf TEXT,
    observacoes_gerais TEXT,
    usuario_responsavel TEXT,
    criado_por_user_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    status_registro TEXT NOT NULL DEFAULT 'ativo'
);

CREATE TABLE IF NOT EXISTS monitoramento_denuncias_historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitoramento_id INTEGER NOT NULL,
    referencia_consultada INTEGER,
    situacao_encontrada TEXT,
    constou_como_beneficiario INTEGER NOT NULL DEFAULT 0 CHECK (constou_como_beneficiario IN (0, 1)),
    especie TEXT,
    dados_principais TEXT,
    data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP,
    usuario_responsavel TEXT,
    observacoes TEXT,
    FOREIGN KEY (monitoramento_id) REFERENCES monitoramento_denuncias(id)
);

CREATE INDEX IF NOT EXISTS idx_monitoramento_denuncias_status
ON monitoramento_denuncias (status_registro, situacao_encaminhamento);

CREATE INDEX IF NOT EXISTS idx_monitoramento_denuncias_busca
ON monitoramento_denuncias (cpf_beneficiario, numero_beneficio, numero_processo);

CREATE INDEX IF NOT EXISTS idx_monitoramento_denuncias_referencia
ON monitoramento_denuncias (referencia_ultima_consulta);

CREATE INDEX IF NOT EXISTS idx_monitoramento_historico_caso
ON monitoramento_denuncias_historico (monitoramento_id, referencia_consultada);
