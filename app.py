import os
import pandas as pd
import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx
import plotly.express as px
import plotly.graph_objects as go
import dash_bootstrap_components as dbc

# =======================
# Configuración y colores
# =======================

# Rutas a los archivos individuales
PATH_FALLEC = os.getenv("PATH_FALLEC", "data/Fallecimientos.xlsx")
PATH_DESC   = os.getenv("PATH_DESC",   "data/Descripcion_cod_fall.xlsx")
PATH_DEPMUN = os.getenv("PATH_DEPMUN", "data/Dep_mun.xlsx")
PATH_UBI    = os.getenv("PATH_UBI",    "data/Ubi_Dep_mun.xlsx")

COLOR_BTN  = "#FBB800"
COLOR_TEXT = "#113250"
COLOR_BG1  = "#FAFBFC"
COLOR_BG2  = "#113250"

PAGE_TITLE = "Actividad 4. Aplicación web interactiva para el análisis de mortalidad en Colombia"
MESES_ES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
            "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

INTRO_SENTENCES = [
    "Esta aplicación permite explorar de forma interactiva diferentes aspectos de la mortalidad en Colombia.",
    "Utilice los filtros para acotar la visualización por año, mes, departamento, municipio, sexo y grupos de edad.",
    "Cada gráfico muestra el total dinámico de los registros visibles en pantalla.",
    "La fuente de los datos provienen del micrositio oficial del DANE 2019"
]

# ======================
# Carga de datos
# ======================
def load_data() -> pd.DataFrame:
    """Carga los 4 libros Excel individuales y arma el DataFrame final."""
    # Validaciones suaves (solo avisa si falta alguno)
    for p in [PATH_FALLEC, PATH_DESC, PATH_DEPMUN, PATH_UBI]:
        if not os.path.isfile(p):
            print(f"[WARN] No se encontró el archivo: {p}")

    # Lecturas (engine explícito para evitar el error de Pandas)
    df   = pd.read_excel(PATH_FALLEC, dtype=str, engine="openpyxl") if os.path.isfile(PATH_FALLEC) else pd.DataFrame()
    cie  = pd.read_excel(PATH_DESC,   dtype=str, engine="openpyxl") if os.path.isfile(PATH_DESC)   else pd.DataFrame()
    dane = pd.read_excel(PATH_DEPMUN, dtype=str, engine="openpyxl") if os.path.isfile(PATH_DEPMUN) else pd.DataFrame()
    geo  = pd.read_excel(PATH_UBI,    dtype=str, engine="openpyxl") if os.path.isfile(PATH_UBI)    else pd.DataFrame()

    if df.empty:
        return df

    # Tipos numéricos seguros
    for col in ["AÑO", "MES"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Mes en texto (si no existe)
    if "Mes_texto" not in df.columns and "MES" in df.columns:
        map_mes = {i + 1: MESES_ES[i] for i in range(12)}
        df["Mes_texto"] = df["MES"].map(map_mes)
    if "Mes_texto" in df.columns:
        df["Mes_texto"] = pd.Categorical(df["Mes_texto"], categories=MESES_ES, ordered=True)

    # Merge con DEPMUN (departamento y municipio)
    if not dane.empty and {"COD_DEPARTAMENTO","COD_MUNICIPIO","DEPARTAMENTO","MUNICIPIO"}.issubset(dane.columns):
        df = df.merge(
            dane[["COD_DEPARTAMENTO","COD_MUNICIPIO","DEPARTAMENTO","MUNICIPIO"]].drop_duplicates(),
            on=["COD_DEPARTAMENTO","COD_MUNICIPIO"], how="left"
        )

    # Merge con descripciones CIE (buscar la columna 'Descripcion ... cuatro')
    if not cie.empty and "COD_MUERTE" in df.columns and "COD_MUERTE" in cie.columns:
        col_desc4 = None
        for c in cie.columns:
            c_up = str(c).lower()
            if "descripcion" in c_up and "cuatro" in c_up:
                col_desc4 = c
                break
        if col_desc4:
            df = df.merge(
                cie[["COD_MUERTE", col_desc4]].rename(columns={col_desc4: "DESC_COD_MUERTE"}),
                on="COD_MUERTE", how="left"
            )

    # Coordenadas por municipio
    if not geo.empty and {"Municipio","Longitud","Latitud"}.issubset(geo.columns) and "MUNICIPIO" in df.columns:
        geo2 = geo[["Municipio","Longitud","Latitud","Departamento"]].drop_duplicates()
        df = df.merge(geo2, left_on="MUNICIPIO", right_on="Municipio", how="left", suffixes=("","_geo"))
        df["Longitud"] = pd.to_numeric(df["Longitud"], errors="coerce")
        df["Latitud"]  = pd.to_numeric(df["Latitud"], errors="coerce")

    return df

# Intento de carga al inicio, pero sin tumbar el proceso si falla.
try:
    df = load_data()
except Exception as e:
    print(f"[WARN] No se pudo cargar los Excel: {e}")
    df = pd.DataFrame()  # continúa con DF vacío para que la app arranque

# ======================
# Utilidades
# ======================
def _format_miles(n: int) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)

def _cod_x95_mask(series: pd.Series) -> pd.Series:
    cod = (series.astype(str)
                 .str.upper()
                 .str.replace(r"[^A-Z0-9]", "", regex=True)
                 .str.strip())
    permitidos = {f"X95{i}" for i in range(10)}  # X950 ... X959
    return cod.isin(permitidos)

def filter_cod_x95(df_: pd.DataFrame) -> pd.DataFrame:
    if "COD_MUERTE" not in df_.columns:
        return df_.iloc[0:0].copy()
    return df_.loc[_cod_x95_mask(df_["COD_MUERTE"])].copy()

def top_10_causas(df_):
    cols = ["COD_MUERTE","DESC_COD_MUERTE"] if "DESC_COD_MUERTE" in df_.columns else ["COD_MUERTE"]
    t = (df_.groupby(cols)
            .size()
            .reset_index(name="Total de casos")
            .sort_values("Total de casos", ascending=False)
            .head(10))
    if "COD_MUERTE" in t.columns: t = t.rename(columns={"COD_MUERTE":"Código"})
    if "DESC_COD_MUERTE" in t.columns: t = t.rename(columns={"DESC_COD_MUERTE":"Nombre"})
    return t

def homicidios_5_ciudades(df_):
    if not {"COD_MUERTE", "MUNICIPIO"}.issubset(df_.columns):
        return pd.DataFrame(columns=["MUNICIPIO","Total"])
    tmp = filter_cod_x95(df_)
    if tmp.empty:
        return pd.DataFrame(columns=["MUNICIPIO","Total"])
    return (tmp.groupby("MUNICIPIO")
                .size()
                .reset_index(name="Total")
                .sort_values("Total", ascending=False)
                .head(5))

def diez_ciudades_menor_indice(df_):
    if "MUNICIPIO" not in df_.columns:
        return pd.DataFrame(columns=["MUNICIPIO","Total"])
    by_city = df_.groupby("MUNICIPIO").size().reset_index(name="Total")
    return by_city.sort_values("Total", ascending=True).head(10)

def muertes_por_departamento_2019(df_):
    d19 = df_.loc[df_["AÑO"] == 2019] if "AÑO" in df_.columns else df_.copy()
    grp = d19.groupby("DEPARTAMENTO").agg(
        Total=("DEPARTAMENTO","size"),
        Lat=("Latitud","mean"),
        Lon=("Longitud","mean")
    ).reset_index()
    return grp

def total_por_mes(df_):
    if "Mes_texto" not in df_.columns:
        return pd.DataFrame(columns=["Mes_texto","Total"])
    t = df_.groupby("Mes_texto").size().reset_index(name="Total")
    return t.sort_values("Mes_texto")

def barras_apiladas_sexo_por_dpto(df_):
    if not {"DEPARTAMENTO","SEXO"}.issubset(df_.columns):
        return pd.DataFrame(columns=["DEPARTAMENTO","SEXO","Total"])
    return df_.groupby(["DEPARTAMENTO","SEXO"]).size().reset_index(name="Total")

def hist_por_rango_edad(df_):
    if "Rango_edad_aproximado" in df_.columns:
        t = df_[["Rango_edad_aproximado"]].copy()
        t["count"] = 1
        return t
    return pd.DataFrame(columns=["Rango_edad_aproximado","count"])

def add_total_annotation(fig, total_value):
    """Etiqueta 'Total' en esquina superior derecha de cada gráfico."""
    fig.add_annotation(
        xref="paper", yref="paper", x=0.75, y=0.99,
        xanchor="right", yanchor="top",
        text=f"<b>Total</b>: {_format_miles(int(total_value))}",
        showarrow=False, align="right",
        font=dict(size=14, color=COLOR_TEXT),
        bgcolor="rgba(255,255,255,0.80)"
    )
    return fig

# ======================
# App y layout
# ======================
external_stylesheets = [dbc.themes.FLATLY]
app = dash.Dash(
    __name__,
    title=PAGE_TITLE,
    external_stylesheets=external_stylesheets,
    suppress_callback_exceptions=True,
    serve_locally=True,
)
server = app.server

def dd(id_, options, multi=True, placeholder="Seleccionar...", value=None, keep_order=False):
    clean = [o for o in options if pd.notna(o)]
    labels = [str(o) for o in clean] if keep_order else sorted(map(str, clean))
    return dcc.Dropdown(
        id=id_,
        options=[{"label": s, "value": s} for s in labels],
        value=value,
        multi=multi,
        placeholder=placeholder,
        className="mb-2"
    )

def build_filters(df_):
    items = []
    if "AÑO" in df_.columns:
        items += [dbc.Label("Año"), dd("f-ano", df_["AÑO"].unique())]
    if "Mes_texto" in df_.columns:
        items += [dbc.Label("Mes"), dd("f-mes", df_.sort_values("Mes_texto")["Mes_texto"].unique(), keep_order=True)]
    if "DEPARTAMENTO" in df_.columns:
        items += [dbc.Label("Departamento"), dd("f-dpto", df_["DEPARTAMENTO"].unique())]
    if "MUNICIPIO" in df_.columns:
        items += [dbc.Label("Municipio"), dd("f-mun", df_["MUNICIPIO"].unique())]
    if "SEXO" in df_.columns:
        items += [dbc.Label("Sexo"), dd("f-sexo", df_["SEXO"].unique())]
    if "Estado_civil" in df_.columns:
        items += [dbc.Label("Estado civil"), dd("f-ec", df_["Estado_civil"].unique())]
    if "GRUPO_EDAD1" in df_.columns:
        items += [dbc.Label("Grupo etario"), dd("f-ge", df_["GRUPO_EDAD1"].unique())]
    if "Rango_edad_aproximado" in df_.columns:
        items += [dbc.Label("Rango de edad"), dd("f-rango", df_["Rango_edad_aproximado"].unique())]
    return items

sidebar = dbc.Offcanvas(
    id="sidebar",
    title="Filtros",
    is_open=False,
    placement="start",
    backdrop=False,
    scrollable=True,
    style={"backgroundColor": COLOR_BG1, "color": COLOR_TEXT, "width": "320px"},
    children=build_filters(df)
)

# Navbar
navbar = dbc.Navbar(
    dbc.Container([
        dbc.NavbarBrand(PAGE_TITLE, className="ms-2", style={"color": COLOR_TEXT}),
    ], fluid=True),
    color=COLOR_BG1, dark=False, className="mb-2",
    style={"borderBottom": f"2px solid {COLOR_TEXT}20"}
)

# Bloque introductorio
intro = dbc.Container(
    dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [html.P(s, className="mb-1", style={"marginBottom": "0.25rem"}) for s in INTRO_SENTENCES],
                            md=True
                        ),
                        dbc.Col(
                            dbc.ButtonGroup(
                                [
                                    dbc.Button("Filtros", id="btn-filtros", n_clicks=0,
                                               style={"backgroundColor": COLOR_BTN, "border":"none", "color":"#111"}),
                                    dbc.Button("Borrar", id="btn-clear", n_clicks=0,
                                               style={"backgroundColor": "#FFFFFF", "color": "#000000", "border":"1px solid #d1d5db"})
                                ],
                                className="justify-content-center"
                            ),
                            width="auto", align="center"
                        ),
                    ],
                    className="g-2 align-items-start"
                )
            ]
        ),
        className="mb-3", style={"backgroundColor":"#ffffff"}
    ),
    fluid=True
)

def card(title, graph_id=None, table=None):
    header = dbc.Row([dbc.Col(html.H5(title, className="mb-0"), align="center")], className="mb-2")
    body = dcc.Graph(id=graph_id, config={"displaylogo": False}) if graph_id else table
    return dbc.Card([dbc.CardBody([header, body])], style={"height":"100%"})

app.layout = dbc.Container(fluid=True, children=[
    dcc.Store(id="s-dpto-clicked"),
    dcc.Store(id="s-mun-clicked"),
    navbar,
    sidebar,
    intro,

    html.Div(
        [
            dbc.Row([
                dbc.Col(card("Mapa interactivo: Fallecidos por departamento", "g-mapa"), lg=6, md=12, className="mb-3"),
                dbc.Col(card("Fallecidos: Variación mensual", "g-linea"), lg=6, md=12, className="mb-3"),
            ], align="stretch"),

            dbc.Row([
                dbc.Col(card("Las 5 ciudades más violentas - Muerte por arma de fuego", "g-violentas"), lg=6, md=12, className="mb-3"),
                dbc.Col(card("Las 10 ciudades con menor índice de fallecidos", "g-pie"), lg=6, md=12, className="mb-3"),
            ], align="stretch"),

            dbc.Row([
                dbc.Col(card("Comparación en Departamentos: Fallecidos por sexo", "g-sexo"), lg=6, md=12, className="mb-3"),
                dbc.Col(card("Fallecidos por grupo etario", "g-hist"), lg=6, md=12, className="mb-3"),
            ], align="stretch"),

            dbc.Row(
                [
                    dbc.Col(
                        card(
                            "Causas: Top 10 causas (código, nombre, total)",
                            table=html.Div(id="tbl-top10"),
                        ),
                        lg=6, md=8, sm=12,
                        className="mb-4",
                    ),
                ],
                justify="center",
                align="stretch",
            ),
        ],
        id="content-wrapper",
        style={"transition":"margin-left 0.25s ease", "marginLeft":"0px",
               "backgroundColor": COLOR_BG1, "color": COLOR_TEXT},
    )
],
style={"backgroundColor": COLOR_BG1, "color": COLOR_TEXT}
)

# ======================
# Callbacks
# ======================
@app.callback(Output("sidebar","is_open"), Input("btn-filtros","n_clicks"), State("sidebar","is_open"))
def toggle_sidebar(n, is_open):
    if n:
        return not is_open
    return is_open

# Botón BORRAR: limpia todos los filtros y clics guardados
@app.callback(
    Output("f-ano", "value"),
    Output("f-mes", "value"),
    Output("f-dpto", "value"),
    Output("f-mun", "value"),
    Output("f-sexo", "value"),
    Output("f-ec", "value"),
    Output("f-ge", "value"),
    Output("f-rango", "value"),
    Input("btn-clear", "n_clicks"),
    prevent_initial_call=True
)
def clear_all(n_clicks):
    return None, None, None, None, None, None, None, None,

def apply_filters(df_, v_ano, v_mes, v_dpto, v_mun, v_sexo, v_ec, v_ge, v_rango, dpto_clicked, mun_clicked):
    t = df_.copy()

    def _isin(series, values):
        if not values:
            return pd.Series([True]*len(series), index=series.index)
        return series.astype(str).isin([str(v) for v in values])

    if "AÑO" in t.columns:                   t = t[_isin(t["AÑO"], v_ano)]
    if "Mes_texto" in t.columns:             t = t[_isin(t["Mes_texto"], v_mes)]
    if "DEPARTAMENTO" in t.columns:          t = t[_isin(t["DEPARTAMENTO"], v_dpto)]
    if "MUNICIPIO" in t.columns:             t = t[_isin(t["MUNICIPIO"], v_mun)]
    if "SEXO" in t.columns:                  t = t[_isin(t["SEXO"], v_sexo)]
    if "Estado_civil" in t.columns:          t = t[_isin(t["Estado_civil"], v_ec)]
    if "GRUPO_EDAD1" in t.columns:           t = t[_isin(t["GRUPO_EDAD1"], v_ge)]
    if "Rango_edad_aproximado" in t.columns: t = t[_isin(t["Rango_edad_aproximado"], v_rango)]

    if dpto_clicked and "DEPARTAMENTO" in t.columns:
        t = t[t["DEPARTAMENTO"] == dpto_clicked]
    if mun_clicked and "MUNICIPIO" in t.columns:
        mun_value = mun_clicked["mun"] if isinstance(mun_clicked, dict) else mun_clicked
        t = t[t["MUNICIPIO"] == mun_value]
    return t

@app.callback(
    Output("g-mapa","figure"),
    Output("g-linea","figure"),
    Output("g-violentas","figure"),
    Output("g-pie","figure"),
    Output("tbl-top10","children"),
    Output("g-sexo","figure"),
    Output("g-hist","figure"),
    Input("f-ano","value"),
    Input("f-mes","value"),
    Input("f-dpto","value"),
    Input("f-mun","value"),
    Input("f-sexo","value"),
    Input("f-ec","value"),
    Input("f-ge","value"),
    Input("f-rango","value"),
    Input("s-dpto-clicked","data"),
    Input("s-mun-clicked","data"),
)
def update_all(v_ano, v_mes, v_dpto, v_mun, v_sexo, v_ec, v_ge, v_rango, dpto_clicked, mun_clicked):
    fdf = apply_filters(df, v_ano, v_mes, v_dpto, v_mun, v_sexo, v_ec, v_ge, v_rango, dpto_clicked, mun_clicked)

    # --- MAPA INTERACTIVO CON BURBUJAS
    data_mapa = muertes_por_departamento_2019(fdf).dropna(subset=["Lat","Lon"])
    fig_mapa = px.scatter_mapbox(
        data_frame=data_mapa, lat="Lat", lon="Lon", size="Total", color="Total",
        hover_name="DEPARTAMENTO", zoom=3.9, height=460
    )
    fig_mapa.update_layout(
        mapbox_style="open-street-map",
        paper_bgcolor=COLOR_BG1, font_color=COLOR_TEXT,
        margin=dict(l=0,r=0,t=0,b=0)
    )
    total_mapa = int(data_mapa["Total"].sum()) if not data_mapa.empty else 0
    fig_mapa = add_total_annotation(fig_mapa, total_mapa)

    # --- GRÁFICO DE LÍNEA
    data_mes = total_por_mes(fdf)
    fig_linea = px.line(data_mes, x="Mes_texto", y="Total", height=380)
    fig_linea.update_traces(line=dict(color="#FBB800"), mode="lines+markers")

    # Etiquetas con offset dinámico
    y_vals = data_mes["Total"].astype(float).tolist() if not data_mes.empty else []
    x_vals = data_mes["Mes_texto"].tolist() if not data_mes.empty else []

    if y_vals:
        rango = max(y_vals) - min(y_vals) if len(set(y_vals)) > 1 else (y_vals[0] if y_vals[0] else 1)
    else:
        rango = 1.0

    offset = max(rango * 0.02, 1.0)
    y_text = []

    for i, y in enumerate(y_vals):
        prev_y = y_vals[i-1] if i > 0 else y_vals[i]
        next_y = y_vals[i+1] if i < len(y_vals)-1 else y_vals[i]
        tendencia = (next_y - prev_y)
        y_text.append(y + offset if tendencia >= 0 else y - offset)

    fig_linea.add_trace(go.Scatter(
        x=x_vals,
        y=y_text,
        mode="text",
        text=[f"{v:,.0f}" for v in y_vals],
        textposition="middle center",
        textfont=dict(size=12, color=COLOR_TEXT),
        hoverinfo="skip",
        showlegend=False
    ))

    fig_linea.update_layout(
        paper_bgcolor=COLOR_BG1,
        plot_bgcolor=COLOR_BG1,
        font_color=COLOR_TEXT,
        margin=dict(l=10,r=10,t=10,b=10),
        xaxis_title=None,
        yaxis=dict(showticklabels=True, showgrid=False, title=None, tickformat="~s")
    )
    total_linea = int(data_mes["Total"].sum()) if not data_mes.empty else 0
    fig_linea = add_total_annotation(fig_linea, total_linea)

    # --- BARRAS 5 CIUDADES (solo X950–X959)
    data_violentas = homicidios_5_ciudades(fdf)
    fig_violentas = px.bar(
        data_violentas, x="MUNICIPIO", y="Total", height=380,
        labels={"MUNICIPIO": "Municipio", "Total": "Total (X950–X959)"}
    )
    labels_con_punto = data_violentas["Total"].astype("int64").apply(_format_miles) if not data_violentas.empty else []
    fig_violentas.update_traces(
        marker_color="#113250",
        text=labels_con_punto,
        texttemplate="%{text}",
        textposition="outside",
        textfont=dict(size=12)
    )
    hover_text = [f"<b>{m}</b><br>Total: {lbl}" for m, lbl in zip(data_violentas.get("MUNICIPIO", []), labels_con_punto)]
    fig_violentas.update_traces(hovertext=hover_text, hovertemplate="%{hovertext}<extra></extra>")
    fig_violentas.update_layout(
        paper_bgcolor=COLOR_BG1, plot_bgcolor=COLOR_BG1, font_color=COLOR_TEXT,
        margin=dict(l=10,r=10,t=20,b=45),
        xaxis_title="Municipio",
        yaxis=dict(title=None, showticklabels=False, showgrid=False, ticks="", tickformat=""),
        uniformtext_minsize=12, uniformtext_mode="show"
    )
    total_violentas = int(data_violentas["Total"].sum()) if not data_violentas.empty else 0
    fig_violentas = add_total_annotation(fig_violentas, total_violentas)

    # --- GRÁFICO DE TORTA 10 CIUDADES
    data_pie = diez_ciudades_menor_indice(fdf)
    palette = ["#F4A259","#F5AF5D","#F6B861","#F7C165","#F8CA69",
               "#F9D36D","#FADD71","#FBE675","#FCEF79","#FDF87D"]
    fig_pie = px.pie(
        data_pie, names="MUNICIPIO", values="Total",
        color="MUNICIPIO", color_discrete_sequence=palette, height=380
    )
    fig_pie.update_traces(
        texttemplate="%{value:,.0f}",
        textposition="inside",
        hovertemplate="<b>%{label}</b><br>Fallecidos: %{value:,.0f}<extra></extra>"
    )
    fig_pie.update_layout(
        paper_bgcolor=COLOR_BG1, font_color=COLOR_TEXT,
        margin=dict(l=10,r=10,t=10,b=10), showlegend=True,
        legend_title_text="Municipio"
    )
    total_pie = int(data_pie["Total"].sum()) if not data_pie.empty else 0
    fig_pie = add_total_annotation(fig_pie, total_pie)

    # --- TABLA TOP 10 CAUSAS
    use_x95 = isinstance(mun_clicked, dict) and mun_clicked.get("source") == "violentas"
    fdf_for_top = filter_cod_x95(fdf) if use_x95 else fdf
    data_top = top_10_causas(fdf_for_top).copy()

    if data_top.empty:
        for col in ["Código", "Nombre", "Total de casos"]:
            if col not in data_top.columns:
                data_top[col] = []
    suma_top = int(data_top["Total de casos"].sum()) if not data_top.empty else 0
    total_row = {c: "—" for c in data_top.columns}
    if "Nombre" in total_row: total_row["Nombre"] = "Total"
    total_row["Total de casos"] = _format_miles(suma_top)

    data_top["__row_type"] = "DATA"
    data_top = pd.concat([data_top, pd.DataFrame([{**total_row, "__row_type":"TOTAL"}])], ignore_index=True)

    columns_dt = [{"name": c, "id": c} for c in data_top.columns if c != "__row_type"] + [{"name":"", "id":"__row_type"}]
    tbl = dash_table.DataTable(
        data=data_top.to_dict("records"),
        columns=columns_dt,
        page_size=len(data_top),
        style_header={"backgroundColor": COLOR_BG2, "color": COLOR_BG1, "fontWeight":"bold"},
        style_cell={"fontFamily":"Arial", "color": COLOR_TEXT, "backgroundColor": COLOR_BG1, "textAlign":"left"},
        style_table={"overflowX":"auto", "border":"1px solid #e5e7eb"},
        style_data_conditional=[
            {"if": {"filter_query": "{__row_type} = \"TOTAL\""}, "fontWeight": "bold"}
        ],
        style_cell_conditional=[
            {"if": {"column_id": "__row_type"}, "display": "none"}
        ]
    )

    # --- BARRAS APILADAS SEXO
    data_sexo = barras_apiladas_sexo_por_dpto(fdf)
    orden_dep = (data_sexo.groupby("DEPARTAMENTO")["Total"]
                 .sum().sort_values(ascending=False).index.tolist()) if not data_sexo.empty else []
    fig_sexo = px.bar(
        data_sexo, x="DEPARTAMENTO", y="Total", color="SEXO",
        barmode="stack", color_discrete_sequence=["#FBB800", "#113250", "#999999"],
        height=380
    )
    fig_sexo.update_xaxes(categoryorder="array", categoryarray=orden_dep,
                          tickangle=-45, automargin=True)

    for tr in fig_sexo.data:
        valores = [_format_miles(int(v)) for v in tr.y] if hasattr(tr, "y") and tr.y is not None else []
        tr.text = valores
        tr.textposition = "inside"
        tr.textfont = dict(size=11, color="white")
        tr.hovertemplate = "<b>%{x}</b><br>Sexo: " + tr.name + "<br>Total: %{y:,.0f}<extra></extra>"

    fig_sexo.update_layout(
        paper_bgcolor=COLOR_BG1, plot_bgcolor=COLOR_BG1, font_color=COLOR_TEXT,
        margin=dict(l=10,r=10,t=10,b=80),
        bargap=0.15, xaxis_title="Departamento",
        yaxis=dict(title=None, showticklabels=False, showgrid=False),
        legend=dict(title="Sexo", yanchor="top", y=0.92, xanchor="left", x=1.02,
                    bgcolor="rgba(0,0,0,0)", borderwidth=0)
    )
    total_sexo = int(data_sexo["Total"].sum()) if not data_sexo.empty else 0
    fig_sexo = add_total_annotation(fig_sexo, total_sexo)

    # --- HISTOGRAMA Rango_edad_aproximado
    data_hist_raw = hist_por_rango_edad(fdf)
    tmp = data_hist_raw.copy()
    if not tmp.empty:
        tmp["Rango_edad_aproximado"] = tmp["Rango_edad_aproximado"].fillna("Sin información")
    data_hist = (
        tmp.groupby("Rango_edad_aproximado", as_index=False)["count"]
           .sum()
           .sort_values("count", ascending=False)
    ) if not tmp.empty else pd.DataFrame(columns=["Rango_edad_aproximado","count"])

    fig_hist = px.bar(
        data_hist,
        x="Rango_edad_aproximado",
        y="count",
        height=380,
        color_discrete_sequence=["#1055C9"],
    )
    labels_con_punto_hist = data_hist["count"].astype("int64").apply(_format_miles) if not data_hist.empty else []
    fig_hist.update_traces(
        text=labels_con_punto_hist,
        texttemplate="%{text}",
        textposition="outside",
        textfont=dict(size=12, color="#1055C9"),
        hovertemplate="<b>%{x}</b><br>Total: %{text}<extra></extra>",
    )
    fig_hist.update_layout(
        paper_bgcolor=COLOR_BG1, plot_bgcolor=COLOR_BG1, font_color=COLOR_TEXT,
        margin=dict(l=10, r=10, t=10, b=80),
        xaxis_title="Rango de edad",
        yaxis=dict(title=None, showticklabels=False, showgrid=False, ticks="", tickformat=""),
        xaxis=dict(categoryorder="array", categoryarray=data_hist.get("Rango_edad_aproximado", [])),
        bargap=0.2,
    )
    total_hist = int(data_hist["count"].sum()) if not data_hist.empty else 0
    fig_hist = add_total_annotation(fig_hist, total_hist)

    return fig_mapa, fig_linea, fig_violentas, fig_pie, tbl, fig_sexo, fig_hist


# ---- Crossfilter por clics
@app.callback(
    Output("s-dpto-clicked", "data"),
    Input("g-mapa", "clickData"),
    prevent_initial_call=True,
)
def store_clicked_depto(clickData):
    if clickData and isinstance(clickData, dict) and clickData.get("points"):
        return clickData["points"][0].get("hovertext")
    return None

@app.callback(
    Output("s-mun-clicked", "data"),
    Input("g-violentas", "clickData"),
    Input("g-pie", "clickData"),
    prevent_initial_call=True
)
def store_clicked_mun(click_barras, click_pie):
    trigger = ctx.triggered_id
    cd = click_barras if trigger == "g-violentas" else click_pie
    if cd and isinstance(cd, dict) and cd.get("points"):
        val = cd["points"][0].get("label") or cd["points"][0].get("x")
        return {"mun": val, "source": "violentas" if trigger == "g-violentas" else "pie"}
    return None

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=int(os.getenv("PORT","8050")), debug=True)
