import streamlit as st
import plotly.express as px
import pandas as pd


SEXO_COLOR_MAP = {
    "FEMININO": "#E63946",
    "MASCULINO": "#4EA8DE",
    "NAO INFORMADO": "#1D3557",
    "IGNORADO": "#6C757D",
}


def format_int_br(value) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", ".")
    except Exception:
        return "0"


def format_pct_br(value) -> str:
    try:
        return f"{float(value):.1f}%".replace(".", ",")
    except Exception:
        return "0,0%"


def show_kpi_row(kpis: list[tuple[str, str]]):
    cols = st.columns(len(kpis))
    for col, (label, value) in zip(cols, kpis):
        col.metric(label, value)


def plot_bar(df: pd.DataFrame, x: str, y: str, title: str, horizontal: bool = False, color=None, color_map=None):
    if df.empty:
        st.warning(f"Sem dados para: {title}")
        return

    if horizontal:
        fig = px.bar(
            df,
            x=y,
            y=x,
            orientation="h",
            title=title,
            text_auto=True,
            color=color,
            color_discrete_map=color_map,
        )
    else:
        fig = px.bar(
            df,
            x=x,
            y=y,
            title=title,
            text_auto=True,
            color=color,
            color_discrete_map=color_map,
        )

    fig.update_layout(height=430)
    st.plotly_chart(fig, use_container_width=True)


def plot_pie(df: pd.DataFrame, names: str, values: str, title: str, color_map=None):
    if df.empty:
        st.warning(f"Sem dados para: {title}")
        return

    fig = px.pie(
        df,
        names=names,
        values=values,
        title=title,
        color=names,
        color_discrete_map=color_map,
    )
    fig.update_layout(height=420)
    st.plotly_chart(fig, use_container_width=True)


def plot_stacked_bar(df: pd.DataFrame, x: str, y: str, color: str, title: str, color_map=None):
    if df.empty:
        st.warning(f"Sem dados para: {title}")
        return

    fig = px.bar(
        df,
        x=x,
        y=y,
        color=color,
        barmode="stack",
        title=title,
        text_auto=True,
        color_discrete_map=color_map,
    )
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)


def plot_histogram(df: pd.DataFrame, x: str, title: str, nbins: int = 30):
    if df.empty or x not in df.columns:
        st.warning(f"Sem dados para: {title}")
        return

    fig = px.histogram(df, x=x, nbins=nbins, marginal="box", title=title)
    fig.update_layout(height=430)
    st.plotly_chart(fig, use_container_width=True)


def show_dataframe(df: pd.DataFrame, title: str = ""):
    if title:
        st.subheader(title)
    st.dataframe(df, use_container_width=True, hide_index=True)