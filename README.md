# WaitLess — Backend

Backend API REST del sistema WaitLess, una plataforma de gestión de restaurantes con predicción inteligente de tiempos de espera mediante Machine Learning.

**Stack:** Python · FastAPI · PostgreSQL · Scikit-learn · WebSockets

---

## ¿Qué hace este proyecto?

WaitLess es el backend de una aplicación móvil para restaurantes con dos roles: **cliente** y **administrador**. El sistema gestiona reservas, pedidos y mesas en tiempo real, e incorpora un modelo de ML entrenado para predecir la afluencia del restaurante según patrones históricos.

---

## Módulos principales

| Módulo | Descripción |
|---|---|
| `auth` | Registro, login y seguridad JWT |
| `pedidos` | Gestión de pedidos con estados en tiempo real |
| `mesas` | Control de disponibilidad de mesas |
| `reservas` | Reservas de mesa por cliente |
| `menu` | Administración del menú del restaurante |
| `reportes` | Métricas y estadísticas del negocio |
| `notificaciones` | Notificaciones push al cliente |
| `websocket` | Comunicación en tiempo real |
| `ia` | Módulo de predicción con Random Forest |

---

## Módulo de Inteligencia Artificial

El módulo `ia/` implementa un modelo de **Random Forest** entrenado con datos históricos del restaurante para predecir niveles de afluencia.

- `entrenamiento.py` — entrenamiento y guardado del modelo
- `prediccion.py` — inferencia en tiempo real desde la API
- `metricas.py` — evaluación del modelo (accuracy, F1, matriz de confusión)
- `modelo_waitless.pkl` — modelo serializado listo para producción
- `router.py` — endpoints REST del módulo de IA

---

## Stack técnico

- **Python 3.11+**
- **FastAPI** — framework principal de la API REST
- **PostgreSQL** — base de datos relacional (hosted en Neon)
- **Scikit-learn** — modelo Random Forest para predicción
- **SQLAlchemy** — ORM para manejo de base de datos
- **JWT** — autenticación segura
- **WebSockets** — comunicación en tiempo real
- **Uvicorn** — servidor ASGI

---

## Cómo correr el proyecto

### 1. Clonar el repositorio
```bash
git clone https://github.com/lauu2801r-dotcom/Waitless_Backend.git
cd Waitless_Backend
```

### 2. Crear entorno virtual e instalar dependencias
```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

### 3. Configurar variables de entorno
Crea un archivo `.env` en la raíz con:

DATABASE_URL=postgresql://usuario:contraseña@host/waitless

SECRET_KEY=tu_clave_secreta

### 4. Correr el servidor
```bash
uvicorn app.main:app --reload
```

La API estará disponible en `http://localhost:8000`  
Documentación automática en `http://localhost:8000/docs`

---

## Estructura del proyecto

app/

├── core/

│   ├── config.py         # variables de entorno

│   ├── database.py       # conexión PostgreSQL

│   ├── security.py       # JWT y autenticación

│   └── seed.py           # datos iniciales

├── ia/

│   ├── entrenamiento.py  # entrenamiento del modelo

│   ├── prediccion.py     # inferencia en tiempo real

│   ├── metricas.py       # evaluación del modelo

│   ├── modelo_waitless.pkl

│   └── router.py         # endpoints de IA

└── modules/

├── auth/

├── menu/

├── mesas/

├── notificaciones/

├── pedidos/

├── reportes/

├── reservas/

└── websocket/

---

## Proyecto académico

Desarrollado como proyecto de grado — Ingeniería de Software  
Universidad Manuela Beltrán · Bogotá, Colombia · 2026  
Autora: Laura Valentina González Rojas y Valentina Blanco Alvis
