# 📋 Manual de Operación Detallado — Winiw Quality Scorecard v3.8

**Para:** Administradores y Jefes de Tráfico  
**Versión del sistema:** 3.8  
**Última actualización:** Marzo 2026

---

## Índice

1. [Primeros pasos — acceso y contraseña](#1-primeros-pasos)
2. [Interfaz — pestañas y roles](#2-interfaz)
3. [Flujo de trabajo semanal — Admin](#3-flujo-semanal-admin)
4. [Pestaña: Dashboard Ejecutivo](#4-dashboard-ejecutivo)
5. [Pestaña: Procesamiento de archivos](#5-procesamiento)
6. [Pestaña: DSP Scorecard PDF](#6-dsp-scorecard-pdf)
7. [Pestaña: Scorecard semanal](#7-scorecard-semanal)
8. [Pestaña: Histórico](#8-historico)
9. [Pestaña: Perfil](#9-perfil)
10. [Pestaña: Administración](#10-administracion)
11. [Gestión de usuarios](#11-gestion-usuarios)
12. [Errores frecuentes y soluciones](#12-errores-frecuentes)
13. [Glosario de métricas Amazon](#13-glosario)

---

## 1. Primeros pasos

### 1.1 Acceso a la app

Abre la URL de la aplicación en el navegador (ej. `https://tu-app.streamlit.app` o `http://localhost:8501` en local).

Verás la pantalla de login. Introduce tu usuario y contraseña y pulsa **Entrar**.

### 1.2 Primer acceso — cambio de contraseña obligatorio

La primera vez que entres con el usuario superadmin, el sistema te redirigirá automáticamente a una pantalla de cambio de contraseña. **Esto es obligatorio** y no se puede saltar. La contraseña nueva debe tener al menos 8 caracteres.

### 1.3 Cuenta bloqueada

Tras **5 intentos fallidos** de login, la cuenta se bloquea automáticamente durante 30 minutos. Si necesitas desbloquearla antes, un administrador debe ir a:

> **Administración → Gestión de Usuarios → Cuentas Bloqueadas → Desbloquear**

---

## 2. Interfaz

### 2.1 Pestañas según rol

| Pestaña | Superadmin | Admin | JT |
|---------|:---:|:---:|:---:|
| 🏢 Dashboard Ejecutivo | ✅ | ✅ | ❌ |
| 🚀 Procesamiento | ✅ | ✅ | ❌ |
| 📋 DSP Scorecard PDF | ✅ | ✅ | ❌ |
| 📊 Scorecard | ✅ | ✅ | ✅ |
| 📈 Histórico | ✅ | ✅ | ✅ |
| 👤 Perfil | ✅ | ✅ | ✅ |
| 👑 Administración | ✅ | ✅ | ❌ |

### 2.2 Sidebar

El sidebar muestra:
- **Estadísticas rápidas** del sistema (total registros, semanas, última actualización)
- **Selector de Centro y Semana** para el scorecard
- **Botón 🔄 Refrescar Datos** — invalida todas las cachés y recarga desde la BD
- **Advertencia** si `bcrypt` no está instalado (el sistema usa SHA-256 como fallback)

### 2.3 Sesión y seguridad

- La sesión caduca por inactividad. Si la pantalla se queda en blanco, recarga y vuelve a entrar.
- Cada acción relevante (login, guardar datos, cambiar roles) queda registrada en el log del sistema.

---

## 3. Flujo de trabajo semanal — Admin

Este es el proceso estándar cada semana:

```
1. Descargar archivos de Amazon Seller Central / DSP Portal
2. Pestaña "🚀 Procesamiento" → subir archivos → procesar lote
3. Pestaña "📋 DSP Scorecard PDF" → subir PDF oficial → guardar todos
4. Revisar "📊 Scorecard" para verificar datos
5. Compartir enlace de la app con los JTs para que vean sus conductores
```

---

## 4. Dashboard Ejecutivo

**Solo visible para Admin y Superadmin.**

Muestra una vista global de todos los centros:

- **Tarjeta resumen** — score global medio, total FANTASTIC, total POOR
- **Ranking de centros** — con medalla 🥇🥈🥉 y delta WoW (semana anterior)
- **Tabla comparativa** — todas las métricas por centro en la semana más reciente
- **Gráfico de barras** — score medio por centro con colores por tier
- **Distribución histórica** — evolución de FANTASTIC/GREAT/FAIR/POOR por semana

> 💡 Los datos del dashboard se cachean 5 minutos. Si acabas de subir un lote y no aparece, pulsa **🔄 Refrescar Datos** en el sidebar.

---

## 5. Procesamiento de archivos

**Solo visible para Admin y Superadmin.**

### 5.1 Archivos requeridos por lote

Cada lote corresponde a **un centro + una semana**. Para procesarlo correctamente necesitas estos archivos de Amazon:

| Archivo | Formato | Descripción |
|---------|---------|-------------|
| Concessions | `.csv` o `.xlsx` | DNR por conductor |
| DSC-Concessions | `.csv` o `.xlsx` | DNR adicional (DSC) |
| Quality Overview | `.csv` o `.xlsx` | DCR, POD, CC por conductor |
| False Scan | `.html` | Falsas lecturas |
| DWC / IADC | `.csv` o `.html` | Datos de ruta |
| FDPS | `.xlsx` o `.csv` | Paquetes fallidos |
| Daily Report | `.html` | Reporte diario |

> ⚠️ No todos los archivos son obligatorios. Si falta alguno, el sistema procesa con los que haya y marca las métricas ausentes como `—`.

### 5.2 Procesamiento individual

1. Introduce **Centro** (ej. `DIC1`) y **Semana** (ej. `W07`) manualmente si el nombre de la carpeta no los incluye, o deja en blanco para que el sistema los detecte automáticamente del nombre de los archivos.
2. Arrastra o selecciona los archivos.
3. Pulsa **⚡ Procesar Lote**.
4. El sistema muestra un resumen: conductores procesados, warnings, errores.

### 5.3 Importación masiva por carpetas

Para procesar varios centros/semanas a la vez:

1. Organiza los archivos en subcarpetas con el nombre `CENTRO_SEMANA` (ej. `DIC1_W07/`).
2. Selecciona **todas** las subcarpetas a la vez en el selector.
3. Pulsa **📦 Importar Todas las Carpetas**.
4. Una barra de progreso muestra el avance. Al terminar, aparece un resumen con los lotes procesados y los que tuvieron errores.

### 5.4 Targets por centro

Cada centro puede tener sus propios objetivos. Para configurarlos:

> **Procesamiento → Configurar Targets del Centro**

Los targets por defecto (si no se configuran) son:

| Métrica | Target por defecto |
|---------|-------------------|
| DNR | ≤ 0.5 |
| DCR | ≥ 99.5% |
| POD | ≥ 99.0% |
| CC | ≥ 99.0% |
| FDPS | ≥ 98.0% |
| RTS | ≤ 1.0% |

---

## 6. DSP Scorecard PDF

**Solo visible para Admin y Superadmin.**

Aquí se suben los **PDFs oficiales semanales de Amazon** (los que Amazon envía directamente al DSP con el ranking de estación).

### 6.1 Proceso

1. Arrastra uno o varios PDFs al selector.
2. El sistema los **parsea todos automáticamente** y muestra una tabla resumen con: Centro, Semana/Año, Score, Standing, Rank, nº conductores extraídos, nº excepciones WHC.
3. Revisa que los datos son correctos.
4. Pulsa el botón **💾 Guardar X PDFs** para guardar todos de una vez.

> 💡 Si quieres ver el detalle de un PDF concreto (métricas completas, Focus Areas de Amazon), expande el panel correspondiente debajo de la tabla.

### 6.2 ¿Qué guarda el PDF?

- Score oficial de estación y standing (Fantastic/Great/Fair/Poor)
- Ranking de estación y variación WoW
- WHC, DCR, DNR DPMO, LoR DPMO, FICO, POD con sus tiers
- Focus Areas indicados por Amazon
- Datos individuales de conductores (si el PDF los incluye)
- Excepciones de horas de trabajo (WHC exceptions)

---

## 7. Scorecard semanal

**Visible para todos los roles.**

Vista principal del rendimiento de conductores. Los JTs ven solo su centro asignado (si tienen uno); los admins pueden seleccionar cualquier centro.

### 7.1 Selección de semana y centro

Usa el **sidebar** para seleccionar el centro y la semana. El desplegable solo muestra semanas con datos.

### 7.2 Resumen de la semana

En la parte superior aparece un resumen con:
- Score medio del centro
- Distribución FANTASTIC / GREAT / FAIR / POOR
- Comparativa con la semana anterior (WoW delta)

### 7.3 Filtrar conductores

Usa el **filtro horizontal** para ver solo una categoría:

```
Todos (N) | 🛑 POOR (N) | ⚠️ FAIR (N) | 🥇 GREAT (N) | 💎 FANTASTIC (N)
```

Haz clic en la categoría que quieras. Haz clic de nuevo en la misma para deseleccionar.

### 7.4 Tarjeta por conductor

Cada conductor muestra:
- **Score** y calificación con color
- **Delta WoW** — variación respecto a la semana anterior (▲/▼)
- **Mini-tendencia** — bolitas de colores con los últimos 6 scores
- **Métricas detalladas** — DNR, DCR, POD, CC, FDPS, RTS, CDF con barra de progreso vs target
- **Comparativa CSV vs PDF** — si hay datos del PDF oficial de Amazon, muestra la diferencia
- **Focus Areas de Amazon** — áreas de mejora indicadas en el PDF oficial

### 7.5 Paginación

Si hay más de 20 conductores, aparecen los controles de paginación. Los filtros de categoría resetean la página a 1 automáticamente.

---

## 8. Histórico

**Visible para todos los roles.**

Permite consultar y descargar datos históricos.

### 8.1 Filtros disponibles

- **Centro** — uno o varios
- **Semana** — rango
- **Conductor** — búsqueda por nombre o ID
- **Calificación** — FANTASTIC / GREAT / FAIR / POOR

Pulsa **🔍 Buscar** para aplicar los filtros. Los resultados se paginan de 50 en 50.

### 8.2 Descarga

El botón **⬇️ Descargar Excel** exporta todos los registros filtrados (no solo la página actual) en formato `.xlsx` con formato profesional.

---

## 9. Perfil

**Visible para todos los roles.**

Permite cambiar la contraseña propia. Requiere introducir la contraseña actual para confirmar.

---

## 10. Administración

**Solo visible para Admin y Superadmin.**

### 10.1 Gestión de usuarios

Desde aquí puedes:
- **Ver** todos los usuarios con su rol, estado y centro asignado
- **Crear** nuevos usuarios (Admin o JT)
- **Editar** el rol de un usuario existente
- **Activar / Desactivar** cuentas
- **Eliminar** usuarios permanentemente
- **Desbloquear** cuentas bloqueadas por intentos fallidos

> ⚠️ Solo el Superadmin puede crear o eliminar otros Admins. Un Admin solo puede gestionar JTs.

### 10.2 Asignación de centro a JTs

Los JTs pueden tener un **centro asignado** que limita lo que pueden ver en Scorecard e Histórico. Si un JT no tiene centro asignado, ve todos los centros.

Para asignar: **Administración → Asignar Centro a JT → selecciona usuario → selecciona centro → Guardar**.

### 10.3 Zona Superadmin

Solo visible para el rol `superadmin`. Contiene:

- **Estadísticas de BD** — total registros, semanas, espacio usado
- **Logs del sistema** — últimas N líneas del log, descargable
- **Configuración avanzada** — targets globales, tipo de BD
- **Gestión de BD** — limpieza de duplicados, mantenimiento, borrado selectivo por centro/semana, y zona de peligro (borrar todo el historial)

> ⛔ **"Borrar TODO el historial"** es IRREVERSIBLE. Requiere escribir `CONFIRMAR` en el campo de texto antes de activarse.

---

## 11. Gestión de usuarios

### 11.1 Crear un usuario nuevo

1. **Administración → Crear Nuevo Usuario**
2. Rellena: nombre de usuario, contraseña temporal, rol (`admin` o `jt`)
3. Pulsa **Crear Usuario**
4. El usuario recibirá la contraseña temporal y deberá cambiarla en su primer acceso

### 11.2 Contraseñas

- Mínimo 8 caracteres
- El sistema usa **bcrypt** si está instalado, SHA-256 como fallback
- Los usuarios pueden cambiar su propia contraseña en la pestaña **👤 Perfil**
- Los admins pueden resetear la contraseña de cualquier JT desde **Administración**

### 11.3 Roles

| Rol | Descripción |
|-----|-------------|
| `superadmin` | Acceso total. Solo puede haber uno activo. |
| `admin` | Procesamiento, gestión de JTs, visualización completa. |
| `jt` | Solo visualización. Puede ver su centro asignado. |

---

## 12. Errores frecuentes y soluciones

| Síntoma | Causa | Solución |
|---------|-------|----------|
| La app muestra pantalla en blanco | Sesión caducada | Recarga la página y vuelve a entrar |
| "Error de conexión" en sidebar | Supabase no responde | Espera 30s y pulsa 🔄 Refrescar. Si persiste, revisar credenciales en secrets.toml |
| Los datos no se actualizan tras subir archivos | Caché activa (TTL 5 min) | Pulsa 🔄 Refrescar Datos en el sidebar |
| "No se pudo procesar el PDF" | Formato de PDF no reconocido | Verifica que es el PDF oficial semanal de Amazon (no el mensual ni el de drivers) |
| Conductor aparece con métricas `—` | Archivo de esa métrica no subido | Sube el archivo correspondiente y reprocesa el lote |
| Login bloqueado | 5 intentos fallidos | Admin → Administración → Cuentas Bloqueadas → Desbloquear |
| "RuntimeError: WINIW_ADMIN_USER not set" | Variables de entorno no configuradas | Definir `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS` antes de arrancar |
| Score no coincide con PDF Amazon | Los datos del CSV son de la semana completa; el PDF puede ser parcial | Normal si el PDF es de mitad de semana |
| BD vacía después de redeployar | SQLite local no persiste entre deploys | Usar Supabase en producción |
| "bcrypt warning" en sidebar | bcrypt no instalado | Añadir `bcrypt>=4.1.0` a requirements.txt y redesplegar |

---

## 13. Glosario de métricas Amazon

| Sigla | Nombre completo | Descripción | Target |
|-------|----------------|-------------|--------|
| **DNR** | Delivery Not Received | Paquetes entregados no recibidos por el cliente | ≤ 0.5 por 1.000 |
| **DCR** | Delivery Completion Rate | % de entregas completadas sobre intentadas | ≥ 99.5% |
| **POD** | Photo On Delivery | % de entregas con foto de confirmación | ≥ 99.0% |
| **CC** | Customer Contact | Contacto del cliente (llamadas/mensajes) | ≥ 99.0% |
| **FDPS** | Failed Delivery Package Score | % de paquetes con entrega fallida gestionados | ≥ 98.0% |
| **RTS** | Return To Station | % de paquetes devueltos a estación sin intentar | ≤ 1.0% |
| **CDF** | Customer Delivery Feedback | Puntuación de feedback del cliente | ≥ 95.0% |
| **WHC** | Working Hours Compliance | Cumplimiento de horas de trabajo | — |
| **LoR** | Loss or Return DPMO | Pérdidas o devoluciones por millón de oportunidades | — |
| **FICO** | Feedback and Incentive Score | Puntuación combinada de feedback e incentivos Amazon | — |
| **WoW** | Week over Week | Variación respecto a la semana anterior | — |
| **DPMO** | Defects Per Million Opportunities | Métrica de defectos normalizada | — |

### Calificaciones Amazon

| Calificación | Score | Color |
|--------------|-------|-------|
| 💎 FANTASTIC | ≥ 90 | Verde |
| 🥇 GREAT | 80–89 | Azul |
| ⚠️ FAIR | 60–79 | Naranja |
| 🛑 POOR | < 60 | Rojo |

---

*Winiw Quality Scorecard v3.8 · Amazon DSP · Marzo 2026*
