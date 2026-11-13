# Diet Service Control

Aplicación web personal para llevar el control de pedidos, entregas y pagos
del servicio de almuerzos/cenas de **Diet Service**. Permite ver el estado
día a día y por semana, registrar pagos por ciclos, consultar reportes de
entregas por ciclo, e importar automáticamente el plan de menú desde el
correo de confirmación de pedido.

Migrado desde una app Flask original a **Django 5.2**, y desplegada de forma
serverless en **Vercel** con la base de datos en **Neon**, manteniendo la
misma lógica de negocio.

## Stack

- **Backend:** Django 5.2 (sin `django.contrib.auth`; autenticación propia por sesión)
- **Templates:** Jinja2 (no el motor nativo de Django — ver `diet_service_control/jinja2.py`)
- **Interactividad:** HTMX servido desde `static/js/htmx.min.js` (sin CDN externo)
- **Base de datos:** PostgreSQL en Neon (con pooler)
- **Ejecución:** Vercel Functions (runtime Python, WSGI)
- **Estáticos en producción:** CDN de Vercel (`collectstatic` automático)
- **Despliegue:** Vercel (producción) / `runserver` (local)

## Estructura del proyecto

```
diet_service_control/     Configuración del proyecto (settings, urls, jinja2, wsgi)
apps/
  core/                    Modelos compartidos, decorador de autenticación, utilidades
  auth_app/                Login, logout, recuperación y cambio de contraseña
  dashboard/                Resumen general y pedidos pendientes
  dia/                      Ver/editar un día puntual
  pagos/                    Registro de pagos y ciclos de pago
  reportes/                 Reporte de entregas por ciclo (copiable desde pantalla)
  log/                      Muestra el changelog en pantalla
  importar/                 Importación del plan de menú desde .eml
  validacion/               Pantalla Hoy: validación de entregas (mobile-first, HTMX)
  calendario/               Calendario unificado semana/mes y modal de edición de un día (HTMX)
templates/                 Templates Jinja2 (compartidos entre apps)
static/                    CSS, JS e íconos
changelog/log.md            Registro editorial de acciones (texto plano)
```

Para el detalle de qué módulo/función tocar según la funcionalidad a
modificar, ver **`REFERENCIA_TECNICA.md`**.

## Variables de entorno

| Variable | Uso |
|---|---|
| `SECRET_KEY` | Clave secreta de Django. **Obligatoria en Vercel** (la app no arranca con la clave por defecto). |
| `DEBUG` | `True` solo en desarrollo local. |
| `DATABASE_URL` | Cadena de conexión de Neon (usar la URL **pooled**, con `-pooler` en el host). |
| `ALLOWED_HOSTS` | Hosts adicionales separados por comas (p. ej. un dominio propio). Los dominios de Vercel se agregan solos. |
| `CSRF_TRUSTED_ORIGINS` | Orígenes adicionales con esquema (p. ej. `https://midominio.com`). Los de Vercel se agregan solos. |
| `APP_USER` / `APP_PASSWORD` | Credencial de acceso inicial. Una vez logueado se puede cambiar la contraseña desde la interfaz (queda en la tabla `credenciales`, con estas variables como respaldo/fallback). |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Alternativa a `DATABASE_URL` para desarrollo local con PostgreSQL propio. |

Ejemplo de `.env` local (no versionado):

```env
SECRET_KEY=una-clave-secreta-larga-y-unica
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgresql://usuario:clave@ep-xxxx-pooler.region.aws.neon.tech/neondb?sslmode=require

APP_USER=admin
APP_PASSWORD=cambia-esta-clave
```

## Desarrollo local

Requiere Python 3.12 y una base PostgreSQL accesible (Neon o local).

```bash
python -m venv venv
source venv/bin/activate          # en Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate          # solo si el esquema no existe o hay migraciones pendientes
python manage.py runserver
```

Con `DEBUG=True`, `runserver` sirve los estáticos directamente.

**HTMX:** descargar `htmx.min.js` (2.x) en `static/js/htmx.min.js`; no se usa CDN.

**Migración 0002:** deduplica `entregas` y agrega la restricción única sobre `fecha`.
Revisar los avisos `WARNING` de la migración antes de aplicarla en producción.

## Despliegue en Vercel

1. Crear el proyecto en Neon y copiar la cadena de conexión **pooled**.
2. Aplicar migraciones desde local contra Neon (si hace falta):
   `DATABASE_URL=... python manage.py migrate`. No se ejecutan en cada despliegue.
3. Importar el repositorio en Vercel. Vercel detecta `manage.py` y toma el
   entrypoint de `WSGI_APPLICATION` (`diet_service_control.wsgi.application`).
4. Definir las variables de entorno de la tabla anterior (`SECRET_KEY`, `DATABASE_URL`,
   `APP_USER`, `APP_PASSWORD`).
5. Desplegar. Al haber `STATIC_ROOT`, Vercel ejecuta `collectstatic` en el
   build y sirve `/static/` desde su CDN.

Notas:

- El plan gratuito (Hobby) de Vercel es solo para uso personal y no comercial.
- Cada petición corre en una función efímera: no se guarda estado en memoria
  ni en disco. Las conexiones a Neon no se reutilizan (`CONN_MAX_AGE=0`) y se
  desactivan los cursores del lado del servidor por el pooler.
- La primera petición tras un periodo de inactividad puede tardar más (cold start).
- Si una vista supera el tiempo máximo de la función, se puede ajustar
  `maxDuration` en un `vercel.json` (sujeto al límite del plan).

## Funcionalidades principales

- **Hoy (inicio):** tarjetas táctiles por día con botones Almuerzo/Cena que
  fijan la entrega al instante (HTMX), contadores de pendientes y saldo en
  barra fija, observación rápida de entrega por día, validación masiva «hasta ayer» y barra de navegación inferior
  en móvil. La fecha de «hoy» se calcula en `America/Lima`.
- **Dashboard:** saldo de almuerzos/cenas pagados vs. entregados dentro del
  ciclo vigente (con su fecha de inicio en la tabla), pestaña de ciclos
  futuros que ya tienen programación, y aviso de días sin validar con enlace a Hoy. Las pestañas se cargan por HTMX.
- **Calendario (`/calendario`):** toggle semana/mes por HTMX (semana por defecto), navegación
  anterior/siguiente sin recargar y modal para editar el pedido de un día. `/semana` y `/mes`
  redirigen al calendario.
- **Edición de día:** pedido (entrada, fondo, cena) y entrega de una fecha
  puntual (pantalla de respaldo; la edición habitual es el modal del calendario).
- **Pagos y ciclos:** registro de pagos, apertura/cierre automático de
  ciclos según el paquete contratado se agote. Alta y edición de pagos y de
  fechas de ciclo en la misma página (HTMX).
- **Reportes:** listado de entregas por ciclo de pago en pantalla, con botón
  para copiar la tabla al portapapeles (se eliminó la exportación a Excel).
  Los selectores de tipo y ciclo actualizan el reporte por HTMX.
- **Importación de menú:** sube el `.eml` del correo "Tu pedido de menú
  quedó registrado" de dietservice.pe y carga automáticamente entrada,
  fondo y cena de cada día en el rango del pedido. Subir → previsualizar →
  confirmar ocurre en la misma página.
- **Changelog:** vista de solo lectura del archivo `changelog/log.md`.

## Logging

El proyecto registra logs por nivel (`INFO` para resultados de operaciones
importantes, `WARNING`/`ERROR` en validaciones y bloques `except`,
`DEBUG` para detalle interno) en cada app bajo el logger `apps`. En
desarrollo se ven en consola; en Vercel quedan en los logs de la función.

## Documentación relacionada

- `REFERENCIA_TECNICA.md` — mapa de funcionalidades a módulos/clases/funciones,
  útil antes de modificar cualquier parte del código.
- `changelog/log.md` — registro histórico de acciones del sistema.
