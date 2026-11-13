# Referencia técnica — diet-service-control

Mapa de funcionalidades → código, para saber rápido qué archivos tocar al
modificar algo. Proyecto Django 5.2 (apps modulares, templates Jinja2,
PostgreSQL). No usa `django.contrib.auth`: la autenticación es propia
(sesión + tabla `Credencial`). Se despliega en Vercel (serverless) con BD en Neon.

## Índice de apps

| App | Responsabilidad |
|---|---|
| `apps/core` | Modelos compartidos, decorador de autenticación, utilidades de fecha/estado |
| `apps/auth_app` | Login, logout, recuperación y cambio de contraseña |
| `apps/dashboard` | Resumen general (saldos, pendientes) y lista de pedidos siguientes |
| `apps/dia` | Ver/editar un día puntual (pedido + entrega) |
| `apps/pagos` | Registro y edición de pagos, apertura/cierre de ciclos de pago |
| `apps/reportes` | Reporte de entregas por ciclo de pago (en pantalla, con botón de copiar) |
| `apps/log` | Muestra el changelog (`changelog/log.md`) en pantalla |
| `apps/importar` | Importa el plan de menú desde el `.eml` de dietservice.pe |
| `apps/validacion` | Pantalla Hoy: validación de entregas (HTMX, mobile-first) |
| `apps/calendario` | Calendario unificado semana/mes y modal de edición del pedido de un día |

Cada app sigue el mismo patrón: `views.py` (lógica), `urls.py` (rutas),
`apps.py` (config Django). Los templates viven todos juntos en `/templates`
(no por app), y usan Jinja2 (no el motor de templates nativo de Django).

---

## 1. Autenticación y sesión

- **Módulo:** `apps/auth_app/views.py`
- **Modelo:** `Credencial` (`apps/core/models.py`)
- **Decorador:** `protegido` en `apps/core/decorators.py` — envuelve toda
  vista que requiera sesión iniciada; redirige a `login` o a
  `cambiar_clave` si la clave es temporal.
- **Funciones clave:**
  - `credencial_valida(usuario, clave)` — valida contra BD, con fallback a
    `APP_USER`/`APP_PASSWORD` (variables de entorno).
  - `login`, `logout`, `recuperar`, `cambiar_clave`.
- **Templates:** `login.html`, `recuperar.html`, `cambiar_clave.html`.
- **Tocar esto si:** cambia la lógica de login, se agrega roles/permisos,
  o se migra a `django.contrib.auth`.

## 2. Dashboard (resumen general)

- **Módulo:** `apps/dashboard/views.py` → `dashboard()`
- **Modelos usados:** `Pedido`, `Entrega`, `Pago`, `CicloPago`
- **Utilidades:** `normalizar_fecha`, `formatear_fecha_con_dia` (`apps/core/utils.py`)
- **Templates:** `dashboard.html` + `partials/_resumen_tabs.html` (pestañas por HTMX con
  `?tab=vigente|futuros`)
- **Qué calcula:** saldo de almuerzos/cenas pagados vs. entregados dentro del
  ciclo vigente (el que contiene la fecha de hoy; si ninguno, el último ya
  iniciado), y listas de pendientes/por-validar. Los pagos se suman por
  `Pago.ciclo` y pedidos/entregas se acotan a `[fecha_inicio, fecha_fin]`.
  Helper: `_ciclo_vigente(tipo, hoy)`; un ciclo sin `fecha_fin` termina el día
  anterior al inicio del siguiente ciclo del mismo tipo (`_fin_efectivo`). Además expone la fecha de inicio del
  ciclo vigente por tipo (`fecha_ciclo_almuerzo`, `fecha_ciclo_cena`).
  `_ciclos_futuros(hoy, pedidos)` arma la lista `ciclos_futuros` (ciclos con
  `fecha_inicio` posterior a hoy que ya tienen días programados) para la
  segunda pestaña de contadores.
- **Tocar esto si:** cambia la fórmula de saldo, o qué cuenta como "pendiente".

## 3–4. Vistas mensual y semanal (retiradas)

- `apps/mes` y `apps/semana` se eliminaron; `/mes` y `/semana` redirigen a `/calendario`
  (ver sección 11). Los colores de estado viven en `apps/calendario/services.py` (`_color`).
- `/pedidos_siguientes` también se retiró: el calendario y Hoy cubren esa información.

## 5. Edición de un día puntual

- **Módulo:** `apps/dia/views.py`
- **Modelos usados:** `Pedido`, `Entrega`
- **Funciones clave:**
  - `cargar_datos_dia(fecha_form)` — arma el contexto completo de un día
    (pedido + entrega + navegación a día anterior/siguiente hábil).
  - `siguiente_dia_habil` / `anterior_dia_habil` — saltan fines de semana.
  - `ver_dia` (solo lectura) vs `editar_dia` (GET muestra form, POST guarda).
- **Templates:** `editar_dia.html`
- **Tocar esto si:** cambia qué campos tiene un pedido/entrega.
- **Nota:** el autocompletado de platos se eliminó.

## 6. Pagos y ciclos de pago

- **Módulo:** `apps/pagos/views.py` → `pagos()`, `editar_pago()`
- **Modelos usados:** `Pago`, `CicloPago`, `Pedido`, `Log`
- **Utilidades:** `formatear_fecha`, `ciclo_agotado` (`apps/core/utils.py`)
- **Lógica central:** al registrar un pago, si no hay ciclo abierto se crea
  uno; si el ciclo abierto ya se agotó (`ciclo_agotado`) se cierra y se abre
  uno nuevo; si aún no se agotó, el pago queda "pendiente" (sin ciclo).
- **Funciones de soporte (`apps/core/utils.py`):**
  `contar_entregas_ciclo(ciclo)`, `ciclo_agotado(ciclo)`.
- **Templates:** `pagos.html`, `editar_pago.html` (respaldo), `partials/_pagos_listas.html`,
  `_pago_fila_edicion.html`, `_ciclo_fila_edicion.html` (edición inline por HTMX).
- **HTMX:** el alta y las ediciones devuelven `_pagos_listas.html` (`#pagos-listas`); los datos
  inválidos responden 400 con un mensaje corto que se muestra como toast.
- **Tocar esto si:** cambia la regla de apertura/cierre de ciclos, o qué
  cuenta como "entrega" dentro de un ciclo.

## 7. Reportes por ciclo

- **Módulo:** `apps/reportes/views.py` → `reporte_ciclo()`
- **Salida:** solo en pantalla; el botón «Copiar tabla» (JS en `reporte_ciclo.html`)
  copia la tabla al portapapeles. La exportación a Excel se eliminó junto con
  `pandas` y `xlsxwriter`.
- **Modelos usados:** `Entrega`, `Pago`, `CicloPago`
- **Templates:** `reporte_ciclo.html` + `partials/_reporte.html` (los selectores de tipo y ciclo
  hacen `hx-get` por query string; ya no hay POST).
- **Tocar esto si:** cambian los filtros del reporte en pantalla o el formato de
  la tabla copiada.

## 8. Changelog en pantalla

- **Módulo:** `apps/log/views.py` → `log()`
- **Fuente de datos:** archivo `changelog/log.md` (texto plano, no modelo)
- **Templates:** `log.html`
- **Tocar esto si:** cambia el formato del changelog o su fuente (hoy lee
  directo del archivo `.md`, no de la tabla `Log`).

## 9. Importación del plan de menú (.eml)

- **Módulo:** `apps/importar/parser.py` (parseo) + `apps/importar/views.py` (flujo web)
- **Modelo usado:** `Pedido` (`update_or_create` por fecha)
- **Formato de entrada:** correo "Tu pedido de menú quedó registrado" de
  `notificacion@dietservice.pe` — tabla HTML con fecha ISO explícita por
  día y filas Entrada/Fondo/Cena.
- **Clases/funciones clave (`parser.py`):**
  - `PedidoMenuParser` (subclase de `HTMLParser`) — recorre la tabla y arma
    `filas` (lista de `{fecha_texto, tipo, plato}`) + `nombre` del cliente.
  - `_extraer_html(msg)`, `_decodificar_asunto(msg)` — helpers de parseo del `.eml`.
  - `parsear_eml(contenido_bytes)` — función pública, agrupa filas por
    fecha (arrastrando la fecha cuando la celda viene vacía) y devuelve
    `{asunto, nombre, dias, errores}`.
- **Vistas (`views.py`):** `importar_eml` (GET form / POST preview),
  `confirmar_importacion` (POST guarda en BD, incluye `cena`/`plato_cena`).
- **Templates:** `importar.html`, `importar_preview.html`, `importar_resultado.html` y
  `partials/_importar_*.html` (el flujo completo ocurre en `#importar-contenido`).
- **Tocar esto si:** dietservice.pe vuelve a cambiar el formato del correo,
  o se quiere soportar otro origen de importación (ver nota abajo).
- **Nota:** el parser de Google Forms (formato anterior) fue eliminado por
  completo; no hay compatibilidad retroactiva con ese `.eml`.

## 10. Validación de entregas (pantalla Hoy)

- **Módulo:** `apps/validacion/` → `views.py` (`hoy`, `marcar_entrega`,
  `validar_hasta_ayer`) y `services.py` (lógica, sin HTTP).
- **Funciones clave (`services.py`):** `hoy_lima()`, `cargar_estado()`,
  `calcular_contadores()` (misma fórmula de saldo que el dashboard; importa los
  helpers `_ciclo_vigente`, `_rango_ciclo`, `_en_rango`, `_pagos_ciclo` de
  `apps/dashboard/views.py`), `armar_dias()`, `guardar_entrega()`,
  `validar_hasta_ayer()`.
- **Semántica:** `marcar_entrega` recibe el valor explícito (1/0), es idempotente
  y rechaza fechas futuras, feriados o tipos sin pedido.
- **Helper HTMX:** `apps/core/htmx.py` → `es_htmx`, `render_page_or_partial`
  (parcial si llega `HX-Request`, página completa si no; añade `Vary: HX-Request`).
- **Templates:** `hoy.html` y `templates/partials/` (`_barra_hoy`, `_lista_hoy`,
  `_macros_validacion`, `_respuesta_marcar`, `_respuesta_masiva`). Los contadores
  se actualizan con `hx-swap-oob`.
- **Base:** `base.html` carga `static/js/htmx.min.js`, envía el CSRF por
  `hx-headers` (global `csrf_value`), muestra toasts de error (el texto de los 400), inicializa flatpickr en contenido cargado por
  HTMX (`htmx:load`) y la barra inferior móvil.
- **Observación rápida:** `obs_entrega` (GET modal / POST guarda en `Entrega.observaciones`);
  el POST responde 204 con `HX-Trigger` (`cerrarModal`, `hoyActualizado`).
- **Tocar esto si:** cambia la regla de «pendiente», los botones de entrega o la barra de contadores.

## 11. Calendario unificado y modal de día

- **Módulo:** `apps/calendario/` → `views.py` (`calendario`, `modal_dia`, `guardar_dia`) y
  `services.py` (`construir_semana`, `construir_mes`, `datos_modal`, `guardar_pedido`).
- **Rutas:** `/calendario?vista=semana|mes&fecha=YYYY-MM-DD`, `/calendario/dia` (modal),
  `/calendario/dia/guardar`. Sin HTMX, `modal_dia` redirige a `/editar_dia`.
- **Modal global:** `<dialog id="modal-global">` en `base.html`; se abre al cargar contenido en
  `#modal-contenido` y se cierra con el evento `cerrarModal` (cabecera `HX-Trigger`).
- **Templates:** `calendario.html`, `partials/_calendario.html`, `_modal_dia.html`, `_modal_obs.html`.
- **Alcance:** edita solo el pedido; la entrega se valida en Hoy. `/semana` y `/mes`
  redirigen aquí.
- **Tocar esto si:** cambian los colores/estados del calendario o los campos del modal.

---

## Modelos de datos (`apps/core/models.py`)

| Modelo | Tabla | Campos clave | Notas |
|---|---|---|---|
| `Credencial` | `credenciales` | `usuario`, `contrasena` | columna BD `contraseña` |
| `Pedido` | `pedidos` | `fecha` (PK), `almuerzo`, `cena`, `entrada`, `fondo`, `plato_cena`, `feriado`, `observaciones` | `almuerzo`/`cena` son flags 1/0, no booleanos |
| `Entrega` | `entregas` | `fecha`, `entregado_almuerzo`, `entregado_cena`, `observaciones` | restricción única sobre `fecha` (`entregas_fecha_unica`); la migración 0002 fusionó duplicados históricos |
| `CicloPago` | `ciclos_pago` | `tipo`, `fecha_inicio`, `fecha_fin` | `fecha_fin` null = ciclo abierto |
| `Pago` | `pagos` | `fecha`, `tipo`, `monto`, `cantidad`, `ciclo` (FK) | `ciclo` puede ser null (pago "pendiente") |
| `Log` | `log` | `timestamp`, `accion`, `detalle` | solo se usa desde `apps/pagos`; el changelog visible (`apps/log`) lee el `.md`, no esta tabla |

## Utilidades transversales (`apps/core/utils.py`)

| Función | Uso |
|---|---|
| `obtener_fechas_semana` | arma fechas lun-vie de una semana ISO |
| `normalizar_fecha` | castea `str`/`datetime`/`date` a `date` |
| `normalizar_fecha_ddmmaaaa` | parsea `DD-MM-YYYY` |
| `formatear_fecha` / `formatear_fecha_con_dia` | formato de salida para templates |
| `estado_textual` | texto de estado de un día (dashboard/semana) |
| `contar_entregas_ciclo` / `ciclo_agotado` | lógica de ciclos en `apps/pagos` |

## Configuración del proyecto

| Archivo | Contenido |
|---|---|
| `diet_service_control/settings.py` | apps instaladas, BD (Postgres/Neon vía `DATABASE_URL`, con fallback `DB_*` local), hosts/CSRF (incluye dominios de Vercel), logging, credenciales por entorno (`APP_USER`/`APP_PASSWORD`) |
| `diet_service_control/urls.py` | registro de rutas raíz (`include` de cada app) + iconos apple-touch |
| `diet_service_control/wsgi.py` | expone `application`; Vercel lo detecta vía `WSGI_APPLICATION` |
| `diet_service_control/jinja2.py` | entorno Jinja2 custom: `url_for_django` (mapea `modulo.vista` → nombre de URL Django) `CsrfExtension` (`{% csrf_token %}` en Jinja2) y el global `csrf_value(request)` (token para `hx-headers`) |

**Importante:** si se agrega una vista nueva con `url_for(...)` en un
template, hay que sumar la entrada correspondiente en `endpoint_map` dentro
de `diet_service_control/jinja2.py`, o el `url_for` fallará en runtime.

---

## Guía rápida: "quiero cambiar X, ¿qué toco?"

| Quiero... | Archivos a revisar |
|---|---|
| Cambiar el login o las credenciales | `apps/auth_app/views.py`, `apps/core/models.py` (`Credencial`) |
| Cambiar qué se considera "pendiente" en el dashboard | `apps/dashboard/views.py` |
| Cambiar colores/estados del calendario | `apps/calendario/services.py` (`_color`) |
| Agregar un campo nuevo a un pedido/entrega | `apps/core/models.py`, `apps/dia/views.py` (`cargar_datos_dia`, `editar_dia`), `templates/editar_dia.html`, migración en `apps/core/migrations/` |
| Cambiar la regla de apertura/cierre de ciclos de pago | `apps/pagos/views.py`, `apps/core/utils.py` (`ciclo_agotado`) |
| Cambiar el reporte por ciclo | `apps/reportes/views.py` (`reporte_ciclo`), `templates/reporte_ciclo.html` |
| Cambiar la conexión a la BD o variables de despliegue | `diet_service_control/settings.py` (`_database_from_url`, hosts/CSRF) |
| Cambiar el formato de importación del menú | `apps/importar/parser.py`, `apps/importar/views.py`, `templates/importar*.html` |
| Agregar una vista/URL nueva | crear en la app correspondiente, registrar en su `urls.py`, incluir en `diet_service_control/urls.py`, y sumar a `endpoint_map` en `jinja2.py` si el template usa `url_for` |
| Cambiar la pantalla Hoy o la validación de entregas | `apps/validacion/services.py`, `apps/validacion/views.py`, `templates/hoy.html`, `templates/partials/_*hoy*.html`, `_macros_validacion.html` |
| Cambiar el calendario unificado o el modal de un día | `apps/calendario/services.py`, `apps/calendario/views.py`, `templates/partials/_calendario.html`, `_modal_dia.html` |
