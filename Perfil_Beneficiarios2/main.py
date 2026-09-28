import os
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import teradatasql
from dotenv import load_dotenv


# =========================================================
# CONFIGURAÇÃO
# =========================================================

load_dotenv()

TD_HOST = os.getenv("TD_HOST", "")
TD_USER = os.getenv("TD_USER", "")
TD_PASSWORD = os.getenv("TD_PASSWORD", "")
TD_DATABASE = os.getenv("TD_DATABASE", "BASE_EXEMPLO_01")

TD_TABLE_PERFIL = os.getenv("TD_TABLE_PERFIL", "TABELA_EXEMPLO_061")
TD_TABLE_SOCIAL_DOM = os.getenv("TD_TABLE_SOCIAL_DOM", "TABELA_EXEMPLO_062")
TD_TABLE_MAPA_UF = os.getenv("TD_TABLE_MAPA_UF", "TABELA_EXEMPLO_060")

FULL_TABLE_NAME_PERFIL = f"{TD_DATABASE}.{TD_TABLE_PERFIL}"
FULL_TABLE_NAME_SOCIAL_DOM = f"{TD_DATABASE}.{TD_TABLE_SOCIAL_DOM}"
FULL_TABLE_NAME_MAPA_UF = f"{TD_DATABASE}.{TD_TABLE_MAPA_UF}"

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GEOJSON_PATH = ASSETS_DIR / "br_ufs.geojson"

UF_ORDER = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO"
]

UF_ORDER_WITH_NI = UF_ORDER + ["NAO INFORMADA"]


# =========================================================
# CONEXÃO
# =========================================================

def get_connection():
    td_logmech = os.getenv("TD_LOGMECH", "")

    if not TD_HOST or not TD_USER or not TD_PASSWORD:
        raise ValueError(
            "Credenciais do Teradata não configuradas no arquivo .env "
            "(TD_HOST, TD_USER, TD_PASSWORD)."
        )

    conn_args = {
        "host": TD_HOST,
        "user": TD_USER,
        "password": TD_PASSWORD,
    }

    if td_logmech:
        conn_args["logmech"] = td_logmech

    return teradatasql.connect(**conn_args)


def run_query_in_chunks(query: str, nome: str, chunk_size: int = 50000) -> pd.DataFrame:
    print(f"[INÍCIO] Executando {nome} em chunks de {chunk_size:,} linhas...".replace(",", "."))

    chunks = []
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query)

        colnames = [desc[0] for desc in cursor.description]
        total_rows = 0
        chunk_num = 0

        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break

            chunk_num += 1
            df_chunk = pd.DataFrame(rows, columns=colnames)
            chunks.append(df_chunk)

            total_rows += len(df_chunk)
            print(
                f"[{nome}] chunk {chunk_num} carregado "
                f"com {len(df_chunk):,} linhas | total acumulado: {total_rows:,}".replace(",", ".")
            )

        if not chunks:
            print(f"[FIM] {nome} sem resultados.")
            return pd.DataFrame(columns=colnames)

        df_final = pd.concat(chunks, ignore_index=True)
        print(f"[FIM] {nome} concluída. Total de linhas: {len(df_final):,}".replace(",", "."))
        return df_final

    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass

        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


# =========================================================
# CACHE LOCAL
# =========================================================

def save_parquet(df: pd.DataFrame, filename: str):
    path = OUTPUT_DIR / filename
    df.to_parquet(path, index=False)
    print(f"[OK] Parquet salvo em: {path}")


def load_parquet_if_exists(filename: str) -> pd.DataFrame | None:
    path = OUTPUT_DIR / filename
    if path.exists():
        print(f"[CACHE] Lendo arquivo local: {path}")
        return pd.read_parquet(path)
    return None


# =========================================================
# TRATAMENTO
# =========================================================

def normalize_text_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype("string")
                .fillna("OUTROS")
                .replace({"None": "OUTROS", "nan": "OUTROS", "": "OUTROS"})
                .str.strip()
            )
    return df


def normalize_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def prepare_perfil_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_text_columns(
        df,
        ["ESPECIE_BPC", "UF", "FAIXA_ETARIA", "GENERO", "RACA_COR"]
    )
    df = normalize_numeric_columns(df, ["IDADE_ANOS"])

    if "UF" in df.columns:
        df["UF"] = df["UF"].where(df["UF"].isin(UF_ORDER_WITH_NI), "NAO INFORMADA")

    return df


def prepare_social_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_text_columns(
        df,
        [
            "ALFABETIZACAO",
            "FREQUENCIA_ESCOLAR",
            "FAIXA_COMODOS_POR_PESSOA",
            "MATERIAL_PISO",
            "MATERIAL_DOMICILIO",
            "AGUA_CANALIZADA",
            "CALCAMENTO",
            "FAMILIA_INDIGENA",
        ]
    )
    df = normalize_numeric_columns(
        df,
        [
            "QTDE_PESSOAS",
            "QTD_COMODOS_DOMIC_FAM",
            "IND_COMODOS_POR_PESSOA",
            "VAL_DESP_GAS_FAM",
        ]
    )
    return df


def prepare_mapa_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    pct_cols = [
        "PCT_FEMININO",
        "PCT_FAMILIA_INDIGENA",
        "PCT_AGUA_CANALIZADA",
        "PCT_1_COMODO_OU_MAIS",
        "PCT_ALFABETIZADO",
    ]
    num_cols = ["QTD_BENEFICIARIOS"] + pct_cols

    df = normalize_numeric_columns(df, num_cols)
    df = normalize_text_columns(df, ["UF"])

    return df


def summarize_by_category(df: pd.DataFrame, column: str) -> pd.DataFrame:
    return (
        df.groupby(column, dropna=False)
        .size()
        .reset_index(name="QTD")
        .sort_values("QTD", ascending=False)
    )


# =========================================================
# EXTRAÇÃO PARTICIONADA POR UF
# =========================================================

def load_perfil_data_by_uf() -> pd.DataFrame:
    partes = []

    for uf in UF_ORDER_WITH_NI:
        parquet_name = f"perfil_{uf}.parquet"
        cached = load_parquet_if_exists(parquet_name)

        if cached is not None:
            print(f"[CACHE] PERFIL {uf} já disponível.")
            partes.append(cached)
            continue

        query = f"""
        SELECT
            NU_NB,
            ESPECIE_BPC,
            UF,
            IDADE_ANOS,
            FAIXA_ETARIA,
            GENERO,
            RACA_COR
        FROM {FULL_TABLE_NAME_PERFIL}
        WHERE UF = '{uf}'
        """

        print(f"\n[UF] Carregando PERFIL da UF {uf}...")
        df_uf = run_query_in_chunks(query, f"PERFIL_{uf}", chunk_size=50000)
        df_uf = prepare_perfil_dataframe(df_uf)
        save_parquet(df_uf, parquet_name)
        partes.append(df_uf)

    df_final = pd.concat(partes, ignore_index=True)
    print(f"[OK] PERFIL consolidado: {len(df_final):,} registros".replace(",", "."))
    return df_final


def load_social_data_by_uf() -> pd.DataFrame:
    partes = []

    for uf in UF_ORDER_WITH_NI:
        parquet_name = f"social_dom_{uf}.parquet"
        cached = load_parquet_if_exists(parquet_name)

        if cached is not None:
            print(f"[CACHE] SOCIAL_DOM {uf} já disponível.")
            partes.append(cached)
            continue

        query = f"""
        SELECT
            B.NU_NB,
            B.ALFABETIZACAO,
            B.FREQUENCIA_ESCOLAR,
            B.QTDE_PESSOAS,
            B.QTD_COMODOS_DOMIC_FAM,
            B.IND_COMODOS_POR_PESSOA,
            B.FAIXA_COMODOS_POR_PESSOA,
            B.MATERIAL_PISO,
            B.MATERIAL_DOMICILIO,
            B.AGUA_CANALIZADA,
            B.CALCAMENTO,
            B.FAMILIA_INDIGENA,
            B.VAL_DESP_GAS_FAM
        FROM {FULL_TABLE_NAME_SOCIAL_DOM} B
        INNER JOIN {FULL_TABLE_NAME_PERFIL} A
            ON A.NU_NB = B.NU_NB
        WHERE A.UF = '{uf}'
        """

        print(f"\n[UF] Carregando SOCIAL_DOM da UF {uf}...")
        df_uf = run_query_in_chunks(query, f"SOCIAL_DOM_{uf}", chunk_size=50000)
        df_uf = prepare_social_dataframe(df_uf)
        save_parquet(df_uf, parquet_name)
        partes.append(df_uf)

    df_final = pd.concat(partes, ignore_index=True)
    print(f"[OK] SOCIAL_DOM consolidado: {len(df_final):,} registros".replace(",", "."))
    return df_final


def load_mapa_data() -> pd.DataFrame:
    query = f"""
    SELECT
        UF,
        QTD_BENEFICIARIOS,
        PCT_FEMININO,
        PCT_FAMILIA_INDIGENA,
        PCT_AGUA_CANALIZADA,
        PCT_1_COMODO_OU_MAIS,
        PCT_ALFABETIZADO
    FROM {FULL_TABLE_NAME_MAPA_UF}
    """
    return run_query_in_chunks(query, "MAPA_UF", chunk_size=1000)


# =========================================================
# INSIGHTS
# =========================================================

def generate_insights(df_joined: pd.DataFrame, df_mapa: pd.DataFrame) -> pd.DataFrame:
    insights = []

    total_beneficiarios = df_joined["NU_NB"].nunique()
    pct_feminino = ((df_joined["GENERO"] == "FEMININO").mean() * 100) if len(df_joined) else 0
    idade_media = df_joined["IDADE_ANOS"].mean()
    pct_indigena = ((df_joined["FAMILIA_INDIGENA"] == "SIM").mean() * 100) if len(df_joined) else 0
    pct_agua = ((df_joined["AGUA_CANALIZADA"] == "SIM").mean() * 100) if len(df_joined) else 0
    pct_alfab = ((df_joined["ALFABETIZACAO"] == "SIM").mean() * 100) if len(df_joined) else 0

    insights.append(("Total de beneficiários", round(total_beneficiarios, 0)))
    insights.append(("Idade média", round(idade_media, 2) if pd.notna(idade_media) else None))
    insights.append(("Percentual feminino (%)", round(pct_feminino, 2)))
    insights.append(("Percentual família indígena (%)", round(pct_indigena, 2)))
    insights.append(("Percentual com água canalizada (%)", round(pct_agua, 2)))
    insights.append(("Percentual alfabetizado (%)", round(pct_alfab, 2)))

    if not df_mapa.empty:
        top_uf = df_mapa.sort_values("QTD_BENEFICIARIOS", ascending=False).iloc[0]
        insights.append(("UF com maior quantidade de beneficiários", top_uf["UF"]))
        insights.append(("Quantidade na UF líder", int(top_uf["QTD_BENEFICIARIOS"])))

    return pd.DataFrame(insights, columns=["INSIGHT", "VALOR"])


# =========================================================
# GRÁFICOS
# =========================================================

def save_plotly_figure(fig, html_path: Path, png_path: Path | None = None):
    fig.write_html(str(html_path))
    if png_path is not None:
        try:
            fig.write_image(str(png_path), scale=2)
        except Exception as e:
            print(f"[AVISO] Não foi possível salvar PNG {png_path.name}: {e}")


def plot_bar(df: pd.DataFrame, x_col: str, y_col: str, title: str):
    fig = px.bar(
        df,
        x=x_col,
        y=y_col,
        title=title,
        text=y_col,
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="",
        height=500,
    )
    fig.update_traces(textposition="outside")
    return fig


def plot_pie(df: pd.DataFrame, names_col: str, values_col: str, title: str):
    fig = px.pie(
        df,
        names=names_col,
        values=values_col,
        title=title,
    )
    fig.update_layout(height=500)
    return fig


def plot_hist_age(df: pd.DataFrame):
    fig = px.histogram(
        df,
        x="IDADE_ANOS",
        nbins=20,
        title="Distribuição de idade dos beneficiários",
    )
    fig.update_layout(
        xaxis_title="Idade",
        yaxis_title="Quantidade",
        height=500,
    )
    return fig


def load_geojson() -> dict:
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def plot_uf_map(df_uf: pd.DataFrame, value_col: str, title: str):
    geojson = load_geojson()

    fig = px.choropleth(
        df_uf,
        geojson=geojson,
        locations="UF",
        featureidkey="properties.UF_05",
        color=value_col,
        color_continuous_scale="Blues",
        hover_name="UF",
        hover_data=df_uf.columns.tolist(),
        title=title,
    )

    fig.update_geos(
        fitbounds="locations",
        visible=False,
        showcountries=False,
        showcoastlines=False,
        showland=True,
    )

    fig.update_traces(
        marker_line_width=0.8,
        marker_line_color="white",
    )

    fig.update_layout(
        height=700,
        margin={"r": 0, "t": 60, "l": 0, "b": 0},
    )

    return fig


# =========================================================
# EXPORTAÇÃO
# =========================================================

def save_excel_outputs(
    df_perfil: pd.DataFrame,
    df_social: pd.DataFrame,
    df_mapa: pd.DataFrame,
    df_joined: pd.DataFrame,
    insights_df: pd.DataFrame,
):
    output_excel = OUTPUT_DIR / "analise_bpc_completa.xlsx"

    with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
        insights_df.to_excel(writer, sheet_name="insights", index=False)
        df_perfil.head(100000).to_excel(writer, sheet_name="perfil_preview", index=False)
        df_social.head(100000).to_excel(writer, sheet_name="social_preview", index=False)
        df_mapa.to_excel(writer, sheet_name="mapa_uf", index=False)
        df_joined.head(100000).to_excel(writer, sheet_name="base_joined_preview", index=False)

        summarize_by_category(df_joined, "ESPECIE_BPC").to_excel(writer, sheet_name="resumo_especie", index=False)
        summarize_by_category(df_joined, "GENERO").to_excel(writer, sheet_name="resumo_genero", index=False)
        summarize_by_category(df_joined, "FAIXA_ETARIA").to_excel(writer, sheet_name="resumo_faixa", index=False)
        summarize_by_category(df_joined, "RACA_COR").to_excel(writer, sheet_name="resumo_raca", index=False)
        summarize_by_category(df_joined, "ALFABETIZACAO").to_excel(writer, sheet_name="resumo_alfab", index=False)
        summarize_by_category(df_joined, "AGUA_CANALIZADA").to_excel(writer, sheet_name="resumo_agua", index=False)

    print(f"[OK] Excel salvo em: {output_excel}")


# =========================================================
# MAIN
# =========================================================

def main():
    print("Iniciando carga dos dados...")

    df_perfil = load_parquet_if_exists("perfil_full.parquet")
    if df_perfil is None:
        df_perfil = load_perfil_data_by_uf()
        save_parquet(df_perfil, "perfil_full.parquet")
    else:
        df_perfil = prepare_perfil_dataframe(df_perfil)
    print(f"[OK] PERFIL disponível: {len(df_perfil):,} registros".replace(",", "."))

    df_social = load_parquet_if_exists("social_dom_full.parquet")
    if df_social is None:
        df_social = load_social_data_by_uf()
        save_parquet(df_social, "social_dom_full.parquet")
    else:
        df_social = prepare_social_dataframe(df_social)
    print(f"[OK] SOCIAL_DOM disponível: {len(df_social):,} registros".replace(",", "."))

    df_mapa = load_parquet_if_exists("mapa_uf.parquet")
    if df_mapa is None:
        df_mapa = prepare_mapa_dataframe(load_mapa_data())
        save_parquet(df_mapa, "mapa_uf.parquet")
    else:
        df_mapa = prepare_mapa_dataframe(df_mapa)
    print(f"[OK] MAPA_UF disponível: {len(df_mapa):,} linhas".replace(",", "."))

    print("[INÍCIO] Fazendo merge local entre PERFIL e SOCIAL_DOM...")
    df_joined = df_perfil.merge(df_social, on="NU_NB", how="left")
    print(f"[OK] MERGE local concluído: {len(df_joined):,} registros".replace(",", "."))

    print("Gerando insights...")
    insights_df = generate_insights(df_joined, df_mapa)
    insights_path = OUTPUT_DIR / "insights_bpc.csv"
    insights_df.to_csv(insights_path, index=False, encoding="utf-8-sig")
    print(f"[OK] Insights salvos em: {insights_path}")

    print("Gerando tabelas-resumo...")
    resumo_especie = summarize_by_category(df_joined, "ESPECIE_BPC")
    resumo_genero = summarize_by_category(df_joined, "GENERO")
    resumo_faixa = summarize_by_category(df_joined, "FAIXA_ETARIA")
    resumo_raca = summarize_by_category(df_joined, "RACA_COR")
    resumo_alfab = summarize_by_category(df_joined, "ALFABETIZACAO")
    resumo_agua = summarize_by_category(df_joined, "AGUA_CANALIZADA")
    resumo_comodos = summarize_by_category(df_joined, "FAIXA_COMODOS_POR_PESSOA")
    resumo_piso = summarize_by_category(df_joined, "MATERIAL_PISO")

    print("Gerando gráficos...")
    graficos = [
        (
            plot_pie(resumo_genero, "GENERO", "QTD", "Distribuição por gênero"),
            OUTPUT_DIR / "grafico_genero.html",
            OUTPUT_DIR / "grafico_genero.png",
        ),
        (
            plot_pie(resumo_especie, "ESPECIE_BPC", "QTD", "Distribuição por espécie"),
            OUTPUT_DIR / "grafico_especie.html",
            OUTPUT_DIR / "grafico_especie.png",
        ),
        (
            plot_bar(resumo_faixa, "FAIXA_ETARIA", "QTD", "Faixa etária"),
            OUTPUT_DIR / "grafico_faixa_etaria.html",
            OUTPUT_DIR / "grafico_faixa_etaria.png",
        ),
        (
            plot_bar(resumo_raca, "RACA_COR", "QTD", "Raça/cor"),
            OUTPUT_DIR / "grafico_raca_cor.html",
            OUTPUT_DIR / "grafico_raca_cor.png",
        ),
        (
            plot_bar(resumo_alfab, "ALFABETIZACAO", "QTD", "Alfabetização"),
            OUTPUT_DIR / "grafico_alfabetizacao.html",
            OUTPUT_DIR / "grafico_alfabetizacao.png",
        ),
        (
            plot_bar(resumo_agua, "AGUA_CANALIZADA", "QTD", "Água canalizada"),
            OUTPUT_DIR / "grafico_agua.html",
            OUTPUT_DIR / "grafico_agua.png",
        ),
        (
            plot_bar(resumo_comodos, "FAIXA_COMODOS_POR_PESSOA", "QTD", "Cômodos por pessoa"),
            OUTPUT_DIR / "grafico_comodos.html",
            OUTPUT_DIR / "grafico_comodos.png",
        ),
        (
            plot_bar(resumo_piso, "MATERIAL_PISO", "QTD", "Material do piso"),
            OUTPUT_DIR / "grafico_material_piso.html",
            OUTPUT_DIR / "grafico_material_piso.png",
        ),
        (
            plot_hist_age(df_joined),
            OUTPUT_DIR / "grafico_idade.html",
            OUTPUT_DIR / "grafico_idade.png",
        ),
    ]

    for fig, html_path, png_path in graficos:
        save_plotly_figure(fig, html_path, png_path)
        print(f"[OK] Gráfico salvo: {html_path.name}")

    print("Gerando mapa...")
    mapa_metricas = {
        "QTD_BENEFICIARIOS": "Mapa por UF - Quantidade de beneficiários",
        "PCT_FEMININO": "Mapa por UF - % Feminino",
        "PCT_FAMILIA_INDIGENA": "Mapa por UF - % Família indígena",
        "PCT_AGUA_CANALIZADA": "Mapa por UF - % Água canalizada",
        "PCT_1_COMODO_OU_MAIS": "Mapa por UF - % 1 cômodo ou mais por pessoa",
        "PCT_ALFABETIZADO": "Mapa por UF - % Alfabetizado",
    }

    for coluna, titulo in mapa_metricas.items():
        fig = plot_uf_map(df_mapa, coluna, titulo)
        html_path = OUTPUT_DIR / f"mapa_{coluna.lower()}.html"
        png_path = OUTPUT_DIR / f"mapa_{coluna.lower()}.png"
        save_plotly_figure(fig, html_path, png_path)
        print(f"[OK] Mapa salvo: {html_path.name}")

    print("Salvando bases e resumos...")
    df_mapa.to_csv(OUTPUT_DIR / "mapa_uf.csv", index=False, encoding="utf-8-sig")
    resumo_especie.to_csv(OUTPUT_DIR / "resumo_especie.csv", index=False, encoding="utf-8-sig")
    resumo_genero.to_csv(OUTPUT_DIR / "resumo_genero.csv", index=False, encoding="utf-8-sig")
    resumo_faixa.to_csv(OUTPUT_DIR / "resumo_faixa_etaria.csv", index=False, encoding="utf-8-sig")
    resumo_raca.to_csv(OUTPUT_DIR / "resumo_raca_cor.csv", index=False, encoding="utf-8-sig")
    resumo_alfab.to_csv(OUTPUT_DIR / "resumo_alfabetizacao.csv", index=False, encoding="utf-8-sig")
    resumo_agua.to_csv(OUTPUT_DIR / "resumo_agua.csv", index=False, encoding="utf-8-sig")

    save_excel_outputs(df_perfil, df_social, df_mapa, df_joined, insights_df)

    print("\nConcluído. Arquivos gerados na pasta outputs.")


if __name__ == "__main__":
    main()