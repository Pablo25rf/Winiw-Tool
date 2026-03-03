# 👑 SISTEMA SUPERADMIN - GUÍA COMPLETA

## 🎯 ¿QUÉ ES SUPERADMIN?

**Superadmin** es el rol de máximo nivel en el sistema. Solo el superadmin configurado en WINIW_ADMIN_USER tendrá este rol.

---

## 📊 JERARQUÍA DE ROLES

```
        👑 SUPERADMIN (configurado en WINIW_ADMIN_USER)
                 |
                 ├── Control total del sistema
                 ├── Gestionar admins
                 ├── Ver logs
                 └── Configuración avanzada
                       |
        🔑 ADMIN (Otros administradores)
                 |
                 ├── Procesar archivos
                 ├── Gestionar usuarios JT
                 └── Visualizar todo
                       |
        👔 JT (Jefes de Tráfico)
                 |
                 └── Solo visualización
```

---

## 🔐 PERMISOS DETALLADOS

### 👑 SUPERADMIN (Solo tú)

✅ **TODO lo que puede hacer Admin**
✅ **PLUS Exclusivo:**
- Crear/Eliminar otros Admins
- Promocionar Admin → Superadmin
- Ver logs del sistema en tiempo real
- Descargar logs completos
- Estadísticas avanzadas del sistema
- Configuración avanzada de BD
- Protección: Nadie puede eliminarte

### 🔑 ADMIN (Tus administradores)

✅ Procesar archivos Amazon
✅ Generar scorecards
✅ Descargar Excel
✅ Ver todo el histórico
✅ Crear/Eliminar usuarios JT
❌ **NO puede:**
- Crear otros Admins
- Eliminar Admins
- Ver logs del sistema
- Acceder a zona Superadmin

### 👔 JT (Jefes de Tráfico)

✅ Ver scorecards generados
✅ Ver histórico filtrado
✅ Buscar conductores
✅ Cambiar su propia contraseña
❌ **NO puede:**
- Procesar archivos
- Descargar nada
- Crear usuarios
- Acceder a administración

---

## 🚀 INSTALACIÓN

### Paso 1: Actualizar el repositorio

```bash
git pull origin main
```

La funcionalidad Superadmin está integrada en `app.py` desde v3.8 — no hay archivos separados.

### Paso 2: Reiniciar App

```bash
streamlit run app.py
```

### Paso 3: Login

Tu usuario superadmin (WINIW_ADMIN_USER) se crea automáticamente al arrancar la app.

```
Usuario: [WINIW_ADMIN_USER]
Contraseña: [WINIW_ADMIN_PASS] (cámbiala al entrar)
```

---

## 🎮 CÓMO USAR TUS PODERES DE SUPERADMIN

### 1️⃣ Crear un Admin

1. Ve a **"👑 Administración"**
2. Sección **"➕ Crear Nuevo Usuario"**
3. Rellena:
   - Usuario: `carlos`
   - Contraseña: `Admin2026`
   - **Rol: admin** ← Esta opción solo tú la ves
4. Crear Usuario

**Resultado**: Carlos puede procesar archivos y gestionar JTs, pero NO puede crear otros admins.

### 2️⃣ Crear un JT

1. Mismo proceso
2. **Rol: jt**
3. Crear Usuario

**Resultado**: Solo visualización, sin descargas.

### 3️⃣ Ver Logs del Sistema

1. Ve a **"👑 Administración"**
2. Baja hasta **"👑 Zona Superadmin (Solo tú)"**
3. Tab **"📝 Ver Logs"**
4. Puedes:
   - Ver últimas 10-500 líneas
   - Descargar logs completos
   - Ver errores y actividad

### 4️⃣ Promocionar Admin a Superadmin

⚠️ **ÚSALO CON CUIDADO** - Le das control total

1. **"👑 Zona Superadmin"**
2. Tab **"⚙️ Configuración"**
3. Expandir **"👑 Promocionar Admin a Superadmin"**
4. Ingresa nombre del admin
5. Promocionar

**Resultado**: Ese usuario ahora tiene tus mismos poderes.

### 5️⃣ Ver Estadísticas Avanzadas

1. **"👑 Zona Superadmin"**
2. Tab **"📊 Estadísticas Avanzadas"**
3. Verás:
   - Cuántos Superadmins hay
   - Cuántos Admins
   - Cuántos JTs
   - Total de registros en BD

---

## 🛡️ PROTECCIONES DE SEGURIDAD

### 1. No puedes eliminarte a ti mismo

```
🛑 No puedes eliminar al superadmin principal
```

Ni siquiera tú puedes borrarte accidentalmente.

### 2. Admins NO pueden eliminar otros admins

```
🛑 Solo Superadmins pueden eliminar Administradores
```

Un admin solo puede eliminar JTs.

### 3. Admins NO pueden crear otros admins

En su formulario de creación solo ven:
```
Rol: [ jt ]
ℹ️ Solo Superadmins pueden crear otros Administradores
```

### 4. Solo Superadmin ve la "Zona Superadmin"

Los admins normales NO ven:
- Logs del sistema
- Estadísticas avanzadas
- Configuración de promoción
- Zona exclusiva

---

## 🎨 INTERFAZ VISUAL

### Login

```
Usuario: [WINIW_ADMIN_USER]
Contraseña: ******

✅ Acceso concedido
```

### Sidebar (Barra Lateral)

```
👤 Usuario Activo
Nombre: [WINIW_ADMIN_USER]
Rol: 👑 Superadmin
```

### Pestaña Administración

Solo tú verás al final:

```
─────────────────────────────────
👑 Zona Superadmin (Solo tú)
─────────────────────────────────

📊 Estadísticas Avanzadas | 📝 Ver Logs | ⚙️ Configuración
```

---

## 📋 CASOS DE USO

### Caso 1: Contratar Nuevo Admin

**Situación**: Contratas a María como administradora.

**Pasos**:
1. Login como superadmin
2. Crear usuario:
   - Usuario: maria
   - Contraseña: Temp2026
   - Rol: **admin**
3. María puede ahora:
   - Procesar archivos
   - Crear JTs
   - Ver todo
4. María **NO** puede:
   - Crear otros admins
   - Verte a ti en la lista
   - Acceder a zona superadmin

### Caso 2: María Merece Ser Superadmin

**Situación**: María lleva 6 meses, confías en ella 100%.

**Pasos**:
1. Login como superadmin
2. "👑 Zona Superadmin" → Configuración
3. Promocionar Admin a Superadmin
4. Usuario: maria
5. Promocionar

**Resultado**: María ahora tiene control total igual que tú.

### Caso 3: Admin se Va de la Empresa

**Situación**: Carlos renuncia.

**Pasos**:
1. Login como superadmin
2. Eliminar Usuario
3. Usuario: carlos
4. Eliminar

**Resultado**: Carlos no puede acceder más. Sus datos procesados se mantienen.

### Caso 4: Investigar un Error

**Situación**: Algo falló al procesar archivos.

**Pasos**:
1. "👑 Zona Superadmin" → Ver Logs
2. Buscar líneas con "ERROR"
3. Ver qué pasó
4. Descargar logs para análisis detallado

---

## 🔄 MIGRACIÓN DESDE VERSIÓN ANTERIOR

### Si ya tienes usuarios en la BD:

**Escenario A: El usuario superadmin ya existe**

✅ **Automático**: Al arrancar la app, el usuario en WINIW_ADMIN_USER se crea/actualiza como superadmin

**Escenario B: Tienes otros admins**

✅ Siguen siendo "admin" (no superadmin)
✅ Mantienen sus permisos actuales
✅ NO pueden crear otros admins ahora

**Escenario C: Quieres hacer superadmin a alguien más**

Usa la función **"Promocionar Admin a Superadmin"**

---

## ⚠️ RECOMENDACIONES DE SEGURIDAD

### 1. Mínimos Superadmins

Recomendado: **1-2 máximo**
- Solo personas de máxima confianza
- Idealmente solo tú

### 2. Cambiar Contraseña Inicial

```
[WINIW_ADMIN_PASS] → TuContraseñaFuerte123!
```

Al primer login, el sistema te fuerza a cambiarla.

### 3. No Compartir Credenciales

Cada persona debe tener su propio usuario.

### 4. Revisar Logs Regularmente

Los logs muestran:
- Quién procesó archivos
- Errores del sistema
- Actividad sospechosa

### 5. Backup de Base de Datos

```bash
# Backup antes de cambios importantes
cp amazon_quality.db amazon_quality_backup_$(date +%Y%m%d).db
```

---

## 📊 COMPARACIÓN DE VERSIONES

| Aspecto | Versión Anterior | Con Superadmin |
|---------|------------------|----------------|
| Roles | 2 (admin, jt) | 3 (superadmin, admin, jt) |
| Admin puede crear admins | ✅ Sí | ❌ No |
| Admin puede ver logs | ❌ No | ❌ No |
| Protección usuario principal | ❌ No | ✅ Sí |
| Zona exclusiva | ❌ No | ✅ Sí (superadmin) |
| Promoción de roles | ❌ No | ✅ Sí (superadmin) |

---

## 🆘 PROBLEMAS COMUNES

### "No veo la zona Superadmin"

**Causa**: No eres superadmin

**Solución**: Verifica que tu usuario sea el configurado en WINIW_ADMIN_USER, o que hayas sido promovido.

```python
# Verificar en BD
import sqlite3
conn = sqlite3.connect('amazon_quality.db')
cursor = conn.cursor()
cursor.execute("SELECT username, role FROM users")
print(cursor.fetchall())
conn.close()
```

### "No puedo crear usuarios admin"

**Causa**: Eres admin, no superadmin

**Solución**: Solo superadmins pueden crear otros admins. Es intencional por seguridad.

### "Quiero cambiar a alguien de JT a Admin"

**Solución**: 
1. Como superadmin, elimina el usuario JT
2. Créalo de nuevo como admin

O directamente en BD:
```sql
UPDATE users SET role = 'admin' WHERE username = 'juan';
```

---

## 🎉 BENEFICIOS DEL SISTEMA

### 1. Control Total

Tú decides quién tiene qué permisos.

### 2. Seguridad

Nadie puede crear admins sin tu autorización.

### 3. Trazabilidad

Los logs muestran toda la actividad.

### 4. Escalabilidad

Puedes tener:
- 1 Superadmin (tú)
- 5 Admins (tus managers)
- 20 JTs (operaciones)

### 5. Protección

Imposible eliminarte accidentalmente.

---

## 📝 CHECKLIST DE IMPLEMENTACIÓN

- [ ] Backup de archivos actuales
- [ ] Reemplazar con versión Superadmin
- [ ] Reiniciar app
- [ ] Login como superadmin (WINIW_ADMIN_USER)
- [ ] Cambiar contraseña
- [ ] Verificar que ves "👑 Zona Superadmin"
- [ ] Probar crear un admin
- [ ] Probar crear un JT
- [ ] Revisar logs
- [ ] Verificar estadísticas

---

## 🚀 ¡LISTO!

Ahora eres el **único Superadmin** del sistema. Tienes control total y nadie más puede crear administradores sin tu autorización.

**Archivos a usar**:
- `app.py` — aplicación principal (incluye funcionalidad Superadmin)
- `amazon_scorecard_ultra_robust_v3_FINAL.py` — motor de procesamiento

**¿Preguntas?** Todo está documentado arriba. 😊

---

**Versión**: 3.1 SUPERADMIN  
**Fecha**: Marzo 2026  
**Nivel de Seguridad**: 👑 MÁXIMO
