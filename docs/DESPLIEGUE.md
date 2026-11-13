# WaitLess — Guía de despliegue

Esta guía explica cómo poner el backend de WaitLess en funcionamiento: en local, con Docker y en la nube (Render), y cómo conectar la app móvil.

## 1. Arquitectura de despliegue

| Componente | Dónde corre | Cómo se accede |
|---|---|---|
| App móvil (Flutter) | Celular Android | APK instalado |
| API REST + WebSocket + IA (FastAPI) | Contenedor Docker en Render (o en el PC) | HTTPS / WSS |
| Base de datos PostgreSQL | Neon (nube) | SQL sobre TLS, solo desde el backend |
| Correo (códigos de verificación) | Gmail (SMTP) | Desde el backend |
| Tableros de análisis | Power BI Service | Enlace público abierto desde la app |

## 2. Variables de entorno

Se definen en un archivo `.env` (local) o en el panel de Render. Hay una plantilla en `.env.example`. **Nunca se suben valores reales a GitHub.**

| Variable | Obligatoria | Descripción |
|---|---|---|
| `DATABASE_URL` | Sí | Cadena de conexión a PostgreSQL (`postgresql://…?sslmode=require`) |
| `SECRET_KEY` | Sí | Llave para firmar los tokens JWT (larga y aleatoria) |
| `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | Sí | Cuenta de correo para los códigos de verificación |
| `MAIL_SERVER`, `MAIL_PORT` | No | Por defecto `smtp.gmail.com` y `587` |
| `CODIGO_NEGOCIO` | No | Código para registrar un restaurante nuevo |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Vigencia del token (por defecto 1440 = 24 h) |
| `ENVIRONMENT` | No | `development` o `production` |

Generar una `SECRET_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

## 3. Ejecución local sin Docker

Requisitos: Python 3.12 o superior.

```
python -m venv .venv
.venv\Scripts\activate            # en Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # y completar los valores
uvicorn app.main:app --reload
```

La documentación interactiva queda en `http://localhost:8000/docs`.

Para recibir conexiones desde el celular en la misma red: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

## 4. Ejecución con Docker

Requisito: Docker Desktop.

```
copy .env.example .env            # completar los valores
docker compose up --build
```

- Comprobación: `http://localhost:8000/health` responde `{"status":"ok"}`.
- Detener: `docker compose down`.
- Con una base de datos PostgreSQL local de pruebas: `docker compose --profile localdb up --build` y en `.env` poner `DATABASE_URL=postgresql://waitless:waitless@db:5432/waitless`.

Al arrancar, el backend crea las tablas que falten y agrega, de forma segura y repetible, las columnas nuevas (módulo `app/core/migraciones.py`), así que **no hay pasos manuales de migración**.

## 5. Despliegue en Render

1. Subir el repositorio del backend a GitHub, **incluyendo** `Dockerfile`, `.dockerignore`, `render.yaml` y la carpeta `static/imagenes/` (fotos de platos y restaurantes).
2. En render.com: **New → Blueprint** (usa `render.yaml`) o **New → Web Service** → elegir el repositorio y la rama → *Runtime: Docker*.
3. Escribir los valores secretos en **Environment** (`DATABASE_URL`, `SECRET_KEY`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `CODIGO_NEGOCIO`).
4. **Create / Deploy.** El primer despliegue tarda entre 5 y 10 minutos.
5. Verificar:
   - `https://<servicio>.onrender.com/health` → `{"status":"ok"}`
   - `https://<servicio>.onrender.com/docs` → documentación de la API
   - `https://<servicio>.onrender.com/static/imagenes/platos/bife-de-chorizo.jpg` → una foto

**Plan gratuito:** el servicio se duerme tras 15 minutos sin tráfico y tarda cerca de un minuto en despertar. Antes de una demostración, abrir `/health` unos minutos antes.

## 6. Entrega de la app móvil (APK)

```
flutter build apk --release --dart-define=API_URL=https://<servicio>.onrender.com
```

El archivo queda en `build/app/outputs/flutter-apk/app-release.apk`. Se instala en el celular (permitiendo orígenes desconocidos) o con `adb install`. Si no se indica `API_URL`, la app usa `http://10.0.2.2:8000` (emulador Android).

Pruebas en un celular conectado por USB al backend local: `adb reverse tcp:8000 tcp:8000` y `flutter run --dart-define=API_URL=http://localhost:8000`.

## 7. Actualizar y volver atrás

- **Actualizar:** hacer push a la rama conectada; Render construye y publica la nueva versión (`autoDeploy`).
- **Volver atrás:** en Render → *Events/Deploys* → elegir un despliegue anterior → *Rollback*. La base de datos no se toca, porque los cambios de esquema solo agregan columnas.
- **Si el nuevo despliegue falla:** Render mantiene la versión anterior activa hasta que el chequeo `/health` del nuevo pase.

## 8. Mantenimiento básico

- **Respaldos:** Neon conserva historial y permite restaurar a un punto anterior; además se puede exportar un volcado con `pg_dump`.
- **Credenciales:** rotar `SECRET_KEY`, la contraseña de la base de datos y la contraseña de aplicación del correo si se llegan a exponer. Cambiar una `SECRET_KEY` cierra todas las sesiones activas.
- **Modelo de IA:** se reentrena automáticamente cada 25 pedidos reales nuevos y se guarda por versión en la base de datos.
- **Pruebas antes de publicar:** `python tests/test_domicilio.py`, `test_negocio.py`, `test_reservas.py`, `test_privacidad.py` y `test_alerta_mesa.py` (cada una imprime «N ok, 0 fallas»).

## 9. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| El build falla instalando dependencias | Versión de Python distinta | El Dockerfile usa Python 3.12; no cambiarlo |
| `/health` no responde justo después de abrir | El servicio estaba dormido (plan gratuito) | Esperar ~1 minuto y reintentar |
| Error de conexión a la base de datos | `DATABASE_URL` mal copiada | Debe empezar por `postgresql://` y terminar en `?sslmode=require` |
| La app no carga datos | `API_URL` incorrecta al compilar | Recompilar con la URL correcta de Render |
| Las fotos no aparecen | No se subió `static/imagenes/` a GitHub | Hacer commit y push de las fotos |
| No llegan los códigos por correo | Falta la «contraseña de aplicación» de Gmail | Crearla en la cuenta de Google y usarla en `MAIL_PASSWORD` |
