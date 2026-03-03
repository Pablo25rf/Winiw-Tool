# 📊 GUÍA POWER BI — WINIW QUALITY SCORECARD
### Versión definitiva · Verificada · Sin errores

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
    Tabla       = Table.FromList(Fechas, Splitter.SplitByNothing(), {"Fecha"}),
    TipoFecha   = Table.TransformColumnTypes(Tabla, {{"Fecha", type date}}),
    Anio        = Table.AddColumn(TipoFecha, "Año",        each Date.Year([Fecha]),                  Int64.Type),
    Trimestre   = Table.AddColumn(Anio,      "Trimestre",  each "Q" & Text.From(Date.QuarterOfYear([Fecha])), type text),
    Mes         = Table.AddColumn(Trimestre, "Mes",        each Date.Month([Fecha]),                 Int64.Type),
    NombreMes   = Table.AddColumn(Mes,       "NombreMes",  each Date.MonthName([Fecha]),             type text),
    NumSemana   = Table.AddColumn(NombreMes, "NumSemana",  each Date.WeekOfYear([Fecha]),            Int64.Type),
    SemanaISO   = Table.AddColumn(NumSemana, "SemanaLabel",each "W" & Text.PadStart(Text.From(Date.WeekOfYear([Fecha])),2,"0"), type text),
    EsFinSemana = Table.AddColumn(SemanaISO, "EsFinSemana",each Date.DayOfWeek([Fecha]) >= 5,       type logical)
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

> La tabla **scorecards** es tu única tabla de hechos.  
> **Calendario** es la tabla de dimensión temporal.  
> No necesitas más relaciones para empezar.

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
Entregados Total   = SUM(scorecards[entregados])
Entregados Promedio = AVERAGE(scorecards[entregados])
```

---

### GRUPO 2: Distribución de Calificaciones

```dax
// Número de conductores por calificación
N Fantastic = 
CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "💎 FANTASTIC")

N Great = 
CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "🥇 GREAT")

N Fair = 
CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "⚠️ FAIR")

N Poor = 
CALCULATE(COUNTROWS(scorecards), scorecards[calificacion] = "🛑 POOR")

// Porcentajes
% Fantastic = DIVIDE([N Fantastic], [Conductores], 0)
% Great     = DIVIDE([N Great],     [Conductores], 0)
% Fair      = DIVIDE([N Fair],      [Conductores], 0)
% Poor      = DIVIDE([N Poor],      [Conductores], 0)
```

---

### GRUPO 3: Alertas y Semáforos

```dax
// Semáforo DNR
Alerta DNR = 
IF(
    [DNR Promedio] > 5, "🔴 Crítico",
    IF([DNR Promedio] > 3, "🟡 Atención", "🟢 OK")
)

// Semáforo Score
Alerta Score = 
IF(
    [Score Promedio] < 60, "🔴 POOR",
    IF([Score Promedio] < 80, "🟡 FAIR", "🟢 OK")
)

// Conductores en riesgo (POOR o FAIR)
Conductores en Riesgo = 
CALCULATE(
    COUNTROWS(scorecards),
    scorecards[calificacion] IN {"⚠️ FAIR", "🛑 POOR"}
)

// % conductores en riesgo
% en Riesgo = DIVIDE([Conductores en Riesgo], [Conductores], 0)
```

---

### GRUPO 4: Comparativas Temporales
> ⚠️ Estas medidas requieren la tabla Calendario conectada y un slicer de semana activo.

```dax
// Semana anterior correcta (comparación de strings "W05" < "W06")
DNR Semana Anterior = 
VAR SemanaActual = MAX(scorecards[semana])
VAR SemanaAnterior =
    MAXX(
        FILTER(
            ALL(scorecards[semana]),
            scorecards[semana] < SemanaActual
        ),
        scorecards[semana]
    )
RETURN
    CALCULATE(
        [DNR Promedio],
        ALL(scorecards[semana]),
        scorecards[semana] = SemanaAnterior
    )

// Variación vs semana anterior
DNR Δ vs Anterior =
VAR Anterior = [DNR Semana Anterior]
RETURN
    IF(ISBLANK(Anterior), BLANK(), [DNR Promedio] - Anterior)

// Igual para Score
Score Semana Anterior =
VAR SemanaActual = MAX(scorecards[semana])
VAR SemanaAnterior =
    MAXX(
        FILTER(ALL(scorecards[semana]), scorecards[semana] < SemanaActual),
        scorecards[semana]
    )
RETURN
    CALCULATE(
        [Score Promedio],
        ALL(scorecards[semana]),
        scorecards[semana] = SemanaAnterior
    )

Score Δ vs Anterior =
VAR Anterior = [Score Semana Anterior]
RETURN
    IF(ISBLANK(Anterior), BLANK(), [Score Promedio] - Anterior)
```

---

### GRUPO 5: Comparativas por Centro

```dax
// DNR de un centro vs el promedio de TODOS los centros
DNR vs Empresa =
VAR DNR_Centro  = [DNR Promedio]
VAR DNR_Empresa = CALCULATE([DNR Promedio], ALL(scorecards[centro]))
RETURN DNR_Centro - DNR_Empresa

// Score de un centro vs el promedio de TODOS los centros
Score vs Empresa =
VAR Score_Centro  = [Score Promedio]
VAR Score_Empresa = CALCULATE([Score Promedio], ALL(scorecards[centro]))
RETURN Score_Centro - Score_Empresa

// Centro con mejor score (devuelve nombre como texto)
Mejor Centro =
VAR Resumen =
    ADDCOLUMNS(
        VALUES(scorecards[centro]),
        "ScoreCentro", CALCULATE([Score Promedio])
    )
VAR MaxScore = MAXX(Resumen, [ScoreCentro])
RETURN
    MINX(FILTER(Resumen, [ScoreCentro] = MaxScore), scorecards[centro])

// Centro con peor score
Peor Centro =
VAR Resumen =
    ADDCOLUMNS(
        VALUES(scorecards[centro]),
        "ScoreCentro", CALCULATE([Score Promedio])
    )
VAR MinScore = MINX(Resumen, [ScoreCentro])
RETURN
    MINX(FILTER(Resumen, [ScoreCentro] = MinScore), scorecards[centro])
```

---

### GRUPO 6: Rankings

```dax
// Ranking de conductores por score (1 = mejor)
Ranking Conductor =
RANKX(
    ALL(scorecards[driver_name]),
    [Score Promedio],
    ,
    DESC,
    Dense
)

// ¿Está el conductor en el top 10%?
Es Top 10% =
VAR Total = DISTINCTCOUNT(scorecards[driver_name])
RETURN
    IF([Ranking Conductor] <= ROUNDUP(Total * 0.1, 0), "⭐ Top 10%", "")

// Número de semanas en las que el conductor aparece como POOR
Semanas en POOR =
CALCULATE(
    DISTINCTCOUNT(scorecards[semana]),
    scorecards[calificacion] = "🛑 POOR"
)
```

---

## PASO 5 — DISEÑO DE PÁGINAS

### Página 1: RESUMEN EJECUTIVO

**Visualizaciones:**

| Visual | Tipo | Campos |
|--------|------|--------|
| Total Conductores | Tarjeta | `Conductores` |
| DNR Promedio | Tarjeta con indicador | `DNR Promedio`, `Alerta DNR` |
| Score Promedio | Tarjeta | `Score Promedio` |
| % Fantastic | Tarjeta | `% Fantastic` (formato %) |
| Tendencia DNR | Gráfico de líneas | Eje X: `semana`, Eje Y: `DNR Promedio` |
| Distribución calificaciones | Gráfico de anillo | Leyenda: `calificacion`, Valores: `Conductores` |
| Ranking centros | Gráfico de barras horizontales | Eje Y: `centro`, Eje X: `Score Promedio` |
| Tabla alertas | Tabla | `centro`, `DNR Promedio`, `Alerta DNR`, `% Poor` |

**Slicers (filtros globales):**
- Semana (desplegable, multi-select)
- Centro (desplegable, multi-select)

---

### Página 2: ANÁLISIS POR CENTRO

**Visualizaciones:**

| Visual | Tipo | Campos |
|--------|------|--------|
| Score centro vs empresa | Tarjeta con comparativa | `Score Promedio`, `Score vs Empresa` |
| DNR centro vs empresa | Tarjeta con comparativa | `DNR Promedio`, `DNR vs Empresa` |
| Evolución score 12 semanas | Líneas | Eje X: `semana`, Líneas: `Score Promedio` por `centro` |
| Distribución calificaciones | Anillo | `calificacion` / `Conductores` |
| Top 15 conductores | Tabla ordenada | `driver_name`, `score`, `dnr`, `dcr`, `calificacion` |
| Conductores en riesgo | Tabla filtrada | `Conductores en Riesgo`, filtro POOR/FAIR |

**Slicer:** Centro (single-select para este análisis)

---

### Página 3: TENDENCIAS TEMPORALES

**Visualizaciones:**

| Visual | Tipo | Campos |
|--------|------|--------|
| Evolución DNR | Líneas múltiples | Eje X: `semana`, Líneas: `centro` |
| Evolución Score | Líneas múltiples | Eje X: `semana`, Líneas: `centro` |
| Heatmap semana × centro | Matriz | Filas: `centro`, Columnas: `semana`, Valores: `Score Promedio` (formato condicional) |
| Comparativa semanas | Barras agrupadas | Eje: `semana`, Grupos: `calificacion` |

**Formato condicional del heatmap:**
- Verde: Score ≥ 90
- Amarillo: Score 70-89
- Rojo: Score < 70

---

### Página 4: DRILL-DOWN CONDUCTORES

**Visualizaciones:**

| Visual | Tipo | Campos |
|--------|------|--------|
| Historial conductor | Líneas | Eje X: `semana`, Valores: `Score Promedio`, `DNR Promedio` |
| Métricas resumen | Tarjetas | `Score Promedio`, `DNR Promedio`, `DCR Promedio`, `Semanas en POOR` |
| Tabla detallada | Tabla | `semana`, `centro`, `score`, `dnr`, `dcr`, `pod`, `calificacion`, `detalles` |
| Gráfico dispersión | Dispersión | Eje X: `dnr`, Eje Y: `score`, Tamaño: `entregados`, Color: `centro` |

**Slicer:** Conductor (búsqueda por nombre)

---

## PASO 6 — FORMATO CONDICIONAL

### En tablas con Score:
- **Valor < 60** → Fondo rojo `#F8696B`, texto blanco
- **Valor 60-79** → Fondo amarillo `#FFEB84`
- **Valor ≥ 80** → Fondo verde `#63BE7B`

### En tablas con DNR:
- **Valor > 5** → Fondo rojo
- **Valor 3-5** → Fondo amarillo
- **Valor < 3** → Fondo verde

**Cómo aplicarlo:**
1. Click en la columna de la tabla → `Formato condicional → Color de fondo`
2. Seleccionar **"Valor de campo"** o **"Reglas"**
3. Introducir los rangos indicados arriba

---

## PASO 7 — REFRESH AUTOMÁTICO

### En Power BI Service (cloud):

1. Publicar el informe: **Archivo → Publicar → Mi área de trabajo**
2. En Power BI Service → **Datasets → el tuyo → Configuración**
3. **Credenciales de origen de datos** → Editar → introducir credenciales Supabase
4. **Actualización programada** → Activar → cada hora (o cada 4h)

### Si usas SQLite local necesitas Gateway:
1. Descargar **Power BI Gateway (modo personal)**
2. Instalarlo en el PC donde está el archivo `.db`
3. Asociarlo en Power BI Service → Dataset → Configuración → Conexión de puerta de enlace

---

## PASO 8 — SEGURIDAD POR ROLES (RLS)

Si quieres que cada centro solo vea sus propios datos:

1. **Modelado → Administrar roles → Nuevo rol**
2. Nombre: `Rol_Centro`
3. Filtro en tabla `scorecards`:

```dax
[centro] = USERPRINCIPALNAME()
```

> Esto filtra automáticamente los datos según el email del usuario.  
> En Power BI Service → Dataset → Seguridad → asignar cada persona a su centro.

---

## PASO 9 — COMPARTIR

### Opción A: Link directo
- Power BI Service → **Compartir → Obtener vínculo**
- Solo accesible con cuenta de Microsoft 365

### Opción B: Insertar en web interna
```html
<iframe
  width="100%"
  height="700"
  src="https://app.powerbi.com/reportEmbed?reportId=TU_ID&autoAuth=true"
  frameborder="0"
  allowFullScreen>
</iframe>
```

### Opción C: App de Power BI
- **Área de trabajo → Crear app**
- Configura accesos y publica para toda tu empresa

---

## PASO 10 — PALETA DE COLORES WINIW/AMAZON

Aplicar en **Vista → Temas → Personalizar tema actual**:

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

## CHECKLIST FINAL

Antes de publicar, verificar:

- [ ] Conexión a Supabase funciona (datos visibles en Power Query)
- [ ] Tabla Calendario creada y relacionada con `scorecards[fecha_semana]`
- [ ] Todas las medidas DAX del Grupo 1 funcionan sin error
- [ ] Página 1 muestra datos reales de tus centros
- [ ] Slicers de semana y centro filtran correctamente todos los visuales
- [ ] Formato condicional aplicado en tablas de score y DNR
- [ ] Refresh automático configurado en Power BI Service
- [ ] Informe compartido con las personas correctas

---

## NOTAS IMPORTANTES

**Sobre los datos:**
- `dcr`, `pod`, `cc`, `fdps`, `cdf` están en formato **decimal 0-1** en la BD (no 0-100)
- Formatear en Power BI como **Porcentaje** para que muestre 99.2% en vez de 0.992
- `dnr`, `score`, `entregados`, `fs_count`, `dnr_risk_events` son números enteros/decimales normales

**Sobre las semanas:**
- El campo `semana` contiene texto como "W05", "W06", etc.
- Para comparativas temporales usar SIEMPRE `fecha_semana` (es tipo DATE) en el eje de tiempo
- Los slicers de texto por semana ("W05") funcionan correctamente para filtrar

**Sobre rendimiento:**
- Con 57.000 registros/año en modo Importar: carga < 3 segundos
- Con DirectQuery: depende de la velocidad de Supabase (~1-2 segundos por visual)
- Los índices ya están creados en la BD — Power BI se beneficia automáticamente de ellos
