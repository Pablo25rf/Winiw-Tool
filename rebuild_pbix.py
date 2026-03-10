"""
rebuild_pbix.py — Reconstruye Rendimiento.pbix con layout god-tier.
Canvas: 1280x720 px · 5 paginas · Pixel-perfect · Tema WINIW Delivery.
"""

import zipfile, json, uuid, io

SRC = "Rendimiento.pbix"
DST = "Rendimiento_NEW.pbix"

W, H = 1280, 720

CONTENT_X = 210          # inicio area contenido (tras panel filtros 200px + 10gap)
CONTENT_W = 1065         # ancho area contenido (1275 - 210)
HEADER_H  = 56           # cabecera mas alta para el logo
PANEL_W   = 200          # ancho panel filtros
TOP_Y     = HEADER_H + 8 # y inicio contenido = 64
GAP       = 6

# ── Paleta WINIW Brand ──────────────────────────────────────────────────────
NAVY       = "#1B3A6B"   # azul corporativo (WIN)
LIME       = "#7DC400"   # verde lima (NIW)
NAVY_DARK  = "#0D2147"   # header mas oscuro
NAVY_MID   = "#244D8A"   # borde panel / acento
PAGE_BG    = "#EFF3F8"   # fondo pagina gris-azul claro
PANEL_BG   = "#FFFFFF"   # fondo panel filtros blanco
CARD_BG    = "#FFFFFF"
SECTION_LBL_COLOR = "#1B3A6B"

# ── Colores metricas ─────────────────────────────────────────────────────────
GREEN  = "#00B050"
RED    = "#D92B2B"
YELL   = "#F5C518"
WHITE  = "#FFFFFF"
GRAY   = "#6B7785"

GRAD_SCORE = (55, 70, 100, RED, YELL, GREEN)
GRAD_DNR   = (833, 1650, 3000, GREEN, YELL, RED)
GRAD_DCR   = (97, 99, 100, RED, YELL, GREEN)
GRAD_PCT   = (90, 97, 100, RED, YELL, GREEN)

CARD_H = 90
SECTION_LBL_H = 20

# ─────────────────────────────── helpers ────────────────────────────────────

def uid():
    return uuid.uuid4().hex[:20]

def pos(x, y, z, w, h):
    return {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}

def vc(sv_dict, x, y, z, w, h, filters="[]", query="", dt="", vc_objects=None):
    name = sv_dict.get("name") or uid()
    sv_dict["name"] = name
    sv_dict["layouts"] = [{"id": 0, "position": pos(x, y, z, w, h)}]
    result = {
        "x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z,
        "config": json.dumps(sv_dict),
        "filters": filters,
        "query": query,
        "dataTransforms": dt,
    }
    if vc_objects:
        result["vcObjects"] = vc_objects
    return result

def section(sid, name, display, ordinal, visuals, w=W, h=H):
    cfg = {
        "objects": {
            "background": [{"properties": {
                "color": {"solid": {"color": PAGE_BG}},
                "transparency": 0,
            }}],
            "displayArea": [{"properties": {
                "verticalAlignment": {"expr": {"Literal": {"Value": "'Middle'"}}}
            }}],
        }
    }
    return {
        "id": sid,
        "name": name,
        "displayName": display,
        "filters": "[]",
        "ordinal": ordinal,
        "visualContainers": visuals,
        "config": json.dumps(cfg),
        "displayOption": 1,
        "width": w,
        "height": h,
    }

# ─────────────────────────────── visual builders ────────────────────────────

def shape(x, y, z, w, h, fill, transparency=0, round_edge=0, border=0, border_color=None):
    """Rectangulo de fondo (basicShape)."""
    line_props = {
        "roundEdge": {"expr": {"Literal": {"Value": f"{round_edge}D"}}},
        "weight":    {"expr": {"Literal": {"Value": f"{border}D"}}},
    }
    if border_color:
        line_props["strokeColor"] = {"solid": {"color": border_color}}
    fill_props = {
        "show":      {"expr": {"Literal": {"Value": "true"}}},
        "fillColor": {"solid": {"color": fill}},
        "transparency": {"expr": {"Literal": {"Value": f"{transparency}D"}}},
    }
    return vc({
        "singleVisual": {
            "visualType": "basicShape",
            "objects": {
                "line": [{"properties": line_props}],
                "fill": [{"properties": fill_props}],
                "general": [{"properties": {}}],
            },
        }
    }, x, y, z, w, h)


def logo_header(page_title):
    """Cabecera WINIW con logo bicolor + titulo de pagina."""
    return vc({
        "singleVisual": {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [{
                "textRuns": [
                    {"value": "WIN",      "textStyle": {"fontWeight": "bold",   "fontSize": "22", "color": WHITE}},
                    {"value": "NIW",      "textStyle": {"fontWeight": "bold",   "fontSize": "22", "color": LIME}},
                    {"value": "  DELIVERY",  "textStyle": {"fontWeight": "normal", "fontSize": "11", "color": "#8AB0D8"}},
                    {"value": f"     |     {page_title}", "textStyle": {"fontWeight": "normal", "fontSize": "14", "color": "#C8D8EF"}},
                ],
                "horizontalTextAlignment": "Left",
            }]}}]},
        }
    }, 10, 0, 100, W - 10, HEADER_H)


def label(x, y, z, w, text, size="11", color=SECTION_LBL_COLOR, bold=True):
    style = {"fontSize": size, "color": color}
    if bold:
        style["fontWeight"] = "bold"
    return vc({
        "singleVisual": {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [{
                "textRuns": [{"value": text, "textStyle": style}],
                "horizontalTextAlignment": "Left",
            }]}}]},
        }
    }, x, y, z, w, SECTION_LBL_H)


def panel_header(text):
    """Label 'FILTROS' dentro del panel izquierdo."""
    return label(8, HEADER_H + 8, 150, PANEL_W - 16, text, size="10",
                 color=NAVY_MID, bold=True)


def slicer(x, y, z, w, h, entity, column, mode="Dropdown"):
    qref = f"{entity}.{column}"
    return vc({
        "singleVisual": {
            "visualType": "slicer",
            "projections": {"Values": [{"queryRef": qref, "active": True}]},
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "d", "Entity": entity, "Type": 0}],
                "Select": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}},
                             "Property": column}, "Name": qref, "NativeReferenceName": column}],
            },
            "drillFilterOtherVisuals": True,
            "objects": {
                "data": [{"properties": {
                    "mode": {"expr": {"Literal": {"Value": f"'{mode}'"}}},
                    "isInvertedSelectionMode": {"expr": {"Literal": {"Value": "true"}}},
                }}],
                "selection": [{"properties": {
                    "selectAllCheckboxEnabled": {"expr": {"Literal": {"Value": "true"}}},
                }}],
                "general": [{"properties": {}}],
            },
        }
    }, x, y, z, w, h)


def _gradient(entity, measure, lo_v, mid_v, hi_v, lo_c, mid_c, hi_c):
    return {"FillRule": {
        "Input": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": measure}},
        "FillRule": {"linearGradient3": {
            "min": {"color": {"Literal": {"Value": f"'{lo_c}'"}}, "value": {"Literal": {"Value": f"{lo_v}D"}}},
            "mid": {"color": {"Literal": {"Value": f"'{mid_c}'"}}, "value": {"Literal": {"Value": f"{mid_v}D"}}},
            "max": {"color": {"Literal": {"Value": f"'{hi_c}'"}}, "value": {"Literal": {"Value": f"{hi_v}D"}}},
        }},
    }}


def card(x, y, z, w, h, measure, entity="Medidas", gradient=None):
    qref = f"{entity}.{measure}"
    objects = {}
    if gradient:
        lv, mv, hv, lc, mc, hc = gradient
        rule = _gradient(entity, measure, lv, mv, hv, lc, mc, hc)
        objects["labels"] = [{"properties": {
            "color": {"solid": {"color": {"expr": rule}}},
            "fontSize": {"expr": {"Literal": {"Value": "26D"}}},
        }}]
    # fondo blanco via vcObjects
    white_bg = {"background": [{"properties": {
        "show":  {"expr": {"Literal": {"Value": "true"}}},
        "color": {"solid": {"color": CARD_BG}},
        "transparency": {"expr": {"Literal": {"Value": "0D"}}},
    }}]}
    return vc({
        "singleVisual": {
            "visualType": "card",
            "projections": {"Values": [{"queryRef": qref}]},
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "m", "Entity": entity, "Type": 0}],
                "Select": [{"Measure": {"Expression": {"SourceRef": {"Source": "m"}},
                             "Property": measure}, "Name": qref, "NativeReferenceName": measure}],
                "OrderBy": [{"Direction": 2, "Expression": {
                    "Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": measure}}}],
            },
            "drillFilterOtherVisuals": True,
            "hasDefaultSort": True,
            "objects": objects,
        }
    }, x, y, z, w, h, vc_objects=white_bg)


def area_chart(x, y, z, w, h, measure, cat_entity, cat_col,
               series_entity=None, series_col=None):
    qref_m = f"Medidas.{measure}"
    qref_c = f"{cat_entity}.{cat_col}"
    from_l = [{"Name": "m", "Entity": "Medidas", "Type": 0},
               {"Name": "d", "Entity": cat_entity, "Type": 0}]
    sel = [
        {"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": measure},
         "Name": qref_m, "NativeReferenceName": measure},
        {"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": cat_col},
         "Name": qref_c, "NativeReferenceName": cat_col},
    ]
    proj = {"Y": [{"queryRef": qref_m}], "Category": [{"queryRef": qref_c, "active": True}]}
    if series_entity and series_col:
        qref_s = f"{series_entity}.{series_col}"
        from_l.append({"Name": "s", "Entity": series_entity, "Type": 0})
        sel.append({"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": series_col},
                    "Name": qref_s, "NativeReferenceName": series_col})
        proj["Series"] = [{"queryRef": qref_s, "active": True}]
    white_bg = {"background": [{"properties": {
        "show":  {"expr": {"Literal": {"Value": "true"}}},
        "color": {"solid": {"color": CARD_BG}},
        "transparency": {"expr": {"Literal": {"Value": "0D"}}},
    }}]}
    return vc({
        "singleVisual": {
            "visualType": "areaChart",
            "projections": proj,
            "prototypeQuery": {
                "Version": 2, "From": from_l, "Select": sel,
                "OrderBy": [{"Direction": 1, "Expression": {
                    "Column": {"Expression": {"SourceRef": {"Source": "d"}},
                               "Property": cat_col}}}],
            },
            "drillFilterOtherVisuals": True,
            "hasDefaultSort": True,
        }
    }, x, y, z, w, h, vc_objects=white_bg)


def line_chart(x, y, z, w, h, measure, cat_entity, cat_col,
               series_entity=None, series_col=None):
    v = area_chart(x, y, z, w, h, measure, cat_entity, cat_col,
                   series_entity, series_col)
    cfg = json.loads(v["config"])
    cfg["singleVisual"]["visualType"] = "lineChart"
    v["config"] = json.dumps(cfg)
    return v


def bar_chart(x, y, z, w, h, measures, cat_entity, cat_col, horizontal=True):
    qref_c = f"{cat_entity}.{cat_col}"
    from_l = [{"Name": "m", "Entity": "Medidas", "Type": 0},
               {"Name": "d", "Entity": cat_entity, "Type": 0}]
    sel = [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": cat_col},
             "Name": qref_c, "NativeReferenceName": cat_col}]
    y_proj = []
    for m in measures:
        qm = f"Medidas.{m}"
        y_proj.append({"queryRef": qm})
        sel.append({"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": m},
                    "Name": qm, "NativeReferenceName": m})
    vtype = "clusteredBarChart" if horizontal else "clusteredColumnChart"
    white_bg = {"background": [{"properties": {
        "show":  {"expr": {"Literal": {"Value": "true"}}},
        "color": {"solid": {"color": CARD_BG}},
        "transparency": {"expr": {"Literal": {"Value": "0D"}}},
    }}]}
    return vc({
        "singleVisual": {
            "visualType": vtype,
            "projections": {"Y": y_proj, "Category": [{"queryRef": qref_c, "active": True}]},
            "prototypeQuery": {
                "Version": 2, "From": from_l, "Select": sel,
                "OrderBy": [{"Direction": 2, "Expression": {
                    "Measure": {"Expression": {"SourceRef": {"Source": "m"}},
                                "Property": measures[0]}}}],
            },
            "drillFilterOtherVisuals": True,
            "hasDefaultSort": True,
        }
    }, x, y, z, w, h, vc_objects=white_bg)


def matrix(x, y, z, w, h, row_entity, row_col, measures,
           col_entity=None, col_col=None):
    qref_r = f"{row_entity}.{row_col}"
    from_l = [{"Name": "r", "Entity": row_entity, "Type": 0}]
    sel = [{"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": row_col},
             "Name": qref_r, "NativeReferenceName": row_col}]
    proj = {"Rows": [{"queryRef": qref_r, "active": True}], "Values": []}
    if col_entity and col_col:
        qref_c = f"{col_entity}.{col_col}"
        from_l.append({"Name": "c", "Entity": col_entity, "Type": 0})
        sel.append({"Column": {"Expression": {"SourceRef": {"Source": "c"}}, "Property": col_col},
                     "Name": qref_c, "NativeReferenceName": col_col})
        proj["Columns"] = [{"queryRef": qref_c, "active": True}]
    from_l.append({"Name": "m", "Entity": "Medidas", "Type": 0})
    for m in measures:
        qm = f"Medidas.{m}"
        proj["Values"].append({"queryRef": qm})
        sel.append({"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": m},
                    "Name": qm, "NativeReferenceName": m})
    white_bg = {"background": [{"properties": {
        "show":  {"expr": {"Literal": {"Value": "true"}}},
        "color": {"solid": {"color": CARD_BG}},
        "transparency": {"expr": {"Literal": {"Value": "0D"}}},
    }}]}
    return vc({
        "singleVisual": {
            "visualType": "pivotTable",
            "projections": proj,
            "prototypeQuery": {"Version": 2, "From": from_l, "Select": sel},
            "drillFilterOtherVisuals": True,
            "hasDefaultSort": True,
        }
    }, x, y, z, w, h, vc_objects=white_bg)


# ─────────────────────────────── layout constants ───────────────────────────

E         = "df_estaciones"
COL_ANO   = "Año"
COL_SEM   = "semana"
COL_CEN   = "centro"
COL_FEC   = "fecha_semana"

CX = CONTENT_X
CW = CONTENT_W

CARD_Y  = TOP_Y                              # 64
CHART_Y = CARD_Y + CARD_H + GAP + SECTION_LBL_H + GAP   # 64+90+6+20+6 = 186

def mat_y(chart_h):
    return CHART_Y + chart_h + GAP + SECTION_LBL_H + GAP

def lbl_y(base_y):
    return base_y - SECTION_LBL_H - GAP

# ── Fondos comunes de cada pagina ────────────────────────────────────────────

def page_backgrounds(has_3_slicers=True):
    """Capa de fondos: header navy, panel blanco."""
    layers = [
        # Header bar navy oscuro
        shape(0, 0, -300, W, HEADER_H, NAVY_DARK),
        # Linea acento verde lima bajo el header
        shape(0, HEADER_H, -299, W, 3, LIME),
        # Panel filtros blanco
        shape(0, HEADER_H + 3, -200, PANEL_W, H - HEADER_H - 3, PANEL_BG,
              border=1, border_color="#D0DAE8"),
    ]
    return layers


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 1 — Resumen Ejecutivo
# ═══════════════════════════════════════════════════════════════════════════
def page1():
    CHART_H = 250
    MAT_Y   = mat_y(CHART_H)
    MAT_H   = H - MAT_Y - GAP   # = 720 - (186+250+6+20+6) - 6 = 246

    # 7 KPI cards — w=143, gap=7 → 7*143+6*7 = 1001+42 = 1043 ≤ 1065
    cw = 143; gap_c = 7
    cards_data = [
        ("Score Global",  GRAD_SCORE),
        ("DCR Promedio",  GRAD_DCR),
        ("DNR (DPMO)",    GRAD_DNR),
        ("DSC (DPMO)",    None),
        ("CC %",          GRAD_PCT),
        ("POD %",         GRAD_PCT),
        ("CDF (DPMO)",    None),
    ]
    v_cards = [card(CX + i*(cw+gap_c), CARD_Y, 500+i, cw, CARD_H, m, gradient=g)
               for i, (m, g) in enumerate(cards_data)]

    LW = 522; RW = CW - LW - GAP  # 522 + 6 + 537 = 1065

    return [
        *page_backgrounds(),
        logo_header("Resumen Ejecutivo"),
        panel_header("FILTROS"),
        slicer(8, TOP_Y + 24,   1000, 186, 52,  E, COL_ANO, "Dropdown"),
        slicer(8, TOP_Y + 84,   1001, 186, 78,  E, COL_SEM, "Dropdown"),
        slicer(8, TOP_Y + 170,  1002, 186, 215, E, COL_CEN, "Dropdown"),
        *v_cards,
        # Charts row
        label(CX, lbl_y(CHART_Y), 200, LW,
              "Score Global — Evolucion Semanal por Centro"),
        area_chart(CX, CHART_Y, 600, LW, CHART_H, "Score Global", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),
        label(CX+LW+GAP, lbl_y(CHART_Y), 201, RW,
              "Score Promedio — Ranking por Centro"),
        bar_chart(CX+LW+GAP, CHART_Y, 610, RW, CHART_H,
                  ["Score Global"], E, COL_CEN, horizontal=True),
        # Matrix
        label(CX, lbl_y(MAT_Y), 202, CW,
              "Score x Centro x Semana — Heatmap"),
        matrix(CX, MAT_Y, 700, CW, MAT_H,
               E, COL_CEN, ["Score Global"], col_entity=E, col_col=COL_SEM),
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 2 — Analisis por Centro
# ═══════════════════════════════════════════════════════════════════════════
def page2():
    CHART_H = 262
    MAT_Y   = mat_y(CHART_H)
    MAT_H   = H - MAT_Y - GAP

    cw4 = 258; gap4 = 9   # 4*258+3*9 = 1032+27 = 1059 ≤ 1065
    cards4 = [
        ("Score Global", GRAD_SCORE),
        ("DCR Promedio", GRAD_DCR),
        ("DNR (DPMO)",   GRAD_DNR),
        ("POD %",        GRAD_PCT),
    ]
    v_cards = [card(CX + i*(cw4+gap4), CARD_Y, 500+i, cw4, CARD_H, m, gradient=g)
               for i, (m, g) in enumerate(cards4)]

    LW = 522; RW = CW - LW - GAP

    return [
        *page_backgrounds(has_3_slicers=False),
        logo_header("Analisis por Centro"),
        panel_header("FILTROS"),
        slicer(8, TOP_Y + 24,  1000, 186, 52, E, COL_ANO, "Dropdown"),
        slicer(8, TOP_Y + 84,  1001, 186, 78, E, COL_SEM, "Dropdown"),
        *v_cards,
        label(CX, lbl_y(CHART_Y), 200, LW,
              "Score Promedio — Por Centro (mayor → menor)"),
        bar_chart(CX, CHART_Y, 600, LW, CHART_H,
                  ["Score Global"], E, COL_CEN, horizontal=True),
        label(CX+LW+GAP, lbl_y(CHART_Y), 201, RW,
              "DNR (DPMO) — Por Centro (menor = mejor)"),
        bar_chart(CX+LW+GAP, CHART_Y, 610, RW, CHART_H,
                  ["DNR (DPMO)"], E, COL_CEN, horizontal=True),
        label(CX, lbl_y(MAT_Y), 202, CW,
              "Todas las Metricas por Centro"),
        matrix(CX, MAT_Y, 700, CW, MAT_H,
               E, COL_CEN,
               ["Score Global", "DCR Promedio", "DNR (DPMO)", "CC %", "POD %", "CDF (DPMO)"]),
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 3 — Evolucion Semanal
# ═══════════════════════════════════════════════════════════════════════════
def page3():
    # 3 KPI cards — w=348, gap=10
    cw3 = 348; gap3 = 10   # 3*348+2*10 = 1044+20 = 1064 ≤ 1065
    cards3 = [
        ("Score Global", GRAD_SCORE),
        ("DCR Promedio", GRAD_DCR),
        ("DNR (DPMO)",   GRAD_DNR),
    ]
    v_cards = [card(CX + i*(cw3+gap3), CARD_Y, 500+i, cw3, CARD_H, m, gradient=g)
               for i, (m, g) in enumerate(cards3)]

    # Line chart full-width (Score) + 2 side by side (DCR, DNR)
    CH1 = 215
    CY2 = CHART_Y + CH1 + GAP + SECTION_LBL_H + GAP
    CH2 = H - CY2 - GAP
    LW = 522; RW = CW - LW - GAP

    return [
        *page_backgrounds(),
        logo_header("Evolucion Semanal"),
        panel_header("FILTROS"),
        slicer(8, TOP_Y + 24,   1000, 186, 52,  E, COL_ANO, "Dropdown"),
        slicer(8, TOP_Y + 84,   1001, 186, 215, E, COL_CEN, "Dropdown"),
        *v_cards,
        label(CX, lbl_y(CHART_Y), 200, CW,
              "Score Global — Tendencia Semanal (linea por Centro)"),
        line_chart(CX, CHART_Y, 600, CW, CH1, "Score Global", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),
        label(CX, lbl_y(CY2), 201, LW,
              "DCR Promedio — Evolucion"),
        line_chart(CX, CY2, 610, LW, CH2, "DCR Promedio", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),
        label(CX+LW+GAP, lbl_y(CY2), 202, RW,
              "DNR (DPMO) — Evolucion"),
        line_chart(CX+LW+GAP, CY2, 620, RW, CH2, "DNR (DPMO)", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 4 — Compliance & Calidad
# ═══════════════════════════════════════════════════════════════════════════
def page4():
    CHART_H = 255
    MAT_Y   = mat_y(CHART_H)
    MAT_H   = H - MAT_Y - GAP

    cw4 = 258; gap4 = 9
    cards4 = [
        ("CC %",       GRAD_PCT),
        ("POD %",      GRAD_PCT),
        ("CDF (DPMO)", None),
        ("DSC (DPMO)", None),
    ]
    v_cards = [card(CX + i*(cw4+gap4), CARD_Y, 500+i, cw4, CARD_H, m, gradient=g)
               for i, (m, g) in enumerate(cards4)]

    LW = 522; RW = CW - LW - GAP

    return [
        *page_backgrounds(),
        logo_header("Compliance & Calidad"),
        panel_header("FILTROS"),
        slicer(8, TOP_Y + 24,   1000, 186, 52,  E, COL_ANO, "Dropdown"),
        slicer(8, TOP_Y + 84,   1001, 186, 78,  E, COL_SEM, "Dropdown"),
        slicer(8, TOP_Y + 170,  1002, 186, 215, E, COL_CEN, "Dropdown"),
        *v_cards,
        label(CX, lbl_y(CHART_Y), 200, LW,
              "CC % (Contacto con Cliente) — Por Centro"),
        bar_chart(CX, CHART_Y, 600, LW, CHART_H,
                  ["CC %"], E, COL_CEN, horizontal=True),
        label(CX+LW+GAP, lbl_y(CHART_Y), 201, RW,
              "POD % (Prueba de Entrega) — Por Centro"),
        bar_chart(CX+LW+GAP, CHART_Y, 610, RW, CHART_H,
                  ["POD %"], E, COL_CEN, horizontal=True),
        label(CX, lbl_y(MAT_Y), 202, CW,
              "Compliance Completo: CC / POD / CDF / DSC por Centro"),
        matrix(CX, MAT_Y, 700, CW, MAT_H,
               E, COL_CEN, ["CC %", "POD %", "CDF (DPMO)", "DSC (DPMO)"]),
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 5 — Vista Completa
# ═══════════════════════════════════════════════════════════════════════════
def page5():
    # 3 KPI cards
    cw3 = 348; gap3 = 10
    cards3 = [
        ("Score Global", GRAD_SCORE),
        ("DCR Promedio", GRAD_DCR),
        ("DNR (DPMO)",   GRAD_DNR),
    ]
    v_cards = [card(CX + i*(cw3+gap3), CARD_Y, 500+i, cw3, CARD_H, m, gradient=g)
               for i, (m, g) in enumerate(cards3)]

    CH1 = 195
    CY2  = CHART_Y + CH1 + GAP + SECTION_LBL_H + GAP
    CH2  = H - CY2 - GAP
    LW = 522; RW = CW - LW - GAP

    return [
        *page_backgrounds(),
        logo_header("Vista Completa — Todas las Metricas"),
        panel_header("FILTROS"),
        slicer(8, TOP_Y + 24,   1000, 186, 52,  E, COL_ANO, "Dropdown"),
        slicer(8, TOP_Y + 84,   1001, 186, 78,  E, COL_SEM, "Dropdown"),
        slicer(8, TOP_Y + 170,  1002, 186, 215, E, COL_CEN, "Dropdown"),
        *v_cards,
        label(CX, lbl_y(CHART_Y), 200, CW,
              "Score Global — Vision Consolidada por Centro y Semana"),
        area_chart(CX, CHART_Y, 600, CW, CH1, "Score Global", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),
        label(CX, lbl_y(CY2), 201, LW,
              "CC % y POD % — Ranking Comparativo por Centro"),
        bar_chart(CX, CY2, 610, LW, CH2,
                  ["CC %", "POD %"], E, COL_CEN, horizontal=True),
        label(CX+LW+GAP, lbl_y(CY2), 202, RW,
              "CDF (DPMO) y DSC (DPMO) — Por Centro"),
        bar_chart(CX+LW+GAP, CY2, 620, RW, CH2,
                  ["CDF (DPMO)", "DSC (DPMO)"], E, COL_CEN, horizontal=True),
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  BUILD & WRITE
# ═══════════════════════════════════════════════════════════════════════════
def build_layout(orig):
    sections = [
        section(0, uid(), "Resumen Ejecutivo",      0, page1()),
        section(1, uid(), "Analisis por Centro",    1, page2()),
        section(2, uid(), "Evolucion Semanal",      2, page3()),
        section(3, uid(), "Compliance y Calidad",   3, page4()),
        section(4, uid(), "Vista Completa",         4, page5()),
    ]
    return {
        "id": orig.get("id", 0),
        "resourcePackages": orig.get("resourcePackages", []),
        "sections": sections,
        "config": orig.get("config", "{}"),
        "layoutOptimization": orig.get("layoutOptimization", 0),
    }


if __name__ == "__main__":
    # Leer original
    with zipfile.ZipFile(SRC, "r") as z:
        raw = z.read("Report/Layout")
        orig = json.loads(raw.decode("utf-16-le"))
        all_files = {n: z.read(n) for n in z.namelist()}

    # Construir nuevo layout
    new_layout = build_layout(orig)
    new_raw = json.dumps(new_layout, ensure_ascii=False).encode("utf-16-le")

    # Escribir .pbix
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, data in all_files.items():
            zout.writestr(n, new_raw if n == "Report/Layout" else data)

    buf.seek(0)
    with open(DST, "wb") as f:
        f.write(buf.read())

    # Validar
    with zipfile.ZipFile(DST, "r") as z:
        pages = json.loads(z.read("Report/Layout").decode("utf-16-le"))["sections"]

    print(f"OK {DST} - {len(pages)} paginas:")
    for p in pages:
        nv = len(p["visualContainers"])
        print(f"  [{p['ordinal']}] {p['displayName']} - {nv} visuales ({p['width']}x{p['height']})")

    # Validar posiciones
    errors = 0
    for p in pages:
        for v in p["visualContainers"]:
            if v["x"] + v["width"] > W or v["y"] + v["height"] > H:
                print(f"  OVERFLOW en {p['displayName']}: x={v['x']} y={v['y']} w={v['width']} h={v['height']}")
                errors += 1
    if errors == 0:
        print("Todas las posiciones OK - cero overflows.")
