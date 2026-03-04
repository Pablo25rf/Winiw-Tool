# 📋 Manual de Operación — Winiw Quality Scorecard v3.9

**Para:** Administradores y Jefes de Tráfico  
**Versión del sistema:** 3.9  
**Última actualización:** Marzo 2026  
**Autor:** [@pablo25rf](https://github.com/pablo25rf)

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

Tras **5 intentos fallidos** de login, la cuenta se bloquea automáticamente durante 15 minutos. El bloqueo es **persistente en base de datos** desde v3.9 — sobrevive reinicios del servidor y es efectivo en despliegues multi-worker.

Para desbloquear antes de que expire:

> **Administración → Gestión de Usuarios → Cuentas Bloqueadas → Desbloquear**

O directamente en SQL:
```sql
DELETE FROM login_attempts WHERE username = 'el_usuario';
```

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
- **Estado del sistema** — total registros, semanas en BD, semana activa (actualizado cada 60 s)
- **Selector de Centro y Semana** para el scorecard semanal
- **Botón 🔄 Refrescar Datos** — invalida toda la caché y recarga desde BD
- **Advertencia** si `bcrypt` no está instalado (el sistema usa SHA-256 como fallback)

### 2.3 Sesión y seguridad

- La sesión caduca por inactividad. Si la pantalla se queda en blanco, recarga y vuelve a entrar.
- Cada acción relevante (login, guardar datos, cambiar roles) queda registrada en el log del sistema.

---

## 3. Flujo de trabajo semanal — Admin

```
1. Descargar archivos de Amazon DSP Portal
2. Pestaña "🚀 Procesamiento" → subir archivos → procesar lote
3. Pestaña "📋 DSP Scorecard PDF" → subir PDF oficial → revisar tabla → guardar todos
4. Revisar "📊 Scorecard" para verificar datos
5. Compartir enlace con los JTs para que vean sus conductores
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

> 💡 Los datos se cachean 5 minutos. Si acabas de subir un lote y no aparece, pulsa **🔄 Refrescar Datos** en el sidebar.

---

## 5. Procesamiento de archivos

**Solo visible para Admin y Superadmin.**

### 5.1 Archivos requeridos por lote

Cada lote corresponde a **un centro + una semana**:

| Archivo | Formato | Descripción |
|---------|---------|-------------|
| Concessions | `.csv` o `.xlsx` | DNR por conductor |
| DSC-Concessions | `.csv` o `.xlsx` | DNR adicional (DSC) |
| Quality Overview | `.csv` o `.xlsx` | DCR, POD, CC por conductor |
| False Scan | `.html` | Falsas lecturas |
| DWC / IADC | `.csv` o `.html` | Datos de ruta y horas |
| FDPS | `.xlsx` o `.csv` | Paquetes fallidos |
| Daily Report | `.html` | Reporte diario |

> ⚠️ No todos los archivos son obligatorios. Si falta alguno, el sistema procesa con los que haya y marca las métricas ausentes como `—`.

### 5.2 Procesamiento

1. Introduce **Centro** (ej. `DIC1`) y **Semana** (ej. `W07`) — o deja en blanco para detección automática por nombre de archivo.
2. Arrastra o selecciona los archivos.
3. Pulsa **⚡ Procesar Lote**.
4. El sistema muestra: conductores procesados, warnings, errores.

### 5.3 Targets por centro

> **Procesamiento → Configurar Targets del Centro**

Targets por defecto:

| Métrica | Target |
|---------|--------|
| DNR | ≤ 0.5 por 1.000 |
| DCR | ≥ 99.5% |
| POD | ≥ 99.0% |
| CC | ≥ 99.0% |
| FDPS | ≥ 98.0% |
| RTS | ≤ 1.0% |

---

## 6. DSP Scorecard PDF

**Solo visible para Admin y Superadmin.**

### 6.1 Proceso

1. Arrastra uno o varios PDFs al selector.
2. El sistema los **parsea todos automáticamente** y muestra una tabla resumen: Centro, Semana/Año, Score, Standing, Rank, conductores extraídos, excepciones WHC.
3. Revisa que los datos son correctos.
4. Pulsa **💾 Guardar X PDFs** para guardar todos de una vez.

> v3.9: Los drivers se extraen de las páginas 3-4 del PDF. La tabla WHC se lee de la página 5. Bug anterior que incluía la página WHC en los drivers corregido.

### 6.2 ¿Qué guarda el PDF?

- Score oficial, standing, ranking WoW
- WHC%, DCR, DNR DPMO, LoR DPMO, FICO, POD con tiers
- Focus Areas indicados por Amazon
- Excepciones de horas de trabajo (WHC exceptions) con nombre de conductor

---

## 7. Scorecard semanal

**Visible para todos los roles.**

Los JTs ven solo su centro asignado y sus 2 semanas más recientes. Los admins pueden seleccionar cualquier centro y semana.

### 7.1 Selección

Usa el **sidebar** para seleccionar centro y semana.

### 7.2 Filtrar conductores

```
Todos (N) | 🛑 POOR (N) | ⚠️ FAIR (N) | 🥇 GREAT (N) | 💎 FANTASTIC (N)
```

### 7.3 Tarjeta por conductor

- Score y calificación con color
- Delta WoW (▲/▼ respecto a semana anterior)
- Mini-tendencia — últimos 6 scores
- Métricas detalladas con barra vs target
- Comparativa CSV vs PDF oficial si disponible
- Focus Areas de Amazon

### 7.4 Paginación

Si hay más de 20 conductores, aparecen los controles de paginación.

---

## 8. Histórico

**Visible para todos los roles.**

Filtros: centro, rango de semanas, conductor (nombre o ID), calificación.

Pulsa **🔍 Buscar** para aplicar. **⬇️ Descargar Excel** exporta todos los resultados (no solo la página actual).

---

## 9. Perfil

**Visible para todos los roles.**

Permite cambiar la contraseña propia. Requiere introducir la contraseña actual para confirmar.

---

## 10. Administración

**Solo visible para Admin y Superadmin.**

### 10.1 Gestión de usuarios

- Ver usuarios con rol, estado y centro asignado
- Crear, editar, activar/desactivar, eliminar usuarios
- Desbloquear cuentas bloqueadas por rate limiting
- Asignar centro a JTs

### 10.2 Zona Superadmin

Solo visible para `superadmin`:

- Estadísticas de BD
- Logs del sistema (últimas N líneas, descargable)
- Limpieza de duplicados y mantenimiento de BD
- Borrado selectivo por centro/semana
- Reset total (requiere escribir `CONFIRMAR` — irreversible)

---

## 11. Gestión de usuarios

### Crear un usuario

1. **Administración → Crear Nuevo Usuario**
2. Rellena usuario, contraseña temporal, rol
3. El usuario deberá cambiar la contraseña en su primer acceso

### Roles

| Rol | Descripción |
|-----|-------------|
| `superadmin` | Acceso total. No puede ser eliminado si es el único activo. |
| `admin` | Procesamiento, gestión de JTs, visualización completa. |
| `jt` | Solo visualización. Puede ver su centro asignado. |

---

## 12. Errores frecuentes y soluciones

| Síntoma | Causa | Solución |
|---------|-------|----------|
| Pantalla en blanco | Sesión caducada | Recarga y vuelve a entrar |
| "Error de conexión" en sidebar | Supabase no responde | Espera 30 s y pulsa 🔄 Refrescar |
| Datos no actualizados tras subir | Caché activa (TTL 5 min) | Pulsa 🔄 Refrescar Datos |
| "No se pudo procesar el PDF" | Formato no reconocido | Verifica que es el PDF oficial semanal de Amazon |
| Conductor con métricas `—` | Archivo de esa métrica no subido | Sube el archivo y reprocesa el lote |
| Login bloqueado | 5 intentos fallidos | Admin → Administración → Desbloquear |
| "RuntimeError: WINIW_ADMIN_USER not set" | Variables de entorno no configuradas | Definir `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS` |
| Score no coincide con PDF Amazon | CSV es semana completa; PDF puede ser parcial | Normal si el PDF es de mitad de semana |
| BD vacía después de redeployar | SQLite local no persiste entre deploys | Usar Supabase en producción |
| "bcrypt warning" en sidebar | bcrypt no instalado | Añadir `bcrypt>=4.1.0` a requirements.txt |
| Columna `anio` faltante | BD antigua pre-v3.9 | Migración automática al arrancar — no hace falta nada manual |

---

## 13. Glosario de métricas Amazon

| Sigla | Nombre completo | Target |
|-------|----------------|--------|
| **DNR** | Delivery Not Received | ≤ 0.5 por 1.000 entregas |
| **DCR** | Delivery Completion Rate | ≥ 99.5% |
| **POD** | Photo On Delivery | ≥ 99.0% |
| **CC** | Customer Contact | ≥ 99.0% |
| **FDPS** | Failed Delivery Package Score | ≥ 98.0% |
| **RTS** | Return To Station | ≤ 1.0% |
| **CDF** | Customer Delivery Feedback | ≥ 95.0% |
| **WHC** | Working Hours Compliance | — |
| **LoR** | Loss or Return DPMO | — |
| **FICO** | Feedback and Incentive Score | — |
| **WoW** | Week over Week | — |
| **DPMO** | Defects Per Million Opportunities | — |

### Calificaciones

| Calificación | Score |
|--------------|-------|
| 💎 FANTASTIC | ≥ 90 |
| 🥇 GREAT | 80–89 |
| ⚠️ FAIR | 60–79 |
| 🛑 POOR | < 60 |

---

*Winiw Quality Scorecard v3.9 · [@pablo25rf](https://github.com/pablo25rf) · Marzo 2026*
