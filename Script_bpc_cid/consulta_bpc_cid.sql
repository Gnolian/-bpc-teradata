WITH MACICA_UNICA AS
(
    SELECT
        a.nu_nb,
        a.cs_diag_1 AS cid,
        a.id_orgao_pag
    FROM BASE_EXEMPLO_06.TABELA_EXEMPLO_073 a
    WHERE a.cs_pa <> 3
      AND a.cs_especie = 87
      AND a.cs_sit_benef = 0
      AND a.nu_mes_ref = {{MES_REF}}

    QUALIFY ROW_NUMBER() OVER
    (
        PARTITION BY a.nu_nb
        ORDER BY
            CASE
                WHEN a.cs_diag_1 IS NULL
                  OR TRIM(a.cs_diag_1) = ''
                THEN 1
                ELSE 0
            END,
            a.cs_diag_1,
            a.id_orgao_pag
    ) = 1
),

AGENTE_UNICO AS
(
    SELECT
        a.co_sinonimo_banc AS id_orgao_pag,
        a.co_mun_inss
    FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_059 a
    WHERE a.nu_mes_ref <= {{MES_REF}}

    QUALIFY ROW_NUMBER() OVER
    (
        PARTITION BY a.co_sinonimo_banc
        ORDER BY
            a.nu_mes_ref DESC,
            a.co_mun_inss
    ) = 1
),

ENTE_UNICO AS
(
    SELECT
        codigo_municipio_origem,
        MAX(CAST(co_ibge7 AS VARCHAR(7))) AS co_ibge7
    FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_068
    GROUP BY
        codigo_municipio_origem
),

CID_UNICO AS
(
    SELECT
        co_cid,
        MAX(ds_descricao) AS ds_descricao
    FROM BASE_EXEMPLO_08.TABELA_EXEMPLO_069
    GROUP BY
        co_cid
),

BASE AS
(
    SELECT
        m.nu_nb,

        CASE SUBSTRING(e.co_ibge7, 1, 2)
            WHEN '11' THEN 'Rondônia'
            WHEN '12' THEN 'Acre'
            WHEN '13' THEN 'Amazonas'
            WHEN '14' THEN 'Roraima'
            WHEN '15' THEN 'Pará'
            WHEN '16' THEN 'Amapá'
            WHEN '17' THEN 'Tocantins'
            WHEN '21' THEN 'Maranhão'
            WHEN '22' THEN 'Piauí'
            WHEN '23' THEN 'Ceará'
            WHEN '24' THEN 'Rio Grande do Norte'
            WHEN '25' THEN 'Paraíba'
            WHEN '26' THEN 'Pernambuco'
            WHEN '27' THEN 'Alagoas'
            WHEN '28' THEN 'Sergipe'
            WHEN '29' THEN 'Bahia'
            WHEN '31' THEN 'Minas Gerais'
            WHEN '32' THEN 'Espírito Santo'
            WHEN '33' THEN 'Rio de Janeiro'
            WHEN '35' THEN 'São Paulo'
            WHEN '41' THEN 'Paraná'
            WHEN '42' THEN 'Santa Catarina'
            WHEN '43' THEN 'Rio Grande do Sul'
            WHEN '50' THEN 'Mato Grosso do Sul'
            WHEN '51' THEN 'Mato Grosso'
            WHEN '52' THEN 'Goiás'
            WHEN '53' THEN 'Distrito Federal'
            ELSE 'UF Desconhecida'
        END AS uf,

        CASE
            WHEN c.ds_descricao IS NULL
            THEN 'Não Informado'
            ELSE m.cid
        END AS cid_ajustado,

        COALESCE(
            c.ds_descricao,
            'Não Informado'
        ) AS ds_descricao_ajustada

    FROM MACICA_UNICA m

    LEFT JOIN AGENTE_UNICO ap
        ON m.id_orgao_pag = ap.id_orgao_pag

    LEFT JOIN ENTE_UNICO e
        ON ap.co_mun_inss = e.codigo_municipio_origem

    LEFT JOIN CID_UNICO c
        ON m.cid = c.co_cid
),

BASE_FINAL AS
(
    SELECT
        b.*
    FROM BASE b

    QUALIFY ROW_NUMBER() OVER
    (
        PARTITION BY b.nu_nb
        ORDER BY
            CASE
                WHEN b.uf = 'UF Desconhecida' THEN 1
                ELSE 0
            END,

            CASE
                WHEN b.cid_ajustado = 'Não Informado' THEN 1
                ELSE 0
            END,

            b.uf,
            b.cid_ajustado,
            b.ds_descricao_ajustada
    ) = 1
)

SELECT
    uf,
    cid_ajustado,
    ds_descricao_ajustada,
    COUNT(DISTINCT nu_nb) AS bpc_pcd_cid
FROM BASE_FINAL
GROUP BY
    uf,
    cid_ajustado,
    ds_descricao_ajustada
HAVING COUNT(DISTINCT nu_nb) > 0
ORDER BY
    uf,
    cid_ajustado;