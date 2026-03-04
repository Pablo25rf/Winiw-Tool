# 📊 Guía Power BI — Winiw Quality Scorecard v3.9
### Versión definitiva · Verificada · Sin errores

> Autor: [@pablo25rf](https://github.com/pablo25rf)

---

## PASO 1 — CONEXIÓN A LA BASE DE DATOS

### Opción A: PostgreSQL / Supabase (Recomendado)

1. Abrir **Power BI Desktop**
2. **Inicio → Obtener datos → Base de datos → PostgreSQL**
3. Introducir:

```
Servidor:        aws-0-us-west-1.pooler.supabase.com:6543
Base de datos:   postgres
```

4. En **Opciones avanzadas → Instrucción SQL**, pegar:

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
    dcr,
    pod,
    cc,
    fdps,
    rts,
    cdf,
    -- columnas del PDF oficial
    entregados_oficial,
    dcr_oficial,
    pod_oficial,
    cc_oficial,
    cdf_dpmo_oficial,
    dsc_dpmo,
    lor_dpmo,
    detalles,
    uploaded_by,
    timestamp
FROM scorecards
ORDER BY fecha_semana DESC
```

5. Modo de conectividad: **Importar** (más rápido) o **DirectQuery** (tiempo real)

> ⚠️ Para **DirectQuery** necesitas Power BI Premium o Premium Per User.
> Para uso normal, **Importar** con refresh automático cada hora es suficiente.

---

### Opción B: SQLite Local

1. **Inicio → Obtener datos → Más… → Base de datos → ODBC**
2. Instalar driver SQLite ODBC: https://www.ch-werner.de/sqliteodbc/
3. DSN: `Driver=SQLite3 ODBC Driver;Database=C:\ruta\amazon_quality.db`

---

## PASO 2 — TABLA CALENDARIO (OBLIGATORIA)

Sin esta tabla, las comparativas temporales no funcionarán bien.

1. **Inicio → Transformar datos → Power Query Editor**
2. **Inicio → Nueva consulta → Consulta en blanco**
3. En la barra de fórmulas pegar:

```powerquery
let
    FechaInicio = #date(2025, 1, 1),
    FechaFin    = #date(2027, 12, 31),
    NumDias     = Duration.Days(FechaFin - FechaInicio) + 1,
    Fechas      = List.Dates(FechaInicio, NumDias, #duration(1,0,0,0)),
    Tabla       = Table.FromList(Fechas, Splitter.SplitByNothing(), {\"Fecha\"}),
    TipoFecha   = Table.TransformColumnTypes(Tabla, {{\"Fecha\", type date}}),
    Anio        = Table.AddColumn(TipoFecha, \"Año\",        each Date.Year([Fecha]),                  Int64.Type),
    Trimestre   = Table.AddColumn(Anio,      \"Trimestre\",  each \"Q\" & Text.From(Date.QuarterOfYear([Fecha])), type text),
    NumSemana   = Table.AddColumn(Trimestre, \"NúmSemana\",  each Date.WeekOfYear([Fecha]),            Int64.Type),
    SemanaISO   = Table.AddColumn(NumSemana, \"SemanaLabel\",each \"W\" & Text.PadStart(Text.From(Date.WeekOfYear([Fecha])),2,\"0\"), type text),
    EsFinSemana = Table.AddColumn(SemanaISO, \"EsFinSemana\",each Date.DayOfWeek([Fecha]) >= 5,       type logical)
in
    EsFinSemana
```

4. Renombrar la consulta como **"Calendario"**
5. Cerrar y aplicar

---

## PASO 3 — MODELO DE DATOS Y RELACIONES

En la vista **Modelo**, crear estas relaciones:

```
Calendario[Fecha]  →  scorecards[fecha_semana]   (1:N, activa)
```

> v3.9: También puedes filtrar por la columna `anio` directamente en `scorecards` — es un entero (2026) que Power BI puede usar en slicers sin necesitar la tabla Calendario.

---

## PASO 4 — MEDIDAS DAX

Crear una tabla vacía llamada **"Medidas"** (Modelado → Nueva tabla → `Medidas = {}`).
Añadir todas las medidas aquí para tenerlas organizadas.

---

### GRUPO 1: KPIs Básicos

```dax
// ─── Total de conductores únicos en el contexto actual ───
Conductores = DISTINCTCOUNT(scorecards[driver_id])

// ─── DNR ───
DNR Promedio = AVERAGE(scorecards[dnr])
DNR Total    = SUM(scorecards[dnr])

// ─── Score ───
Score Promedio = AVERAGE(scorecards[score])

// ─── Métricas de calidad (están en formato 0-1 en la BD) ───
DCR Promedio  = AVERAGE(scorecards[dcr])
POD Promedio  = AVERAGE(scorecards[pod])
CC Promedio   = AVERAGE(scorecards[cc])
FDPS Promedio = AVERAGE(scorecards[fdps])
RTS Promedio  = AVERAGE(scorecards[rts])
CDF Promedio  = AVERAGE(scorecards[cdf])

// ─── Entregados ───
Entregados Total    = SUM(scorecards[entregados])
Entregados Promedio = AVERAGE(scorecards[entregados])

// ─── Filtro rápido por año (usando columna anio de v3.9) ───
Anio Actual = MAX(scorecards[anio])
```

---

### GRUPO 2: Distribución de Calificaciones

```dax
N Fantastic = CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "💎 FANTASTIC")
N Great     = CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "🥇 GREAT")
N Fair      = CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "⚠️ FAIR")
N Poor      = CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "🛑 POOR")

% Fantastic = DIVIDE([N Fantastic], [Conductores], 0)
% Great     = DIVIDE([N Great],     [Conductores], 0)
% Fair      = DIVIDE([N Fair],      [Conductores], 0)
% Poor      = DIVIDE([N Poor],      [Conductores], 0)
```

---

### GRUPO 3: Alertas y Semáforos

```dax
Alerta DNR =
IF([DNR Promedio] > 5, "🔴 Crítico",
   IF([DNR Promedio] > 3, "🟡 Atención", "🟢 OK"))

Alerta Score =
IF([Score Promedio] < 60, "🔴 POOR",
   IF([Score Promedio] < 80, "🟡 FAIR", "🟢 OK"))

Conductores en Riesgo =
CALCULATE(COUNTROWS(scorecards),
    scorecards[calificacion] IN {"⚠️ FAIR", "🛑 POOR"})

% en Riesgo = DIVIDE([Conductores en Riesgo], [Conductores], 0)
```

---

### GRUPO 4: Comparativas Temporales

> ⚠️ Estas medidas requieren la tabla Calendario conectada y un slicer de semana activo.

```dax
// Semana anterior por fecha (evita comparación lexicográfica de strings)
DNR Semana Anterior =
VAR FechaActual = MAX(scorecards[fecha_semana])
VAR FechaAnterior =
    MAXX(
        FILTER(ALL(scorecards[fecha_semana]),
               scorecards[fecha_semana] < FechaActual),
        scorecards[fecha_semana]
    )
RETURN
    CALCULATE([DNR Promedio],
              ALL(scorecards[fecha_semana]),
              scorecards[fecha_semana] = FechaAnterior)

DNR Δ vs Anterior =
VAR Anterior = [DNR Semana Anterior]
RETURN IF(ISBLANK(Anterior), BLANK(), [DNR Promedio] - Anterior)

Score Semana Anterior =
VAR FechaActual   = MAX(scorecards[fecha_semana])
VAR FechaAnterior =
    MAXX(FILTER(ALL(scorecards[fecha_semana]),
                scorecards[fecha_semana] < FechaActual),
         scorecards[fecha_semana])
RETURN
    CALCULATE([Score Promedio],
              ALL(scorecards[fecha_semana]),
              scorecards[fecha_semana] = FechaAnterior)

Score Δ vs Anterior =
VAR Anterior = [Score Semana Anterior]
RETURN IF(ISBLANK(Anterior), BLANK(), [Score Promedio] - Anterior)
```

> v3.9: Usa `fecha_semana` (tipo DATE) en vez de `semana` (texto) para comparativas temporales. Evita bugs de ordenación lexicográfica ("W9" > "W10").

---

### GRUPO 5: Comparativas por Centro

```dax
DNR vs Empresa =
VAR DNR_Centro  = [DNR Promedio]
VAR DNR_Empresa = CALCULATE([DNR Promedio], ALL(scorecards[centro]))
RETURN DNR_Centro - DNR_Empresa

Score vs Empresa =
VAR Score_Centro  = [Score Promedio]
VAR Score_Empresa = CALCULATE([Score Promedio], ALL(scorecards[centro]))
RETURN Score_Centro - Score_Empresa

Mejor Centro =
VAR Resumen =
    ADDCOLUMNS(VALUES(scorecards[centro]),
               "ScoreCentro", CALCULATE([Score Promedio]))
VAR MaxScore = MAXX(Resumen, [ScoreCentro])
RETURN MINX(FILTER(Resumen, [ScoreCentro] = MaxScore), scorecards[centro])

Peor Centro =
VAR Resumen =
    ADDCOLUMNS(VALUES(scorecards[centro]),
               "ScoreCentro", CALCULATE([Score Promedio]))
VAR MinScore = MINX(Resumen, [ScoreCentro])
RETURN MINX(FILTER(Resumen, [ScoreCentro] = MinScore), scorecards[centro])
```

---

### GRUPO 6: Rankings

```dax
Ranking Conductor =
RANKX(ALL(scorecards[driver_name]), [Score Promedio], , DESC, Dense)

Es Top 10% =
VAR Total = DISTINCTCOUNT(scorecards[driver_name])
RETURN IF([Ranking Conductor] <= ROUNDUP(Total * 0.1, 0), "⭐ Top 10%", "")

Semanas en POOR =
CALCULATE(DISTINCTCOUNT(scorecards[semana]),
          scorecards[calificacion] = "🛑 POOR")
```

---

### GRUPO 7: WHC (v3.9 — datos de excepciones de horas)

```dax
// Conductores con al menos una excepción WHC
Conductores WHC =
CALCULATE(
    DISTINCTCOUNT(wh_exceptions[driver_id]),
    wh_exceptions[daily_limit_exceeded]  = 1
    || wh_exceptions[weekly_limit_exceeded] = 1
    || wh_exceptions[under_offwork_limit]   = 1
    || wh_exceptions[workday_limit_exceeded]= 1
)

// Si tienes la tabla wh_exceptions conectada (JOIN por semana+centro):
WHC Count = SUM(station_scorecards[wh_count])
```

---

## PASO 5 — DISEÑO DE PÁGINAS

### Página 1: Resumen Ejecutivo

| Visual | Tipo | Campos |
|--------|------|--------|
| Total Conductores | Tarjeta | `Conductores` |
| DNR Promedio | Tarjeta con indicador | `DNR Promedio`, `Alerta DNR` |
| Score Promedio | Tarjeta | `Score Promedio` |
| % Fantastic | Tarjeta | `% Fantastic` (formato %) |
| Tendencia DNR | Gráfico de líneas | Eje X: `fecha_semana`, Eje Y: `DNR Promedio` |
| Distribución calificaciones | Gráfico de anillo | `calificacion` / `Conductores` |
| Ranking centros | Barras horizontales | Eje Y: `centro`, Eje X: `Score Promedio` |
| Tabla alertas | Tabla | `centro`, `DNR Promedio`, `Alerta DNR`, `% Poor` |

**Slicers:** `anio` (entero, desplegable) · `semana` · `centro`

---

### Página 2: Análisis por Centro

| Visual | Tipo | Campos |
|--------|------|--------|
| Score vs empresa | Tarjeta | `Score Promedio`, `Score vs Empresa` |
| DNR vs empresa | Tarjeta | `DNR Promedio`, `DNR vs Empresa` |
| Evolución score 12 semanas | Líneas | Eje X: `fecha_semana`, por `centro` |
| Distribución calificaciones | Anillo | `calificacion` / `Conductores` |
| Top 15 conductores | Tabla | `driver_name`, `score`, `dnr`, `dcr`, `calificacion` |
| Conductores en riesgo | Tabla | filtro POOR/FAIR |

---

### Página 3: Tendencias Temporales

| Visual | Tipo | Campos |
|--------|------|--------|
| Evolución DNR | Líneas múltiples | Eje X: `fecha_semana`, por `centro` |
| Evolución Score | Líneas múltiples | Eje X: `fecha_semana`, por `centro` |
| Heatmap semana × centro | Matriz | Filas: `centro`, Columnas: `semana`, Valores: `Score Promedio` |
| Comparativa semanas | Barras agrupadas | Eje: `semana`, Grupos: `calificacion` |

---

### Página 4: Drill-down Conductores

| Visual | Tipo | Campos |
|--------|------|--------|
| Historial conductor | Líneas | Eje X: `fecha_semana`, Valores: `Score Promedio`, `DNR Promedio` |
| Métricas resumen | Tarjetas | `Score Promedio`, `DNR Promedio`, `DCR Promedio`, `Semanas en POOR` |
| Tabla detallada | Tabla | `semana`, `anio`, `centro`, `score`, `dnr`, `dcr`, `pod`, `calificacion` |
| Dispersión | Dispersión | Eje X: `dnr`, Eje Y: `score`, Tamaño: `entregados`, Color: `centro` |

---

## PASO 6 — FORMATO CONDICIONAL

### Columnas de Score:
- `< 60` → Fondo rojo `#F8696B`, texto blanco
- `60–79` → Fondo amarillo `#FFEB84`
- `≥ 80` → Fondo verde `#63BE7B`

### Columnas de DNR:
- `> 5` → Fondo rojo
- `3–5` → Fondo amarillo
- `< 3` → Fondo verde

**Cómo aplicarlo:** Click columna → `Formato condicional → Color de fondo → Reglas`

---

## PASO 7 — REFRESH AUTOMÁTICO

### Power BI Service (cloud):
1. Publicar: **Archivo → Publicar → Mi área de trabajo**
2. Power BI Service → **Datasets → el tuyo → Configuración**
3. **Credenciales de origen de datos** → Editar con credenciales Supabase
4. **Actualización programada** → Activar → cada hora

### SQLite local (requiere Gateway):
1. Descargar **Power BI Gateway (modo personal)**
2. Instalar en el PC donde está el `.db`
3. Asociar en Power BI Service → Dataset → Configuración → Puerta de enlace

---

## PASO 8 — SEGURIDAD POR ROLES (RLS)

Si quieres que cada centro solo vea sus propios datos:

1. **Modelado → Administrar roles → Nuevo rol**
2. Nombre: `Rol_Centro`
3. Filtro en tabla `scorecards`:

```dax
[centro] = USERPRINCIPALNAME()
```

En Power BI Service → Dataset → Seguridad → asigna cada persona a su centro.

---

## PASO 9 — COMPARTIR

### Link directo
Power BI Service → **Compartir → Obtener vínculo** (requiere cuenta Microsoft 365)

### Insertar en web interna
```html
<iframe
  width="100%"
  height="700"
  src="https://app.powerbi.com/reportEmbed?reportId=TU_ID&autoAuth=true"
  frameborder="0"
  allowFullScreen>
</iframe>
```

---

## PASO 10 — PALETA DE COLORES WINIW/AMAZON

**Vista → Temas → Personalizar tema actual:**

```json
{
  "name": "Winiw Amazon",
  "dataColors": ["#FF9900","#146EB4","#232F3E","#43A047","#E53935","#FB8C00","#8E24AA","#00ACC1"],
  "background": "#FFFFFF",
  "foreground": "#232F3E",
  "tableAccent": "#FF9900"
}
```

---

## Checklist final

- [ ] Conexión a Supabase funciona (datos visibles en Power Query)
- [ ] Tabla Calendario creada y relacionada con `scorecards[fecha_semana]`
- [ ] La columna `anio` aparece en Power Query (v3.9 — entero)
- [ ] Todas las medidas DAX del Grupo 1 funcionan sin error
- [ ] Página 1 muestra datos reales de tus centros
- [ ] Slicers de `anio`, `semana` y `centro` filtran correctamente
- [ ] Formato condicional aplicado en tablas de score y DNR
- [ ] Refresh automático configurado en Power BI Service
- [ ] Informe compartido con las personas correctas

---

## Notas importantes

**Sobre los datos:**
- `dcr`, `pod`, `cc`, `fdps`, `cdf` están en formato **decimal 0-1** en la BD (no 0-100)
- Formatear en Power BI como **Porcentaje** para que muestre 99.2% en vez de 0.992
- `dnr`, `score`, `entregados`, `fs_count` son números decimales normales
- `anio` es un entero (2026) — útil para slicers sin necesitar tabla Calendario

**Sobre las semanas:**
- El campo `semana` contiene texto: "W05", "W06", etc.
- Para comparativas temporales usar SIEMPRE `fecha_semana` (DATE) en el eje de tiempo
- Para filtros de usuario, el slicer de texto por `semana` es más intuitivo

**Sobre rendimiento:**
- Con 57.000 registros/año en modo Importar: carga < 3 segundos
- Con DirectQuery: ~1-2 segundos por visual (depende de Supabase)
- Los índices están creados en la BD — Power BI se beneficia automáticamente

---

*Winiw Quality Scorecard v3.9 · [@pablo25rf](https://github.com/pablo25rf) · Marzo 2026*
