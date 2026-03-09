# Guía Power BI — Winiw Quality Scorecard
### Versión God Tier · Completa · Lista para Producción

> Autor: [@pablo25rf](https://github.com/pablo25rf)
> Última actualización: Marzo 2026
> Motor: `amazon_scorecard_ultra_robust_v3_FINAL.py` · BD: Supabase (PostgreSQL)

---

## ADVERTENCIA IMPORTANTE — Estado actual del .pbix

El archivo `Rendimiento.pbix` tiene actualmente **1 página** ("Página 1") con:
- Fuente de datos: tabla local `df_estaciones` (importada desde Python/CSV — **NO conectada a Supabase**)
- 7 tarjetas KPI, 1 gráfico de área, 1 tabla dinámica, 3 slicers
- Medidas en tabla `Medidas`: `Score Global`, `DCR Promedio`, `DNR (DPMO)`, `DSC (DPMO)`, `CC %`, `POD %`, `CDF (DPMO)`

**Para conectar a Supabase:** hay que eliminar la consulta `df_estaciones` en Power Query y crear 3 nuevas conexiones PostgreSQL. Las medidas DAX existentes se romperán hasta que las tablas de Supabase estén conectadas. Sigue el PASO 1 antes de crear medidas nuevas.

---

## PASO 1 — Conexión a Supabase (3 tablas)

### 1A — Eliminar la fuente local df_estaciones

1. Abrir **Power BI Desktop → Transformar datos** (Power Query Editor)
2. En el panel izquierdo, click derecho sobre `df_estaciones` → **Eliminar**
3. Confirmar. Las medidas que dependen de ella mostrarán error temporalmente (normal).
4. No cerrar Power Query todavía.

### 1B — Crear conexión PostgreSQL para `scorecards`

1. En Power Query: **Inicio → Nueva consulta → Origen en blanco** (o **Nuevo origen → Base de datos → PostgreSQL**)
2. Si pide servidor:
   ```
   Servidor:        aws-0-eu-west-3.pooler.supabase.com:6543
   Base de datos:   postgres
   ```
   > El puerto 6543 es el de Supabase Pooler (Transaction mode). Si falla, prueba puerto 5432 con el host directo de tu proyecto.
3. En **Opciones avanzadas → Instrucción SQL nativa**, pegar exactamente:

```sql
SELECT
    id,
    semana,
    anio,
    fecha_semana,
    centro,
    driver_id,
    driver_name,
    calificacion,
    score,
    entregados,
    dnr,
    fs_count,
    dnr_risk_events,
    -- Porcentajes: multiplicar x100 porque en BD son decimales 0-1
    ROUND(dcr  * 100, 2) AS dcr_pct,
    ROUND(pod  * 100, 2) AS pod_pct,
    ROUND(cc   * 100, 2) AS cc_pct,
    ROUND(rts  * 100, 2) AS rts_pct,
    ROUND(cdf  * 100, 2) AS cdf_pct,
    ROUND(fdps * 100, 2) AS fdps_pct,
    -- DPMO calculados en SQL (más eficiente que en DAX)
    ROUND((1 - dcr) * 1000000)                              AS dnr_dpmo_driver,
    ROUND(dnr::numeric / NULLIF(entregados, 0) * 1000000)   AS dnr_dpmo_calc,
    -- Columnas del PDF oficial Amazon
    entregados_oficial,
    ROUND(dcr_oficial  * 100, 2) AS dcr_oficial_pct,
    ROUND(pod_oficial  * 100, 2) AS pod_oficial_pct,
    ROUND(cc_oficial   * 100, 2) AS cc_oficial_pct,
    cdf_dpmo_oficial,
    lor_dpmo,
    dsc_dpmo,
    ce_dpmo,
    detalles,
    pdf_loaded,
    uploaded_by,
    timestamp
FROM scorecards
ORDER BY fecha_semana DESC, centro, driver_name
```

4. Autenticación: **Base de datos** → usuario y contraseña de Supabase
5. Renombrar la consulta como **"scorecards"**

### 1C — Crear conexión para `station_scorecards`

Repetir pasos 1B con esta SQL:

```sql
SELECT
    semana,
    anio,
    fecha_semana,
    centro,
    overall_score,
    overall_standing,
    rank_station,
    rank_wow,
    fico,
    fico_tier,
    whc_pct,
    whc_tier,
    dcr_pct,
    dcr_tier,
    dnr_dpmo,
    dnr_tier,
    lor_dpmo,
    lor_tier,
    dsc_dpmo,
    dsc_tier,
    pod_pct,
    pod_tier,
    cc_pct,
    cc_tier,
    ce_dpmo,
    ce_tier,
    cdf_dpmo,
    cdf_tier,
    safety_tier,
    speeding_rate,
    mentor_adoption,
    vsa_compliance,
    focus_area_1,
    focus_area_2,
    focus_area_3,
    boc,
    cas,
    capacity_next_day,
    capacity_same_day,
    -- wh_count: número de infracciones WHC de esa semana/centro (LEFT JOIN)
    (
        SELECT COUNT(*)
        FROM wh_exceptions w
        WHERE w.semana = station_scorecards.semana
          AND w.anio   = station_scorecards.anio
          AND w.centro = station_scorecards.centro
          AND (w.daily_limit_exceeded = 1
            OR w.weekly_limit_exceeded = 1
            OR w.under_offwork_limit = 1
            OR w.workday_limit_exceeded = 1)
    ) AS wh_count,
    uploaded_by,
    timestamp
FROM station_scorecards
ORDER BY fecha_semana DESC, centro
```

Renombrar como **"station_scorecards"**

### 1D — Crear conexión para `wh_exceptions`

```sql
SELECT
    semana,
    anio,
    fecha_semana,
    centro,
    driver_id,
    driver_name,
    daily_limit_exceeded,
    weekly_limit_exceeded,
    under_offwork_limit,
    workday_limit_exceeded,
    uploaded_by,
    timestamp
FROM wh_exceptions
ORDER BY fecha_semana DESC, centro, driver_name
```

Renombrar como **"wh_exceptions"**

### 1E — Tipos de datos en Power Query (OBLIGATORIO)

Después de cargar cada tabla, verificar y corregir tipos:

| Columna | Tipo correcto |
|---------|--------------|
| `fecha_semana` | Fecha |
| `semana` | Texto |
| `anio` | Número entero |
| `score`, `overall_score`, `dcr_pct`, `pod_pct`, etc. | Número decimal |
| `entregados`, `dnr`, `fs_count`, `lor_dpmo`, `dsc_dpmo`, `dnr_dpmo` | Número entero |
| `calificacion`, `centro`, `driver_id`, `driver_name` | Texto |
| `daily_limit_exceeded`, `weekly_limit_exceeded`, etc. | Número entero (0/1) |
| `timestamp` | Fecha/Hora |

**Cerrar y aplicar** cuando todos los tipos estén correctos.

### 1F — Modo de conectividad

- **Importar** (recomendado): carga los datos en memoria, actualización manual o programada. Con ~57.000 registros/año, carga < 3 segundos.
- **DirectQuery**: tiempo real pero requiere Power BI Premium o PPU. Cada visual lanza una query a Supabase (~1-2 segundos por visual).

---

## PASO 2 — Tabla Calendario ISO (Power Query M)

> **Cuándo usar el Calendario:** es útil si necesitas slicers jerárquicos Año → Trimestre → Mes. Para filtrar solo por `anio` (entero de la BD) y `semana` (texto W01..W52), **no es obligatorio**.
>
> **Nunca uses `Calendario[Fecha]` como eje de gráficos de línea** — genera 6 puntos vacíos entre cada semana real. Usa siempre `scorecards[fecha_semana]` como eje.

1. Power Query → **Inicio → Nueva consulta → Consulta en blanco**
2. En la barra de fórmulas (F2), pegar todo el bloque M siguiente:

```powerquery
let
    FechaInicio  = #date(2025, 1, 1),
    FechaFin     = #date(2028, 12, 31),
    NumDias      = Duration.Days(FechaFin - FechaInicio) + 1,
    Fechas       = List.Dates(FechaInicio, NumDias, #duration(1,0,0,0)),
    Tabla        = Table.FromList(Fechas, Splitter.SplitByNothing(), {"Fecha"}),
    TipoFecha    = Table.TransformColumnTypes(Tabla, {{"Fecha", type date}}),

    // Año
    Anio         = Table.AddColumn(TipoFecha, "Año",
                       each Date.Year([Fecha]), Int64.Type),

    // Trimestre
    Trimestre    = Table.AddColumn(Anio, "Trimestre",
                       each "Q" & Text.From(Date.QuarterOfYear([Fecha])), type text),

    // Mes número y nombre
    MesNum       = Table.AddColumn(Trimestre, "MesNum",
                       each Date.Month([Fecha]), Int64.Type),
    MesNombre    = Table.AddColumn(MesNum, "Mes",
                       each Text.Start(Date.ToText([Fecha], "MMMM", "es-ES"), 20), type text),

    // ── Semana ISO 8601 ─────────────────────────────────────────────────────
    // El jueves de cada fecha determina el año ISO y el número de semana.
    // Es la misma lógica que usa amazon_scorecard_ultra_robust_v3_FINAL.py.
    ISONumSemana = Table.AddColumn(MesNombre, "NúmSemana",
                       each
                           let
                               d        = [Fecha],
                               dow      = Date.DayOfWeek(d, Day.Monday),    // 0=Lun … 6=Dom
                               thursday = Date.AddDays(d, 3 - dow),
                               yr       = Date.Year(thursday),
                               jan4     = #date(yr, 1, 4),
                               jan4dow  = Date.DayOfWeek(jan4, Day.Monday),
                               wk1start = Date.AddDays(jan4, -jan4dow)
                           in
                               Number.IntegerDivide(
                                   Duration.Days(thursday - wk1start), 7) + 1,
                       Int64.Type),

    // Label "W05", "W10", etc. — mismo formato que la BD
    SemanaLabel  = Table.AddColumn(ISONumSemana, "SemanaLabel",
                       each "W" & Text.PadStart(Text.From([NúmSemana]), 2, "0"),
                       type text),

    // Año ISO de la semana (puede diferir del año calendario en sem 1/52)
    AnioISO      = Table.AddColumn(SemanaLabel, "AnioISO",
                       each
                           let
                               d        = [Fecha],
                               dow      = Date.DayOfWeek(d, Day.Monday),
                               thursday = Date.AddDays(d, 3 - dow)
                           in
                               Date.Year(thursday),
                       Int64.Type),

    // Lunes de la semana (= fecha_semana que almacena la BD)
    LunesSemana  = Table.AddColumn(AnioISO, "LunesSemana",
                       each
                           let
                               dow = Date.DayOfWeek([Fecha], Day.Monday)
                           in
                               Date.AddDays([Fecha], -dow),
                       type date),

    // Indicador fin de semana
    EsFinSemana  = Table.AddColumn(LunesSemana, "EsFinSemana",
                       each Date.DayOfWeek([Fecha]) >= 5, type logical)
in
    EsFinSemana
```

3. Renombrar la consulta como **"Calendario"**
4. **Cerrar y aplicar**

> **Nota sobre semana ISO vs US:** `Date.WeekOfYear` nativo de Power Query usa semanas US (domingo = día 1). La app Python usa semanas ISO 8601 (lunes = día 1). El código M de arriba replica exactamente el algoritmo ISO — **no lo sustituyas por `Date.WeekOfYear`**.

---

## PASO 3 — Modelo de datos y relaciones

### 3A — Tabla dimensión Centros (OBLIGATORIO para slicers cruzados)

Un slicer de `Centros[centro]` filtra las 3 tablas a la vez mediante relaciones.

1. **Modelado → Nueva tabla** y pegar:
   ```dax
   Centros = DISTINCT(SELECTCOLUMNS(scorecards, "centro", scorecards[centro]))
   ```
   > Esta tabla se actualiza sola cuando hay nuevos centros en `scorecards`.

2. Crear las 3 relaciones en la vista **Modelo**:

   | Desde | Hacia | Cardinalidad | Activa |
   |-------|-------|-------------|--------|
   | `Centros[centro]` | `scorecards[centro]` | 1:N | Sí |
   | `Centros[centro]` | `station_scorecards[centro]` | 1:N | Sí |
   | `Centros[centro]` | `wh_exceptions[centro]` | 1:N | Sí |

3. **Relación opcional con Calendario** (solo si se usa):
   ```
   Calendario[Fecha]  →  scorecards[fecha_semana]         (1:N, activa)
   Calendario[Fecha]  →  station_scorecards[fecha_semana] (1:N, inactiva)
   Calendario[Fecha]  →  wh_exceptions[fecha_semana]      (1:N, inactiva)
   ```
   Las relaciones inactivas se activan en medidas DAX con `USERELATIONSHIP`.

### 3B — Ordenar `semana` por `fecha_semana` (OBLIGATORIO)

El campo `semana` es texto ("W01", "W10"…). Sin configuración, Power BI lo ordena alfabéticamente: W10 aparece antes que W09.

1. Vista **Datos** → seleccionar tabla `scorecards`
2. Click en columna `semana`
3. Cinta: **Herramientas de columna → Ordenar por columna → fecha_semana**
4. Repetir para `station_scorecards[semana]` y `wh_exceptions[semana]`

### 3C — Tabla de medidas vacía

```dax
Medidas = {}
```

Crear con **Modelado → Nueva tabla**. Todas las medidas DAX van aquí.

---

## PASO 4 — Medidas DAX

> Todas las medidas se crean en la tabla `Medidas` (Modelado → Nueva medida, o click derecho sobre la tabla Medidas → Nueva medida).

---

### GRUPO 1 — KPIs Básicos (conductores)

```dax
// ─── Conductores únicos en el contexto actual ───────────────────────────────
Conductores = DISTINCTCOUNT(scorecards[driver_id])

// ─── Score ──────────────────────────────────────────────────────────────────
Score Promedio = AVERAGE(scorecards[score])

// ─── DNR ────────────────────────────────────────────────────────────────────
// dnr_dpmo_calc viene calculado en SQL (dnr/entregados*1.000.000)
DNR (DPMO) = AVERAGE(scorecards[dnr_dpmo_calc])
DNR Total   = SUM(scorecards[dnr])

// ─── DCR (en BD ya viene como dcr_pct = dcr*100) ────────────────────────────
DCR Promedio = AVERAGE(scorecards[dcr_pct])

// ─── POD ────────────────────────────────────────────────────────────────────
POD % = AVERAGE(scorecards[pod_pct])

// ─── CC ─────────────────────────────────────────────────────────────────────
CC % = AVERAGE(scorecards[cc_pct])

// ─── RTS ────────────────────────────────────────────────────────────────────
RTS % = AVERAGE(scorecards[rts_pct])

// ─── CDF ────────────────────────────────────────────────────────────────────
CDF (DPMO) = AVERAGE(scorecards[cdf_dpmo_oficial])

// ─── FDPS ───────────────────────────────────────────────────────────────────
FDPS % = AVERAGE(scorecards[fdps_pct])

// ─── Entregados ─────────────────────────────────────────────────────────────
Entregados Total    = SUM(scorecards[entregados])
Entregados Promedio = AVERAGE(scorecards[entregados])

// ─── DSC ────────────────────────────────────────────────────────────────────
DSC (DPMO) = AVERAGE(scorecards[dsc_dpmo])

// ─── False Scans ────────────────────────────────────────────────────────────
FS Total = SUM(scorecards[fs_count])
```

---

### GRUPO 2 — Station KPIs (datos del PDF oficial Amazon)

```dax
// ─── Score global de estación ───────────────────────────────────────────────
Score Estación = AVERAGE(station_scorecards[overall_score])

Standing Estación =
VAR MaxFecha = MAX(station_scorecards[fecha_semana])
RETURN
    CALCULATE(
        FIRSTNONBLANK(station_scorecards[overall_standing], 1),
        station_scorecards[fecha_semana] = MaxFecha
    )

// ─── Ranking ─────────────────────────────────────────────────────────────────
Rank Estación =
VAR MaxFecha = MAX(station_scorecards[fecha_semana])
RETURN
    CALCULATE(
        MIN(station_scorecards[rank_station]),
        station_scorecards[fecha_semana] = MaxFecha
    )

Rank WoW =
VAR MaxFecha = MAX(station_scorecards[fecha_semana])
RETURN
    CALCULATE(
        MIN(station_scorecards[rank_wow]),
        station_scorecards[fecha_semana] = MaxFecha
    )

// ─── FICO ────────────────────────────────────────────────────────────────────
FICO Promedio = AVERAGE(station_scorecards[fico])

FICO Tier =
VAR MaxFecha = MAX(station_scorecards[fecha_semana])
RETURN
    CALCULATE(
        FIRSTNONBLANK(station_scorecards[fico_tier], 1),
        station_scorecards[fecha_semana] = MaxFecha
    )

// ─── WHC ─────────────────────────────────────────────────────────────────────
WHC % Estación = AVERAGE(station_scorecards[whc_pct])

// ─── DNR, LoR, DSC de estación ───────────────────────────────────────────────
DNR DPMO Estación = AVERAGE(station_scorecards[dnr_dpmo])
LoR DPMO Estación = AVERAGE(station_scorecards[lor_dpmo])
DSC DPMO Estación = AVERAGE(station_scorecards[dsc_dpmo])
CE DPMO Estación  = AVERAGE(station_scorecards[ce_dpmo])
CDF DPMO Estación = AVERAGE(station_scorecards[cdf_dpmo])

// ─── Áreas de foco (última semana disponible) ─────────────────────────────────
Focus Area 1 =
VAR MaxFecha = MAX(station_scorecards[fecha_semana])
RETURN
    CALCULATE(
        FIRSTNONBLANK(station_scorecards[focus_area_1], 1),
        station_scorecards[fecha_semana] = MaxFecha
    )

Focus Area 2 =
VAR MaxFecha = MAX(station_scorecards[fecha_semana])
RETURN
    CALCULATE(
        FIRSTNONBLANK(station_scorecards[focus_area_2], 1),
        station_scorecards[fecha_semana] = MaxFecha
    )

Focus Area 3 =
VAR MaxFecha = MAX(station_scorecards[fecha_semana])
RETURN
    CALCULATE(
        FIRSTNONBLANK(station_scorecards[focus_area_3], 1),
        station_scorecards[fecha_semana] = MaxFecha
    )
```

---

### GRUPO 3 — Distribución de Calificaciones

```dax
// ─── Conteos ─────────────────────────────────────────────────────────────────
N Fantastic = CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "💎 FANTASTIC")
N Great     = CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "🥇 GREAT")
N Fair      = CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "⚠️ FAIR")
N Poor      = CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "🛑 POOR")

// ─── Porcentajes ──────────────────────────────────────────────────────────────
% Fantastic = DIVIDE([N Fantastic], [Conductores], 0)
% Great     = DIVIDE([N Great],     [Conductores], 0)
% Fair      = DIVIDE([N Fair],      [Conductores], 0)
% Poor      = DIVIDE([N Poor],      [Conductores], 0)
```

> Formatear `% Fantastic`, `% Great`, `% Fair`, `% Poor` como **Porcentaje** en el panel Formato de medida.

---

### GRUPO 4 — Alertas y Semáforos

```dax
// ─── Alerta DNR (en DPMO) ─────────────────────────────────────────────────────
Alerta DNR =
IF([DNR (DPMO)] > 1650, "CRÍTICO",
   IF([DNR (DPMO)] > 833,  "ATENCIÓN", "OK"))

// ─── Alerta Score ─────────────────────────────────────────────────────────────
Alerta Score =
IF([Score Promedio] < 60, "POOR",
   IF([Score Promedio] < 80, "FAIR", "OK"))

// ─── Conductores en riesgo (FAIR o POOR) ─────────────────────────────────────
Conductores en Riesgo =
CALCULATE(
    COUNTROWS(scorecards),
    scorecards[calificacion] IN {"⚠️ FAIR", "🛑 POOR"}
)

% en Riesgo = DIVIDE([Conductores en Riesgo], [Conductores], 0)

// ─── Conductores POOR en 2 o más semanas (acumulado en el contexto actual) ────
Conductores POOR Acumulado =
VAR Drivers_POOR =
    CALCULATETABLE(
        VALUES(scorecards[driver_id]),
        scorecards[calificacion] = "🛑 POOR"
    )
RETURN
    COUNTROWS(
        FILTER(
            Drivers_POOR,
            CALCULATE(
                DISTINCTCOUNT(scorecards[semana]),
                scorecards[calificacion] = "🛑 POOR"
            ) >= 2
        )
    )

// ─── Conductores con Score < umbral crítico ────────────────────────────────────
Conductores Score Crítico =
CALCULATE(
    DISTINCTCOUNT(scorecards[driver_id]),
    scorecards[score] < 60
)
```

---

### GRUPO 5 — Comparativas Temporales

> Estas medidas usan `fecha_semana` (tipo DATE), no strings, para evitar bugs de ordenación lexicográfica ("W9" > "W10" pero W09 < W10).

```dax
// ─── Score semana anterior ────────────────────────────────────────────────────
Score Semana Anterior =
VAR FechaActual   = MAX(scorecards[fecha_semana])
VAR FechaAnterior =
    MAXX(
        FILTER(ALL(scorecards[fecha_semana]),
               scorecards[fecha_semana] < FechaActual),
        scorecards[fecha_semana]
    )
RETURN
    CALCULATE(
        [Score Promedio],
        ALL(scorecards[fecha_semana]),
        scorecards[fecha_semana] = FechaAnterior
    )

// ─── Delta Score vs semana anterior ──────────────────────────────────────────
Score Delta vs Anterior =
VAR Anterior = [Score Semana Anterior]
RETURN IF(ISBLANK(Anterior), BLANK(), [Score Promedio] - Anterior)

// ─── DNR semana anterior ───────────────────────────────────────────────────────
DNR Semana Anterior =
VAR FechaActual   = MAX(scorecards[fecha_semana])
VAR FechaAnterior =
    MAXX(
        FILTER(ALL(scorecards[fecha_semana]),
               scorecards[fecha_semana] < FechaActual),
        scorecards[fecha_semana]
    )
RETURN
    CALCULATE(
        [DNR (DPMO)],
        ALL(scorecards[fecha_semana]),
        scorecards[fecha_semana] = FechaAnterior
    )

// ─── Delta DNR ────────────────────────────────────────────────────────────────
DNR Delta vs Anterior =
VAR Anterior = [DNR Semana Anterior]
RETURN IF(ISBLANK(Anterior), BLANK(), [DNR (DPMO)] - Anterior)

// ─── DCR semana anterior ──────────────────────────────────────────────────────
DCR Semana Anterior =
VAR FechaActual   = MAX(scorecards[fecha_semana])
VAR FechaAnterior =
    MAXX(
        FILTER(ALL(scorecards[fecha_semana]),
               scorecards[fecha_semana] < FechaActual),
        scorecards[fecha_semana]
    )
RETURN
    CALCULATE(
        [DCR Promedio],
        ALL(scorecards[fecha_semana]),
        scorecards[fecha_semana] = FechaAnterior
    )

DCR Delta vs Anterior =
VAR Anterior = [DCR Semana Anterior]
RETURN IF(ISBLANK(Anterior), BLANK(), [DCR Promedio] - Anterior)
```

---

### GRUPO 6 — Comparativas por Centro

```dax
// ─── DNR vs empresa (promedio de todos los centros) ───────────────────────────
DNR vs Empresa =
VAR DNR_Centro  = [DNR (DPMO)]
VAR DNR_Empresa = CALCULATE([DNR (DPMO)], ALL(Centros))
RETURN DNR_Centro - DNR_Empresa

// ─── Score vs empresa ─────────────────────────────────────────────────────────
Score vs Empresa =
VAR Score_Centro  = [Score Promedio]
VAR Score_Empresa = CALCULATE([Score Promedio], ALL(Centros))
RETURN Score_Centro - Score_Empresa

// ─── Mejor centro (mayor Score Promedio en el contexto actual) ────────────────
Mejor Centro =
VAR Resumen =
    ADDCOLUMNS(
        VALUES(scorecards[centro]),
        "ScoreCentro", CALCULATE([Score Promedio])
    )
VAR MaxScore = MAXX(Resumen, [ScoreCentro])
RETURN MINX(FILTER(Resumen, [ScoreCentro] = MaxScore), scorecards[centro])

// ─── Peor centro ─────────────────────────────────────────────────────────────
Peor Centro =
VAR Resumen =
    ADDCOLUMNS(
        VALUES(scorecards[centro]),
        "ScoreCentro", CALCULATE([Score Promedio])
    )
VAR MinScore = MINX(Resumen, [ScoreCentro])
RETURN MINX(FILTER(Resumen, [ScoreCentro] = MinScore), scorecards[centro])

// ─── Score empresa (promedio global, sin filtro de centro) ────────────────────
Score Global Empresa = CALCULATE([Score Promedio], ALL(Centros))
DNR Global Empresa   = CALCULATE([DNR (DPMO)],     ALL(Centros))
```

---

### GRUPO 7 — Rankings

```dax
// ─── Ranking conductor por Score (Dense: sin saltos en caso de empate) ────────
Ranking Conductor =
RANKX(
    ALL(scorecards[driver_name]),
    [Score Promedio],
    ,
    DESC,
    Dense
)

// ─── Indicador Top 10% ───────────────────────────────────────────────────────
Es Top 10% =
VAR TotalConductores = DISTINCTCOUNT(scorecards[driver_name])
VAR Umbral           = ROUNDUP(TotalConductores * 0.1, 0)
RETURN IF([Ranking Conductor] <= Umbral, "Top 10%", "")

// ─── Semanas en POOR (para un conductor concreto en contexto actual) ──────────
Semanas en POOR =
CALCULATE(
    DISTINCTCOUNT(scorecards[semana]),
    scorecards[calificacion] = "🛑 POOR"
)

// ─── Ranking Score por centro ─────────────────────────────────────────────────
Ranking Centro =
RANKX(
    ALL(scorecards[centro]),
    [Score Promedio],
    ,
    DESC,
    Dense
)
```

---

### GRUPO 8 — WHC (Working Hours Compliance)

```dax
// ─── Conductores con al menos una infracción WHC ──────────────────────────────
Conductores WHC =
CALCULATE(
    DISTINCTCOUNT(wh_exceptions[driver_id]),
    FILTER(
        wh_exceptions,
           wh_exceptions[daily_limit_exceeded]   = 1
        || wh_exceptions[weekly_limit_exceeded]  = 1
        || wh_exceptions[under_offwork_limit]    = 1
        || wh_exceptions[workday_limit_exceeded] = 1
    )
)

// ─── Totales por tipo de infracción ───────────────────────────────────────────
WHC Daily Exceeded   = SUM(wh_exceptions[daily_limit_exceeded])
WHC Weekly Exceeded  = SUM(wh_exceptions[weekly_limit_exceeded])
WHC Under Offwork    = SUM(wh_exceptions[under_offwork_limit])
WHC Workday Exceeded = SUM(wh_exceptions[workday_limit_exceeded])

// ─── Total infracciones (todas las categorías) ────────────────────────────────
WHC Total Infracciones =
    [WHC Daily Exceeded]
  + [WHC Weekly Exceeded]
  + [WHC Under Offwork]
  + [WHC Workday Exceeded]

// ─── % conductores sin infracción WHC ────────────────────────────────────────
WHC Compliance % =
VAR TotalConductores = [Conductores]
VAR ConInfracciones  = [Conductores WHC]
RETURN DIVIDE(TotalConductores - ConInfracciones, TotalConductores, 1)

// ─── WHC % desde station_scorecards (dato oficial Amazon) ────────────────────
WHC % Oficial = AVERAGE(station_scorecards[whc_pct])
```

---

### GRUPO 9 — False Scan y FDPS

```dax
// ─── False Scans ─────────────────────────────────────────────────────────────
FS Total = SUM(scorecards[fs_count])

Conductores con FS =
CALCULATE(
    DISTINCTCOUNT(scorecards[driver_id]),
    scorecards[fs_count] > 0
)

FS Promedio por Conductor = DIVIDE([FS Total], [Conductores], 0)

// ─── FDPS (Fantastic DSP Score) ───────────────────────────────────────────────
FDPS Promedio = AVERAGE(scorecards[fdps_pct])

// ─── Score Global (medida de resumen ejecutivo) ───────────────────────────────
// Esta es la medida principal que ya existe en el .pbix actual.
// Si necesitas recrearla:
Score Global = AVERAGE(scorecards[score])
```

---

## PASO 5 — Diseño de 5 páginas (1920 × 1080)

> Todas las páginas usan resolución **1920 × 1080** (Widescreen 16:9).
> Ir a **Ver → Tamaño de página → Personalizado → 1920 × 1080** antes de añadir visuals.

---

### Página 1 — Resumen Ejecutivo

**Objetivo:** vista de un vistazo del estado de la semana para el responsable de flota.

**Layout (coordenadas aproximadas):**

```
┌─────────────────────────────────────────────────────────────────────┐
│ Slicers (izq)    │    KPI Row 1: Score | Standing | Rank | FICO      │
│ Año (dropdown)   │─────────────────────────────────────────────────── │
│ Semana (lista)   │    KPI Row 2: WHC%  | DNR DPMO | DCR% | POD%      │
│ Centro (multi)   │─────────────────────────────────────────────────── │
│                  │  Area chart Score      │  Donut calificaciones      │
│                  │  (eje: fecha_semana)   │  (% Fantastic/Great/…)     │
│                  │─────────────────────────────────────────────────── │
│                  │  Pivot: centro × semana, valor = Score Promedio     │
└─────────────────────────────────────────────────────────────────────┘
```

**Visuals detallados:**

| Visual | Tipo | Campos / Configuración |
|--------|------|----------------------|
| Slicer Año | Slicer desplegable | `scorecards[anio]` |
| Slicer Semana | Slicer lista | `scorecards[semana]` (ordenado por `fecha_semana`) |
| Slicer Centro | Slicer lista multi | `Centros[centro]` |
| Score Global | Tarjeta | `Score Global` · formato: sin decimales · color condicional |
| Standing | Tarjeta | `Standing Estación` |
| Rank Estación | Tarjeta | `Rank Estación` |
| FICO | Tarjeta | `FICO Promedio` |
| WHC % | Tarjeta | `WHC % Oficial` · formato % |
| DNR DPMO | Tarjeta | `DNR (DPMO)` · color condicional rojo >1650 |
| DCR % | Tarjeta | `DCR Promedio` · formato % |
| POD % | Tarjeta | `POD %` · formato % |
| Tendencia Score | Gráfico de área | Eje X: `fecha_semana` · Y: `Score Promedio` · línea referencia 80 |
| Distribución | Gráfico de anillo | Leyenda: `calificacion` · Valores: `Conductores` |
| Tabla resumen | Tabla dinámica | Filas: `centro` · Columnas: `semana` · Valores: `Score Promedio` · formato condicional |

**Configuración gráfico de área (Score):**
- Línea de referencia constante en **80** (color verde `#63BE7B`)
- Color de la línea: degradado rojo→amarillo→verde con stops 55, 70, 100
- Marcadores activados para cada semana

---

### Página 2 — Análisis por Centro

**Objetivo:** comparar centros entre sí y encontrar los mejores conductores.

**Slicers:** `Centros[centro]` (multi-selección) · `scorecards[anio]` · `scorecards[semana]`

| Visual | Tipo | Campos |
|--------|------|--------|
| Mejor Centro | Tarjeta | `Mejor Centro` |
| Peor Centro | Tarjeta | `Peor Centro` |
| Score vs Empresa | Tarjeta | `Score vs Empresa` · formato: +/- |
| DNR vs Empresa | Tarjeta | `DNR vs Empresa` |
| Barras Score | Gráfico barras horizontal | Eje Y: `centro` · X: `Score Promedio` · color condicional |
| Dispersión DNR vs Score | Gráfico de dispersión | X: `DNR (DPMO)` · Y: `Score Promedio` · Tamaño: `Entregados Total` · Color: `calificacion` · Detalle: `driver_name` |
| Top 15 conductores | Tabla | `driver_name`, `Score Promedio`, `DNR (DPMO)`, `DCR Promedio`, `calificacion` · formato condicional Score |
| Tarjetas | Tarjetas | `Conductores`, `Conductores en Riesgo`, `% en Riesgo` |

**Configuración dispersión:**
- Cuadrantes manuales: líneas X en 1650 DPMO, líneas Y en 80 (Score)
- Cuadrante superior-izquierda = bueno (bajo DNR, alto Score)
- Cuadrante inferior-derecha = POOR (alto DNR, bajo Score)

---

### Página 3 — Drill-down Conductores

**Objetivo:** análisis histórico de un conductor concreto semana a semana.

**Slicers:** `scorecards[driver_name]` (búsqueda) · `scorecards[centro]` · `scorecards[anio]`

| Visual | Tipo | Campos |
|--------|------|--------|
| Score conductor | Tarjeta | `Score Promedio` |
| DNR conductor | Tarjeta | `DNR (DPMO)` |
| DCR conductor | Tarjeta | `DCR Promedio` |
| Semanas POOR | Tarjeta | `Semanas en POOR` |
| Ranking | Tarjeta | `Ranking Conductor` |
| Historial Score+DNR | Gráfico líneas (doble eje) | Eje X: `fecha_semana` · Y izq: `Score Promedio` · Y der: `DNR (DPMO)` |
| Tabla detallada | Tabla | `semana`, `anio`, `centro`, `score`, `dnr_dpmo_calc`, `dcr_pct`, `pod_pct`, `calificacion`, `entregados` |
| Dispersión vs flota | Dispersión | X: `DNR (DPMO)` · Y: `Score Promedio` · resaltar conductor seleccionado |
| Delta Score | Tarjeta | `Score Delta vs Anterior` · flecha arriba/abajo con formato condicional |

**Truco:** en el slicer `driver_name`, usar **Tipo: Búsqueda** (search box) para acceder rápido a cualquier conductor por nombre.

---

### Página 4 — WHC & Compliance

**Objetivo:** control de infracciones de horas de trabajo (Working Hours Compliance).

**Slicers:** `Centros[centro]` · `scorecards[semana]` · `scorecards[anio]`

| Visual | Tipo | Campos |
|--------|------|--------|
| Conductores WHC | Tarjeta | `Conductores WHC` |
| WHC % Oficial | Tarjeta | `WHC % Oficial` · formato % |
| Total Infracciones | Tarjeta | `WHC Total Infracciones` |
| Compliance % | Tarjeta | `WHC Compliance %` · color condicional |
| Barras por tipo | Gráfico barras agrupadas | Categorías: tipos de infracción (Daily, Weekly, Offwork, Workday) · Valores: sumas correspondientes |
| Tabla infracciones | Tabla | `driver_name`, `centro`, `semana`, `daily_limit_exceeded`, `weekly_limit_exceeded`, `under_offwork_limit`, `workday_limit_exceeded` · filtrar filas > 0 |
| Tendencia WHC% | Gráfico líneas | Eje X: `fecha_semana` · Y: `WHC % Oficial` · línea referencia 95% |
| Distribución por centro | Barras apiladas | Centro vs tipos de infracción |

**Para la tabla de infracciones:** usar un filtro de nivel visual en `WHC Total Infracciones > 0` para mostrar solo los conductores con alguna infracción.

**Para las barras por tipo:** crear una tabla de datos estructurada en Power Query o usar medidas individuales como valores de un visual de "multi-row card":
```
WHC Daily Exceeded   → "Límite Diario"
WHC Weekly Exceeded  → "Límite Semanal"
WHC Under Offwork    → "Descanso Insuficiente"
WHC Workday Exceeded → "Jornada Excedida"
```

---

### Página 5 — Tendencias & Alertas

**Objetivo:** vista ejecutiva de evolución temporal y conductores en situación de alerta.

**Slicers:** `Centros[centro]` (multi) · `scorecards[anio]`

| Visual | Tipo | Campos |
|--------|------|--------|
| Líneas multi-centro Score | Gráfico líneas | Eje X: `fecha_semana` · Y: `Score Promedio` · Leyenda: `centro` |
| Líneas multi-centro DNR | Gráfico líneas | Eje X: `fecha_semana` · Y: `DNR (DPMO)` · Leyenda: `centro` |
| Heatmap Score | Matriz | Filas: `centro` · Columnas: `semana` · Valores: `Score Promedio` · formato condicional |
| Tabla POOR 2+ semanas | Tabla | Filtrar con `Semanas en POOR >= 2`: `driver_name`, `Semanas en POOR`, `Score Promedio`, `centro`, `fecha_semana` |
| Conductores POOR Acum. | Tarjeta | `Conductores POOR Acumulado` |
| Score Delta | Tarjeta | `Score Delta vs Anterior` |
| DNR Delta | Tarjeta | `DNR Delta vs Anterior` |

**Para la tabla POOR 2+ semanas:** añadir filtro de nivel visual `Semanas en POOR >= 2` en el panel Filtros del visual (arrastrar medida `Semanas en POOR` al panel Filtros y poner condición >= 2).

**Configuración heatmap:** en Formato → Formato condicional → aplicar escala de colores con los mismos umbrales que en PASO 6.

---

## PASO 6 — Formato Condicional (umbrales exactos)

### Score (0–100)

| Rango | Color fondo | Color texto | Código hex |
|-------|------------|------------|-----------|
| < 60  | Rojo | Blanco | `#F8696B` |
| 60–79 | Amarillo | Negro | `#FFEB84` |
| ≥ 80  | Verde | Negro | `#63BE7B` |

**Cómo aplicar en una tabla:**
1. Click en columna de Score en la tabla
2. **Herramientas de columna → Formato condicional → Color de fondo → Reglas**
3. Añadir regla: Si valor < 60 → `#F8696B`
4. Añadir regla: Si valor >= 60 y < 80 → `#FFEB84`
5. Añadir regla: Si valor >= 80 → `#63BE7B`

**Para tarjetas KPI:** en Formato → Color del valor de datos → Formato condicional → usar el mismo esquema.

### DNR (en DPMO)

| Rango | Color | Hex |
|-------|-------|-----|
| > 1650 DPMO | Rojo | `#F8696B` |
| 833–1650 DPMO | Amarillo | `#FFEB84` |
| < 833 DPMO | Verde | `#63BE7B` |

> Los umbrales 833 y 1650 DPMO corresponden a los tiers Fair/Good/Fantastic de Amazon (equivalen a ~0.083% y ~0.165% de error respectivamente).

### DCR y POD (en %)

| Rango | Color |
|-------|-------|
| < 99% | Rojo `#F8696B` |
| 99%–99.5% | Amarillo `#FFEB84` |
| ≥ 99.5% | Verde `#63BE7B` |

### WHC % (Compliance)

| Rango | Color |
|-------|-------|
| < 85% | Rojo `#F8696B` |
| 85%–95% | Amarillo `#FFEB84` |
| ≥ 95% | Verde `#63BE7B` |

### Gráfico de área Score (Página 1)

Configurar colores de fondo de área con gradiente:
- Stop 0% del eje: rojo `#F8696B`
- Stop 70 (= 70% de 100): amarillo `#FFEB84`
- Stop 100% del eje: verde `#63BE7B`

Línea de referencia en 80: color `#63BE7B`, estilo discontinuo, etiqueta "Meta: 80".

---

## PASO 7 — Tema Amazon/Winiw JSON

Guardar como `tema_winiw_amazon.json` e importar con **Ver → Temas → Examinar temas**:

```json
{
  "name": "Winiw Amazon Quality",
  "dataColors": [
    "#FF9900",
    "#146EB4",
    "#232F3E",
    "#43A047",
    "#E53935",
    "#FB8C00",
    "#8E24AA",
    "#00ACC1"
  ],
  "good": "#63BE7B",
  "neutral": "#FFEB84",
  "bad": "#F8696B",
  "maximum": "#63BE7B",
  "center": "#FFEB84",
  "minimum": "#F8696B",
  "null": "#8C8C8C",
  "background": "#FFFFFF",
  "foreground": "#232F3E",
  "tableAccent": "#FF9900",
  "visualStyles": {
    "*": {
      "*": {
        "fontFamily": [{ "value": "Segoe UI" }],
        "fontSize": [{ "value": 11 }],
        "color": [{ "solid": { "color": "#232F3E" } }]
      }
    },
    "card": {
      "*": {
        "calloutValue": [{ "fontSize": { "value": 28 }, "fontBold": [{ "value": true }] }],
        "categoryLabel": [{ "color": { "solid": { "color": "#595959" } } }]
      }
    },
    "slicer": {
      "*": {
        "header": [{ "fontColor": { "solid": { "color": "#FF9900" } }, "outline": [{ "value": "None" }] }]
      }
    },
    "lineChart": {
      "*": {
        "lineWidth": [{ "value": 2 }],
        "markerEnabled": [{ "value": true }]
      }
    },
    "barChart": {
      "*": {
        "dataLabelColor": [{ "solid": { "color": "#232F3E" } }]
      }
    }
  }
}
```

---

## PASO 8 — Refresh automático desde Supabase

### En Power BI Service (cloud)

1. **Archivo → Publicar → Mi área de trabajo** (requiere cuenta Power BI Pro o PPU)
2. En Power BI Service (app.powerbi.com):
   - Ir al dataset publicado → **Configuración**
   - **Credenciales de origen de datos → Editar**:
     - Método de autenticación: **Básico**
     - Usuario: usuario de Supabase (`postgres` o el tuyo)
     - Contraseña: contraseña del proyecto Supabase
3. **Actualización programada** → Activar:
   - Frecuencia: **Diaria** o **Por hora** (hasta 8 actualizaciones/día en Pro, 48 en PPU)
   - Zona horaria: **Madrid** (UTC+1/UTC+2)
   - Hora: p.ej. 08:00, 12:00, 16:00
4. **Enviar notificación de error** → activar con tu email

> Supabase Pooler (puerto 6543) es compatible con Power BI Service directamente, sin necesidad de Gateway, siempre que el proyecto Supabase tenga IP allowing habilitado o esté en modo público.

### Con Power BI Gateway (si Supabase requiere IP fija)

Si Supabase tiene allowlist de IPs y Power BI Service no tiene IP fija:
1. Descargar **Power BI On-Premises Data Gateway (modo estándar)** en el servidor/PC de la empresa
2. Instalar y asociar con tu cuenta Power BI
3. En Power BI Service → Dataset → Configuración → **Conexión de puerta de enlace** → seleccionar el gateway instalado

### Refresh desde Power BI Desktop (manual)

**Inicio → Actualizar** — actualiza todos los datos desde Supabase en el archivo local.

---

## PASO 9 — RLS por Centro (Row-Level Security)

Permite que cada responsable de centro vea solo sus datos.

### Crear roles en Power BI Desktop

1. **Modelado → Administrar roles → Nuevo rol**
2. Crear un rol por centro (o un rol dinámico):

**Opción A — Rol dinámico (recomendado):**
```dax
// En la tabla Centros, añadir este filtro al rol "RolCentro":
[centro] = LOOKUPVALUE(
    usuarios_centro[centro],  -- tabla adicional: email → centro
    usuarios_centro[email], USERPRINCIPALNAME()
)
```

**Opción B — Filtro simple (si el UPN contiene el código de centro):**
```dax
// En tabla scorecards:
[centro] = MID(USERPRINCIPALNAME(), 1, FIND("@", USERPRINCIPALNAME()) - 1)
```

**Opción C — Rol estático por centro (más sencillo):**
```dax
// Rol "Centro_DMA15":
scorecards[centro] = "DMA15"
```
Repetir para cada centro. En Power BI Service → Dataset → Seguridad → asignar cada persona al rol de su centro.

### Probar RLS

**Modelado → Ver como → seleccionar rol** — verifica que los datos se filtran correctamente antes de publicar.

### Publicar con RLS

1. Publicar el informe
2. Power BI Service → Dataset → **Seguridad**
3. Asignar usuarios/grupos de Microsoft 365 a cada rol

---

## PASO 10 — Compartir el informe

### Opción A — Link directo (usuarios internos con licencia)
Power BI Service → Archivo → **Compartir** → introducir emails → nivel "Puede ver"

### Opción B — Embed en aplicación web interna
```html
<iframe
  width="100%"
  height="700"
  src="https://app.powerbi.com/reportEmbed?reportId=TU_REPORT_ID&autoAuth=true&ctid=TU_TENANT_ID"
  frameborder="0"
  allowFullScreen="true">
</iframe>
```

### Opción C — Exportar a PDF
Power BI Service → **Exportar → PDF** — genera un snapshot estático del informe.

---

## Checklist Final Completo

### Conexión y datos
- [ ] Consulta `df_estaciones` eliminada de Power Query
- [ ] Tabla `scorecards` conectada a Supabase con la SQL del PASO 1B
- [ ] Tabla `station_scorecards` conectada con SQL del PASO 1C
- [ ] Tabla `wh_exceptions` conectada con SQL del PASO 1D
- [ ] Tipos de datos corregidos en Power Query (fecha_semana = Fecha, anio = Entero, etc.)
- [ ] Las 3 tablas cargan sin errores (verde en Power Query)

### Modelo
- [ ] Tabla `Centros` creada con `DISTINCT(SELECTCOLUMNS(...))`
- [ ] 3 relaciones Centros → scorecards / station_scorecards / wh_exceptions creadas
- [ ] `semana` ordenado por `fecha_semana` en las 3 tablas
- [ ] Tabla `Medidas` creada (vacía)

### Medidas DAX
- [ ] GRUPO 1: KPIs Básicos (Conductores, Score, DNR, DCR, POD, CC, CDF, FDPS, Entregados) sin errores
- [ ] GRUPO 2: Station KPIs (Score Estación, Standing, Rank, FICO, WHC, DNR/LoR/DSC DPMO)
- [ ] GRUPO 3: Distribución calificaciones (N y % de cada una)
- [ ] GRUPO 4: Alertas (Alerta DNR, Score, Conductores en Riesgo, POOR Acumulado)
- [ ] GRUPO 5: Comparativas temporales (Score/DNR Semana Anterior, Deltas)
- [ ] GRUPO 6: Comparativas por centro (Mejor/Peor Centro, vs Empresa)
- [ ] GRUPO 7: Rankings (Ranking Conductor, Top 10%, Semanas en POOR)
- [ ] GRUPO 8: WHC (Conductores WHC, tipos, Total, Compliance %)
- [ ] GRUPO 9: False Scan y FDPS

### Páginas
- [ ] Página 1 — Resumen Ejecutivo: 8 tarjetas KPI + gráfico área + donut + pivot
- [ ] Página 2 — Análisis por Centro: barras + dispersión + tabla top 15
- [ ] Página 3 — Drill-down Conductores: slicer driver + historial líneas + tabla
- [ ] Página 4 — WHC & Compliance: tabla infracciones + barras por tipo + tendencia
- [ ] Página 5 — Tendencias & Alertas: multi-líneas + heatmap + tabla POOR 2+ semanas

### Formato
- [ ] Formato condicional Score: rojo <60, amarillo 60-79, verde >=80
- [ ] Formato condicional DNR: rojo >1650, amarillo 833-1650, verde <833
- [ ] Formato condicional DCR/POD: rojo <99%, amarillo 99-99.5%, verde >=99.5%
- [ ] Formato condicional WHC: rojo <85%, amarillo 85-95%, verde >=95%
- [ ] Tema Amazon/Winiw importado
- [ ] Línea de referencia 80 en gráfico Score

### Publicación
- [ ] Informe publicado en Power BI Service
- [ ] Credenciales de Supabase configuradas en el dataset
- [ ] Refresh automático programado
- [ ] RLS configurado (si aplica)
- [ ] Informe compartido con las personas correctas

---

## Referencia rápida — Columnas y sus unidades

| Columna BD | Fuente | Unidad en BD | Cómo usarla en Power BI |
|-----------|--------|-------------|------------------------|
| `dcr`, `pod`, `cc`, `rts`, `cdf`, `fdps` | `scorecards` | Decimal 0-1 | SQL ya los convierte a % (dcr_pct etc.) |
| `dcr_pct`, `pod_pct`… | `scorecards` (calculado en SQL) | % (0-100) | AVERAGE directo, formatear como número decimal con 2 decimales |
| `score` | `scorecards` | 0-100 float | AVERAGE directo |
| `dnr_dpmo_calc` | `scorecards` (calculado en SQL) | DPMO (entero) | AVERAGE directo |
| `dnr` | `scorecards` | Count de eventos | SUM para total |
| `entregados` | `scorecards` | Paquetes entregados | SUM para total |
| `overall_score` | `station_scorecards` | 0-100 float | AVERAGE directo |
| `whc_pct` | `station_scorecards` | % (0-100) | AVERAGE directo |
| `dnr_dpmo`, `lor_dpmo`, `dsc_dpmo`, `cdf_dpmo` | `station_scorecards` | DPMO | AVERAGE directo |
| `daily_limit_exceeded` etc. | `wh_exceptions` | 0 o 1 (boolean int) | SUM para contar infracciones |

---

## Notas de rendimiento

- Con **modo Importar** y 57.000 registros/año: carga < 3 segundos, visuals instantáneos.
- Con **DirectQuery**: cada visual lanza una query SQL a Supabase. Supabase tiene índices en `(semana, centro, anio)` — respuesta ~1-2 segundos por visual.
- Las columnas calculadas en SQL (DPMO, porcentajes) son más eficientes que calcularlas en DAX o Power Query para datasets grandes.
- Si el informe se vuelve lento: usar **Optimizador de rendimiento** (Vista → Optimizador de rendimiento) para identificar medidas DAX lentas.

---

## Solución de problemas frecuentes

**"No se puede conectar a Supabase"**
- Verificar host y puerto (6543 para Pooler, 5432 para directo)
- Comprobar que Supabase tiene `Password authentication` habilitada en Settings → Database
- En Power BI Service: el Gateway puede ser necesario si hay firewall de empresa

**"La semana W10 aparece antes que W09"**
- Olvidaste hacer "Ordenar por columna → fecha_semana" (PASO 3B)

**"El gráfico de líneas tiene huecos entre puntos"**
- Estás usando `Calendario[Fecha]` como eje — usa `scorecards[fecha_semana]` en su lugar

**"La medida devuelve BLANK() inesperadamente"**
- Comprobar que el contexto de filtro tiene datos (el slicer no filtra a cero registros)
- Revisar que las relaciones están activas en el modelo

**"Los emojis de calificación no coinciden"**
- Los valores en BD son exactamente: `"💎 FANTASTIC"`, `"🥇 GREAT"`, `"⚠️ FAIR"`, `"🛑 POOR"` (con espacio después del emoji)
- Copiar y pegar desde aquí directamente en el código DAX

**"Conductores POOR Acumulado devuelve 0"**
- Esta medida necesita contexto de múltiples semanas. Asegúrate de que el slicer de semana no está filtrado a una sola semana.

---

*Winiw Quality Scorecard · [@pablo25rf](https://github.com/pablo25rf) · Marzo 2026*
