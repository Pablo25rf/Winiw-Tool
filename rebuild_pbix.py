"""
rebuild_pbix.py — Reconstruye Rendimiento.pbix con layout god-tier.
Canvas: 1280×720 px · 5 páginas · Pixel-perfect.
"""

import zipfile, json, uuid, io, os, shutil

SRC  = "Rendimiento.pbix"
DST  = "Rendimiento_NEW.pbix"
BCK  = "Rendimiento_BACKUP.pbix"

W, H = 1280, 720          # canvas
CONTENT_X = 205           # inicio área de contenido (tras panel filtros)
CONTENT_W = 1070          # ancho área de contenido (1275 - 205)
HEADER_H  = 48            # altura cabecera
TOP_Y     = HEADER_H + 5  # y de inicio del contenido (53)

DARK  = "#1F2D40"
AMBER = "#FF9900"
GREEN = "#00B050"
RED   = "#F70707"
YELL  = "#E5FA02"

# ─────────────────────────────── helpers ───────────────────────────────────

def uid():
    return uuid.uuid4().hex[:20]

def pos(x, y, z, w, h):
    return {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}

def vc(sv_dict, x, y, z, w, h, filters="[]", query="", dt=""):
    name = sv_dict.get("name") or uid()
    sv_dict["name"] = name
    sv_dict["layouts"] = [{"id": 0, "position": pos(x, y, z, w, h)}]
    return {
        "x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z,
        "config": json.dumps(sv_dict),
        "filters": filters,
        "query": query,
        "dataTransforms": dt,
    }

def section(sid, name, display, ordinal, visuals, w=W, h=H):
    return {
        "id": sid,
        "name": name,
        "displayName": display,
        "filters": "[]",
        "ordinal": ordinal,
        "visualContainers": visuals,
        "config": json.dumps({"objects": {"displayArea": [{"properties": {
            "verticalAlignment": {"expr": {"Literal": {"Value": "'Middle'"}}}
        }}]}}),
        "displayOption": 1,
        "width": w,
        "height": h,
    }

# ─────────────────────────────── visual builders ────────────────────────────

def textbox(x, y, z, w, h, text, size="16", bold=True, color="#252423", align="Left"):
    style = {"fontSize": size}
    if bold:
        style["fontWeight"] = "bold"
    if color != "#252423":
        style["color"] = color
    return vc({
        "singleVisual": {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [{
                "textRuns": [{"value": text, "textStyle": style}],
                "horizontalTextAlignment": align,
            }]}}]},
        }
    }, x, y, z, w, h)


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


def _gradient_fill_rule(entity, measure, lo, mid, hi, lo_v=55, mid_v=70, hi_v=100):
    return {"FillRule": {
        "Input": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": measure}},
        "FillRule": {"linearGradient3": {
            "min": {"color": {"Literal": {"Value": f"'{lo}'"}}, "value": {"Literal": {"Value": f"{lo_v}D"}}},
            "mid": {"color": {"Literal": {"Value": f"'{mid}'"}}, "value": {"Literal": {"Value": f"{mid_v}D"}}},
            "max": {"color": {"Literal": {"Value": f"'{hi}'"}}, "value": {"Literal": {"Value": f"{hi_v}D"}}},
        }},
    }}


def card(x, y, z, w, h, measure, entity="Medidas", gradient=None):
    """
    gradient: None | (lo_val, mid_val, hi_val, lo_color, mid_color, hi_color)
    """
    qref = f"{entity}.{measure}"
    objects = {}
    if gradient:
        lv, mv, hv, lc, mc, hc = gradient
        rule = _gradient_fill_rule(entity, measure, lc, mc, hc, lv, mv, hv)
        objects["labels"] = [{"properties": {
            "color": {"solid": {"color": {"expr": rule}}},
            "fontSize": {"expr": {"Literal": {"Value": "28D"}}},
            "fontFamily": {"expr": {"Literal": {"Value": "'Segoe UI'"}}}
        }}]
        objects["title"] = [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}]

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
    }, x, y, z, w, h)


def area_chart(x, y, z, w, h, measure, cat_entity, cat_col, series_entity=None, series_col=None):
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

    return vc({
        "singleVisual": {
            "visualType": "areaChart",
            "projections": proj,
            "prototypeQuery": {
                "Version": 2, "From": from_l, "Select": sel,
                "OrderBy": [{"Direction": 1, "Expression": {
                    "Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": cat_col}}}],
            },
            "drillFilterOtherVisuals": True,
            "hasDefaultSort": True,
        }
    }, x, y, z, w, h)


def line_chart(x, y, z, w, h, measure, cat_entity, cat_col, series_entity=None, series_col=None):
    v = area_chart(x, y, z, w, h, measure, cat_entity, cat_col, series_entity, series_col)
    cfg = json.loads(v["config"])
    cfg["singleVisual"]["visualType"] = "lineChart"
    v["config"] = json.dumps(cfg)
    return v


def bar_chart(x, y, z, w, h, measures, cat_entity, cat_col, horizontal=True):
    """Clustered bar (horizontal=True) or column chart."""
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
    return vc({
        "singleVisual": {
            "visualType": vtype,
            "projections": {"Y": y_proj, "Category": [{"queryRef": qref_c, "active": True}]},
            "prototypeQuery": {
                "Version": 2, "From": from_l, "Select": sel,
                "OrderBy": [{"Direction": 2, "Expression": {
                    "Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": measures[0]}}}],
            },
            "drillFilterOtherVisuals": True,
            "hasDefaultSort": True,
        }
    }, x, y, z, w, h)


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

    return vc({
        "singleVisual": {
            "visualType": "pivotTable",
            "projections": proj,
            "prototypeQuery": {"Version": 2, "From": from_l, "Select": sel},
            "drillFilterOtherVisuals": True,
            "hasDefaultSort": True,
        }
    }, x, y, z, w, h)


# ─────────────────────────────── shorthand helpers ──────────────────────────

E  = "df_estaciones"   # table entity name
M  = "Medidas"
COL_ANO   = "Año"      # with accent — matches DataModel
COL_SEM   = "semana"
COL_CEN   = "centro"
COL_FEC   = "fecha_semana"

CARD_Y = TOP_Y          # y=53
CARD_H = 92

# Score gradient: 55→red, 70→yellow, 100→green
GRAD_SCORE = (55, 70, 100, RED, YELL, GREEN)
# DNR gradient inverted: low is good → 833=green, 1650=yellow, >1650=red
GRAD_DNR   = (833, 1650, 3000, GREEN, YELL, RED)
# DCR: 99→yellow, 99.5→green (already %)
GRAD_DCR   = (97, 99, 100, RED, YELL, GREEN)
# CC/POD %
GRAD_PCT   = (90, 97, 100, RED, YELL, GREEN)

SECTION_LBL_H = 22      # height of section label textboxes
GAP = 5                  # gap between elements

def chart_y():  # y where charts start (below KPI cards)
    return CARD_Y + CARD_H + GAP + SECTION_LBL_H + GAP  # 53+92+5+22+5 = 177

def matrix_y(chart_h):  # y where matrix starts
    return chart_y() + chart_h + GAP + SECTION_LBL_H + GAP

def lbl_y(base_y):  # y of section label above a block
    return base_y - SECTION_LBL_H - GAP

# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 1 — Resumen Ejecutivo
# ═══════════════════════════════════════════════════════════════════════════
def page1():
    # Layout constants
    CX, CW = CONTENT_X, CONTENT_W    # 205, 1070
    CHART_H = 255
    CY = chart_y()                    # 177
    MAT_H = H - matrix_y(CHART_H) - GAP  # 720 - (177+255+5+22+5) - 5 = 251
    MAT_Y = matrix_y(CHART_H)        # 464

    # 7 KPI cards — 146px wide × 92px high, gap=8, starts at x=205
    cw = 146
    gap_c = 8
    cards_order = [
        ("Score Global",  GRAD_SCORE),
        ("DCR Promedio",  GRAD_DCR),
        ("DNR (DPMO)",    GRAD_DNR),
        ("DSC (DPMO)",    None),
        ("CC %",          GRAD_PCT),
        ("POD %",         GRAD_PCT),
        ("CDF (DPMO)",    None),
    ]
    v_cards = []
    for i, (m, g) in enumerate(cards_order):
        cx = CX + i * (cw + gap_c)
        v_cards.append(card(cx, CARD_Y, 500 + i, cw, CARD_H, m, gradient=g))

    # Charts
    chart_lw = 530
    chart_rw = CW - chart_lw - GAP  # 535

    v_charts = [
        textbox(CX, lbl_y(CY), 200, chart_lw, SECTION_LBL_H,
                "Score Global — Evolución Semanal", size="11", bold=True, color="#555555"),
        area_chart(CX, CY, 600, chart_lw, CHART_H, "Score Global", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),

        textbox(CX + chart_lw + GAP, lbl_y(CY), 201, chart_rw, SECTION_LBL_H,
                "Score Promedio — Por Centro (desc)", size="11", bold=True, color="#555555"),
        bar_chart(CX + chart_lw + GAP, CY, 610, chart_rw, CHART_H,
                  ["Score Global"], E, COL_CEN, horizontal=True),
    ]

    # Matrix
    v_matrix = [
        textbox(CX, lbl_y(MAT_Y), 202, CW, SECTION_LBL_H,
                "Matriz Score × Centro × Semana", size="11", bold=True, color="#555555"),
        matrix(CX, MAT_Y, 700, CW, MAT_H,
               E, COL_CEN, ["Score Global"], col_entity=E, col_col=COL_SEM),
    ]

    return [
        textbox(0, 0, 100, W, HEADER_H,
                "WINIW  |  Rendimiento DSP — Resumen Ejecutivo",
                size="16", bold=True, color=AMBER),
        # Slicers
        slicer(8, 53,  1000, 184, 55,  E, COL_ANO,  "Dropdown"),
        slicer(8, 113, 1001, 184, 80,  E, COL_SEM,  "Dropdown"),
        slicer(8, 198, 1002, 184, 220, E, COL_CEN,  "Dropdown"),
        *v_cards,
        *v_charts,
        *v_matrix,
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 2 — Análisis por Centro
# ═══════════════════════════════════════════════════════════════════════════
def page2():
    CX, CW = CONTENT_X, CONTENT_W
    CHART_H = 268
    CY = chart_y()
    MAT_H = H - matrix_y(CHART_H) - GAP
    MAT_Y = matrix_y(CHART_H)

    # 4 KPI cards — each 260px wide, gap=10
    cw4 = 260; gap4 = 10
    cards4 = [
        ("Score Global", GRAD_SCORE),
        ("DCR Promedio", GRAD_DCR),
        ("DNR (DPMO)",   GRAD_DNR),
        ("POD %",        GRAD_PCT),
    ]
    v_cards = []
    for i, (m, g) in enumerate(cards4):
        cx = CX + i * (cw4 + gap4)
        v_cards.append(card(cx, CARD_Y, 500 + i, cw4, CARD_H, m, gradient=g))

    chart_lw = 530; chart_rw = CW - chart_lw - GAP

    v_charts = [
        textbox(CX, lbl_y(CY), 200, chart_lw, SECTION_LBL_H,
                "Score Promedio — Por Centro", size="11", bold=True, color="#555555"),
        bar_chart(CX, CY, 600, chart_lw, CHART_H,
                  ["Score Global"], E, COL_CEN, horizontal=True),

        textbox(CX + chart_lw + GAP, lbl_y(CY), 201, chart_rw, SECTION_LBL_H,
                "DNR (DPMO) — Por Centro", size="11", bold=True, color="#555555"),
        bar_chart(CX + chart_lw + GAP, CY, 610, chart_rw, CHART_H,
                  ["DNR (DPMO)"], E, COL_CEN, horizontal=True),
    ]

    v_matrix = [
        textbox(CX, lbl_y(MAT_Y), 202, CW, SECTION_LBL_H,
                "Todas las Métricas × Centro", size="11", bold=True, color="#555555"),
        matrix(CX, MAT_Y, 700, CW, MAT_H,
               E, COL_CEN,
               ["Score Global", "DCR Promedio", "DNR (DPMO)", "CC %", "POD %", "CDF (DPMO)"]),
    ]

    return [
        textbox(0, 0, 100, W, HEADER_H,
                "WINIW  |  Análisis por Centro",
                size="16", bold=True, color=AMBER),
        slicer(8, 53,  1000, 184, 55,  E, COL_ANO, "Dropdown"),
        slicer(8, 113, 1001, 184, 80,  E, COL_SEM, "Dropdown"),
        *v_cards,
        *v_charts,
        *v_matrix,
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 3 — Evolución Semanal
# ═══════════════════════════════════════════════════════════════════════════
def page3():
    CX, CW = CONTENT_X, CONTENT_W

    # 3 KPI cards — each 350px wide, gap=10
    cw3 = 350; gap3 = 10
    cards3 = [
        ("Score Global", GRAD_SCORE),
        ("DCR Promedio", GRAD_DCR),
        ("DNR (DPMO)",   GRAD_DNR),
    ]
    v_cards = []
    for i, (m, g) in enumerate(cards3):
        cx = CX + i * (cw3 + gap3)
        v_cards.append(card(cx, CARD_Y, 500 + i, cw3, CARD_H, m, gradient=g))

    # Score full-width line chart
    CH1 = 220
    CY1 = chart_y()  # 177
    # Two side-by-side line charts below
    CY2 = CY1 + CH1 + GAP + SECTION_LBL_H + GAP  # 177+220+5+22+5 = 429
    CH2 = H - CY2 - GAP  # 720 - 429 - 5 = 286
    chart_lw = 530; chart_rw = CW - chart_lw - GAP

    v_charts = [
        textbox(CX, lbl_y(CY1), 200, CW, SECTION_LBL_H,
                "Score Global — Tendencia Semanal (por Centro)", size="11", bold=True, color="#555555"),
        line_chart(CX, CY1, 600, CW, CH1, "Score Global", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),

        textbox(CX, lbl_y(CY2), 201, chart_lw, SECTION_LBL_H,
                "DCR Promedio — Evolución", size="11", bold=True, color="#555555"),
        line_chart(CX, CY2, 610, chart_lw, CH2, "DCR Promedio", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),

        textbox(CX + chart_lw + GAP, lbl_y(CY2), 202, chart_rw, SECTION_LBL_H,
                "DNR (DPMO) — Evolución", size="11", bold=True, color="#555555"),
        line_chart(CX + chart_lw + GAP, CY2, 620, chart_rw, CH2, "DNR (DPMO)", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),
    ]

    return [
        textbox(0, 0, 100, W, HEADER_H,
                "WINIW  |  Evolución Semanal",
                size="16", bold=True, color=AMBER),
        slicer(8, 53,  1000, 184, 55,  E, COL_ANO, "Dropdown"),
        slicer(8, 113, 1001, 184, 220, E, COL_CEN, "Dropdown"),
        *v_cards,
        *v_charts,
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 4 — Compliance & Calidad
# ═══════════════════════════════════════════════════════════════════════════
def page4():
    CX, CW = CONTENT_X, CONTENT_W
    CHART_H = 262
    CY = chart_y()
    MAT_H = H - matrix_y(CHART_H) - GAP
    MAT_Y = matrix_y(CHART_H)

    # 4 KPI cards — each 260px, gap=10
    cw4 = 260; gap4 = 10
    cards4 = [
        ("CC %",      GRAD_PCT),
        ("POD %",     GRAD_PCT),
        ("CDF (DPMO)", None),
        ("DSC (DPMO)", None),
    ]
    v_cards = []
    for i, (m, g) in enumerate(cards4):
        cx = CX + i * (cw4 + gap4)
        v_cards.append(card(cx, CARD_Y, 500 + i, cw4, CARD_H, m, gradient=g))

    chart_lw = 530; chart_rw = CW - chart_lw - GAP

    v_charts = [
        textbox(CX, lbl_y(CY), 200, chart_lw, SECTION_LBL_H,
                "CC % — Por Centro", size="11", bold=True, color="#555555"),
        bar_chart(CX, CY, 600, chart_lw, CHART_H,
                  ["CC %"], E, COL_CEN, horizontal=True),

        textbox(CX + chart_lw + GAP, lbl_y(CY), 201, chart_rw, SECTION_LBL_H,
                "POD % — Por Centro", size="11", bold=True, color="#555555"),
        bar_chart(CX + chart_lw + GAP, CY, 610, chart_rw, CHART_H,
                  ["POD %"], E, COL_CEN, horizontal=True),
    ]

    v_matrix = [
        textbox(CX, lbl_y(MAT_Y), 202, CW, SECTION_LBL_H,
                "Compliance × Centro — CC / POD / CDF / DSC", size="11", bold=True, color="#555555"),
        matrix(CX, MAT_Y, 700, CW, MAT_H,
               E, COL_CEN, ["CC %", "POD %", "CDF (DPMO)", "DSC (DPMO)"]),
    ]

    return [
        textbox(0, 0, 100, W, HEADER_H,
                "WINIW  |  Compliance & Calidad",
                size="16", bold=True, color=AMBER),
        slicer(8, 53,  1000, 184, 55,  E, COL_ANO, "Dropdown"),
        slicer(8, 113, 1001, 184, 80,  E, COL_SEM, "Dropdown"),
        slicer(8, 198, 1002, 184, 220, E, COL_CEN, "Dropdown"),
        *v_cards,
        *v_charts,
        *v_matrix,
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE 5 — Vista Completa
# ═══════════════════════════════════════════════════════════════════════════
def page5():
    CX, CW = CONTENT_X, CONTENT_W

    # 3 KPI cards — each 350px, gap=10
    cw3 = 350; gap3 = 10
    cards3 = [
        ("Score Global", GRAD_SCORE),
        ("DCR Promedio", GRAD_DCR),
        ("DNR (DPMO)",   GRAD_DNR),
    ]
    v_cards = []
    for i, (m, g) in enumerate(cards3):
        cx = CX + i * (cw3 + gap3)
        v_cards.append(card(cx, CARD_Y, 500 + i, cw3, CARD_H, m, gradient=g))

    # Full-width area chart (Score trend all centros)
    CH1 = 200
    CY1 = chart_y()  # 177
    # Two side by side below
    CY2 = CY1 + CH1 + GAP + SECTION_LBL_H + GAP   # 177+200+5+22+5 = 409
    CH2 = H - CY2 - GAP   # 720-409-5 = 306
    chart_lw = 530; chart_rw = CW - chart_lw - GAP

    v_charts = [
        textbox(CX, lbl_y(CY1), 200, CW, SECTION_LBL_H,
                "Score Global — Vista Consolidada por Centro y Semana", size="11", bold=True, color="#555555"),
        area_chart(CX, CY1, 600, CW, CH1, "Score Global", E, COL_FEC,
                   series_entity=E, series_col=COL_CEN),

        textbox(CX, lbl_y(CY2), 201, chart_lw, SECTION_LBL_H,
                "CC % y POD % — Ranking por Centro", size="11", bold=True, color="#555555"),
        bar_chart(CX, CY2, 610, chart_lw, CH2,
                  ["CC %", "POD %"], E, COL_CEN, horizontal=True),

        textbox(CX + chart_lw + GAP, lbl_y(CY2), 202, chart_rw, SECTION_LBL_H,
                "CDF (DPMO) y DSC (DPMO) — Ranking por Centro", size="11", bold=True, color="#555555"),
        bar_chart(CX + chart_lw + GAP, CY2, 620, chart_rw, CH2,
                  ["CDF (DPMO)", "DSC (DPMO)"], E, COL_CEN, horizontal=True),
    ]

    return [
        textbox(0, 0, 100, W, HEADER_H,
                "WINIW  |  Vista Completa — Todas las Métricas",
                size="16", bold=True, color=AMBER),
        slicer(8, 53,  1000, 184, 55,  E, COL_ANO, "Dropdown"),
        slicer(8, 113, 1001, 184, 80,  E, COL_SEM, "Dropdown"),
        slicer(8, 198, 1002, 184, 220, E, COL_CEN, "Dropdown"),
        *v_cards,
        *v_charts,
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  BUILD LAYOUT
# ═══════════════════════════════════════════════════════════════════════════
def build_layout(original_layout):
    orig_cfg = original_layout.get("config", "{}")
    orig_rp  = original_layout.get("resourcePackages", [])

    sections = [
        section(0, uid(), "Resumen Ejecutivo",     0, page1()),
        section(1, uid(), "Análisis por Centro",   1, page2()),
        section(2, uid(), "Evolución Semanal",     2, page3()),
        section(3, uid(), "Compliance & Calidad",  3, page4()),
        section(4, uid(), "Vista Completa",        4, page5()),
    ]

    layout = {
        "id": original_layout.get("id", 0),
        "resourcePackages": orig_rp,
        "sections": sections,
        "config": orig_cfg,
        "layoutOptimization": original_layout.get("layoutOptimization", 0),
    }
    return layout


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # 1. Read original
    with zipfile.ZipFile(SRC, "r") as z:
        raw = z.read("Report/Layout")
        orig_layout = json.loads(raw.decode("utf-16-le"))
        all_files = {name: z.read(name) for name in z.namelist()}

    # 2. Build new layout
    new_layout = build_layout(orig_layout)
    new_raw = json.dumps(new_layout, ensure_ascii=False).encode("utf-16-le")

    # 3. Write new .pbix (in-memory to avoid partial writes)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z_out:
        for name, data in all_files.items():
            if name == "Report/Layout":
                z_out.writestr(name, new_raw)
            else:
                z_out.writestr(name, data)

    buf.seek(0)
    with open(DST, "wb") as f:
        f.write(buf.read())

    # 4. Summary
    with zipfile.ZipFile(DST, "r") as z:
        layout_check = json.loads(z.read("Report/Layout").decode("utf-16-le"))

    pages = layout_check["sections"]
    print(f"OK {DST} escrito - {len(pages)} paginas:")
    for p in pages:
        n_vis = len(p["visualContainers"])
        print(f"  [{p['ordinal']}] {p['displayName']} - {n_vis} visuales  ({p['width']}x{p['height']})")
