# 👑 GUÍA SUPERADMIN — Quality Scorecard v3.9

> Autor: [@pablo25rf](https://github.com/pablo25rf)

---

## ¿Qué es Superadmin?

**Superadmin** es el rol de máximo nivel del sistema. Solo el usuario configurado en `QS_ADMIN_USER` tiene este rol por defecto. Puedes promover otros usuarios una vez dentro.

---

## Jerarquía de roles

```
        👑 SUPERADMIN
                 |
                 ├── Control total del sistema
                 ├── Gestionar admins y superadmins
                 ├── Ver y descargar logs
                 └── Configuración avanzada y reset de BD
                       |
        🔑 ADMIN
                 |
                 ├── Procesar archivos CSV/PDF
                 ├── Gestionar usuarios JT
                 └── Ver scorecards de todos los centros
                       |
        👔 JT (Jefe de Tráfico)
                 |
                 └── Solo visualización de su centro y semanas recientes
```

---

## Permisos detallados

### 👑 SUPERADMIN

- Todo lo que puede hacer Admin
- Crear y eliminar Admins y Superadmins
- Promocionar Admin → Superadmin
- Ver logs del sistema en tiempo real y descargarlos
- Estadísticas avanzadas de BD
- Reset total de base de datos (con confirmación)
- Protección: el sistema nunca permite eliminar al último superadmin activo

### 🔑 ADMIN

- Procesar archivos de Logística (CSV/Excel/PDF)
- Generar y descargar scorecards Excel
- Ver histórico completo de todos los centros
- Crear/eliminar/modificar usuarios JT
- **No puede** crear Admins, ver logs, acceder a la Zona Superadmin ni hacer reset de BD

### 👔 JT

- Ver el scorecard de su centro asignado
- Ver histórico filtrado a sus 2 semanas más recientes
- Buscar conductores
- Cambiar su propia contraseña
- **No puede** procesar archivos, descargar Excel, crear usuarios ni acceder a administración

---

## Primer acceso

Al arrancar la app por primera vez con `QS_ADMIN_USER` y `QS_ADMIN_PASS` definidas:

1. El usuario superadmin se crea automáticamente (solo si no existe)
2. Login con esas credenciales
3. **El sistema fuerza cambio de contraseña** en el primer login (`must_change_password = 1`)
4. Ya estás dentro con control total

---

## Operaciones frecuentes

### Crear un Admin

1. **Administración** → **Crear Nuevo Usuario**
2. Rellena usuario, contraseña y selecciona **Rol: admin**
3. Solo tú ves la opción `admin` en el desplegable — los admins solo pueden crear JTs

### Crear un JT y asignarle centro

1. **Administración** → **Crear Nuevo Usuario** → **Rol: jt**
2. Después, en Gestión de Usuarios, asigna el centro al JT

### Promover Admin a Superadmin

1. **Zona Superadmin** → **Configuración** → **Promocionar Admin a Superadmin**
2. Escribe el nombre de usuario y confirma
3. Ese usuario tendrá exactamente los mismos permisos que tú — úsalo con criterio

### Ver logs del sistema

1. **Zona Superadmin** → **Ver Logs**
2. Selecciona cuántas líneas mostrar (10–500)
3. Usa **Descargar logs** para análisis en detalle

### Investigar un error de procesamiento

1. Zona Superadmin → Ver Logs
2. Busca líneas con `ERROR`
3. El log incluye timestamp, usuario que realizó la acción y detalle del error

### Desbloquear una cuenta bloqueada por rate limiting

En v3.9 el rate limiting es persistente en BD (tabla `login_attempts`). Para desbloquear manualmente:

**Desde la interfaz:**  
Administración → Gestión de Usuarios → selecciona el usuario → Desbloquear

**Desde SQL (si no hay acceso a la app):**
```sql
DELETE FROM login_attempts WHERE username = 'el_usuario';
```

### Reset total de base de datos

> ⚠️ Irreversible. Solo para entornos de desarrollo o reinstalación completa.

1. **Zona Superadmin** → **Configuración**
2. Expande **Reset de Base de Datos**
3. Escribe `CONFIRMAR` en el campo de texto
4. Clic en **BORRAR TODO**

---

## Seguridad

### Protecciones del sistema

- No es posible eliminar al último superadmin activo
- Los admins no pueden ver ni eliminar a otros admins
- Los admins no pueden ver la Zona Superadmin
- El rate limiting (5 intentos → 15 min de bloqueo) es persistente en BD desde v3.9 — sobrevive reinicios y es efectivo en despliegues multi-worker
- Las contraseñas se almacenan con bcrypt (salt automático); SHA-256 como fallback si bcrypt no está instalado

### Recomendaciones

- **Mínimo número de superadmins** — idealmente 1 o 2 personas de máxima confianza
- **Cambiar la contraseña inicial** inmediatamente en el primer acceso
- **Cada persona su propio usuario** — nunca compartir credenciales
- **Revisar logs regularmente** para detectar actividad anómala
- **Backup antes de cambios importantes**:

```bash
cp scorecard.db scorecard_backup_$(date +%Y%m%d).db
```

---

## Diagnóstico desde consola

```python
import sqlite3
conn = sqlite3.connect('scorecard.db')

# Ver todos los usuarios y roles
print(conn.execute("SELECT username, role, active FROM users").fetchall())

# Ver intentos de login bloqueados
print(conn.execute(
    "SELECT username, fail_count, locked_until FROM login_attempts"
).fetchall())

conn.close()
```

---

## Checklist de primer despliegue

- [ ] Definir `QS_ADMIN_USER` y `QS_ADMIN_PASS` en el entorno
- [ ] Arrancar la app (`streamlit run app.py`)
- [ ] Login y cambio obligatorio de contraseña
- [ ] Verificar que aparece la **Zona Superadmin**
- [ ] Crear los usuarios Admin necesarios
- [ ] Crear los usuarios JT y asignarles centros
- [ ] Verificar que los JTs solo ven su centro
- [ ] Revisar logs para confirmar que la actividad queda registrada

---

## Cambios en v3.9 relevantes para Superadmin

- **Rate limiting en BD** — los bloqueos sobreviven reinicios del servidor; ya no se pierden si Streamlit recarga el proceso
- **Columna `centro` en usuarios** — los JTs tienen su centro asignado directamente en la tabla `users`; visible y editable desde la interfaz
- **`get_user_role()` filtra `active = 1`** — usuarios desactivados ya no son reconocidos como superadmin en checks de permisos (bug corregido)

---

*Quality Scorecard v3.9 · [@pablo25rf](https://github.com/pablo25rf) · Marzo 2026*
