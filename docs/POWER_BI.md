# WaitLess — Dashboard en Power BI

Guía paso a paso para armar el dashboard analítico de WaitLess en **Power BI Desktop**
conectado a la base de datos real (Neon / PostgreSQL).

> Power BI **solo lee** los datos. No modifica pedidos, facturas ni usuarios.

---

## 1. Crear las vistas en la base de datos

Las vistas `bi_*` ordenan los datos para Power BI (horas de Colombia, días en español,
columnas calculadas como el error de la IA). Se crean con un script:

```powershell
cd C:\Users\Laura\Documents\GitHub\Waitless_Backend
.\.venv\Scripts\activate
python -m app.core.bi_vistas --rol-bi "UnaClaveSegura2026"
```

- Crea 9 vistas y un usuario **`waitless_bi`** que **solo puede leer esas vistas**
  (no ve contraseñas, usuarios ni nada más). Usa **ese** usuario en Power BI, no el dueño.
- Elige tu propia clave (10+ caracteres, sin comillas) y no la subas a GitHub.
- Se puede volver a correr cuando quieras (actualiza las vistas). Para quitarlas: `--borrar`.

| Vista | Qué trae | Un renglón por… |
|---|---|---|
| `bi_restaurantes` | Restaurantes y tipo de cocina | restaurante |
| `bi_productos` | Menú, categoría y precio | producto |
| `bi_pedidos` | Pedidos con fecha, hora, día, estado, tiempo estimado y real, si fue pagado | pedido |
| `bi_ventas` | Facturas: subtotal, impuesto, propina, total, método de pago | factura |
| `bi_items_vendidos` | Productos vendidos dentro de cada pedido | ítem |
| `bi_ia_predicciones` | Cada predicción de la IA y, si ya se cerró, su tiempo real y error | predicción |
| `bi_ia_modelos` | Versiones del modelo, muestras, error y mejora | versión |
| `bi_calificaciones` | Estrellas y comentarios por plato | calificación |
| `bi_inventario` | Insumos, stock, mínimo y valor | insumo |

Todas las vistas con datos de pedidos traen **`es_simulado`** (`True` = viene del historial
de demostración `seed_historial`). Úsalo como filtro: así puedes mostrar solo datos reales
o todos, y dejar claro en la tesis qué es qué.

---

## 2. Conectar Power BI Desktop a Neon

1. En el panel de Neon abre tu proyecto → **Connection Details** y copia:
   **Host** (algo como `ep-xxxx.us-east-2.aws.neon.tech`), **Database**.
   Usa el host **sin** `-pooler`.
2. Power BI Desktop → **Obtener datos** → **Base de datos PostgreSQL** → **Conectar**.
3. **Servidor:** el host de Neon (puedes añadir el puerto: `ep-xxxx...neon.tech:5432`).
   **Base de datos:** la de Neon (normalmente `neondb`).
   **Modo de conectividad de datos:** **Importar** (más rápido y suficiente).
4. En credenciales elige **Base de datos**: usuario `waitless_bi` y la clave que pusiste.
5. En el navegador marca **todas** las tablas/vistas `bi_*` → **Cargar**.

Si aparece un error de SSL o *"Endpoint ID is not specified"*: en la clave usa
`endpoint=ep-xxxx$TuClave` (el `ep-xxxx` es el primer pedazo del host). Si no conecta, avísame
con el mensaje exacto.

---

## 3. Modelo (relaciones)

Ve a la vista **Modelo** (icono de tres tablas a la izquierda).

**3.1 Tabla calendario** — Modelado → *Nueva tabla* y pega:

```dax
Calendario =
ADDCOLUMNS (
    CALENDAR ( MIN ( bi_pedidos[fecha] ), MAX ( bi_pedidos[fecha] ) ),
    "Año", YEAR ( [Date] ),
    "Mes N", MONTH ( [Date] ),
    "Mes", FORMAT ( [Date], "mmmm" ),
    "Día N", WEEKDAY ( [Date], 2 ),
    "Día", FORMAT ( [Date], "dddd" )
)
```

Selecciónala → Herramientas de tabla → **Marcar como tabla de fechas** (columna `Date`).

**3.2 Relaciones** (arrastra de una columna a la otra; todas *uno a varios*, dirección única):

| De (uno) | A (varios) |
|---|---|
| `Calendario[Date]` | `bi_pedidos[fecha]`, `bi_ventas[fecha]`, `bi_items_vendidos[fecha]`, `bi_ia_predicciones[fecha]`, `bi_calificaciones[fecha]` |
| `bi_restaurantes[restaurante_id]` | `bi_pedidos[restaurante_id]`, `bi_ventas[restaurante_id]`, `bi_items_vendidos[restaurante_id]`, `bi_ia_predicciones[restaurante_id]`, `bi_calificaciones[restaurante_id]` |
| `bi_ia_modelos[version]` | `bi_ia_predicciones[version_modelo]` |
| `bi_productos[producto_id]` | `bi_items_vendidos[producto_id]` |

**No** relaciones `bi_productos` con `bi_restaurantes` (crearía caminos duplicados).
Con esto, un solo segmentador de **Restaurante** o de **Fecha** filtra todo el dashboard.

---

## 4. Medidas DAX

Selecciona cualquier tabla → *Nueva medida* y pega cada una. Conviene crear una tabla vacía
llamada `Medidas` (Introducir datos) para tenerlas ordenadas.

> Si Power BI marca error en las comas, tu equipo usa `;` como separador: cámbialas todas.

### Ventas y pedidos

```dax
Ventas = CALCULATE ( SUM ( bi_ventas[total] ), bi_ventas[estado] = "pagada" )

Propinas = CALCULATE ( SUM ( bi_ventas[propina] ), bi_ventas[estado] = "pagada" )

Impuestos = CALCULATE ( SUM ( bi_ventas[impuesto] ), bi_ventas[estado] = "pagada" )

Facturas = CALCULATE ( COUNTROWS ( bi_ventas ), bi_ventas[estado] = "pagada" )

Ticket promedio = DIVIDE ( [Ventas], [Facturas] )

Pedidos = CALCULATE ( COUNTROWS ( bi_pedidos ), bi_pedidos[estado] <> "cancelado" )

Pedidos cancelados = CALCULATE ( COUNTROWS ( bi_pedidos ), bi_pedidos[estado] = "cancelado" )

% cancelados = DIVIDE ( [Pedidos cancelados], COUNTROWS ( bi_pedidos ) )

Pedidos por día = DIVIDE ( [Pedidos], DISTINCTCOUNT ( bi_pedidos[fecha] ) )

Ventas mes anterior = CALCULATE ( [Ventas], DATEADD ( Calendario[Date], -1, MONTH ) )

Variación vs mes anterior = DIVIDE ( [Ventas] - [Ventas mes anterior], [Ventas mes anterior] )

Productos vendidos = SUM ( bi_items_vendidos[cantidad] )
```

### Cocina y tiempos

```dax
Tiempo real prom (min) = AVERAGE ( bi_pedidos[minutos_reales] )

Tiempo estimado prom (min) = AVERAGE ( bi_pedidos[minutos_estimados] )
```

### Inteligencia artificial (solo cuentan predicciones ya cerradas)

```dax
Predicciones evaluadas = CALCULATE ( COUNTROWS ( bi_ia_predicciones ), bi_ia_predicciones[cerrada] = TRUE () )

Error promedio (min) = AVERAGE ( bi_ia_predicciones[error_absoluto] )

Acierto ±5 min = AVERAGE ( bi_ia_predicciones[acierto_5min] )

Acierto ±10 min = AVERAGE ( bi_ia_predicciones[acierto_10min] )

Real dentro del rango = AVERAGE ( bi_ia_predicciones[dentro_del_rango] )

Sesgo (min) = AVERAGE ( bi_ia_predicciones[error_con_signo] )

Error si promediara (min) =
VAR prom = CALCULATE ( AVERAGE ( bi_ia_predicciones[minutos_reales] ), bi_ia_predicciones[cerrada] = TRUE () )
RETURN
    AVERAGEX (
        FILTER ( bi_ia_predicciones, bi_ia_predicciones[cerrada] = TRUE () ),
        ABS ( bi_ia_predicciones[minutos_reales] - prom )
    )

Mejora vs promediar = DIVIDE ( [Error si promediara (min)] - [Error promedio (min)], [Error si promediara (min)] )

Confianza promedio = AVERAGE ( bi_ia_predicciones[confianza] ) / 100
```

Columna calculada para el histograma de errores (tabla `bi_ia_predicciones` → *Nueva columna*):

```dax
Rango de error =
SWITCH (
    TRUE (),
    ISBLANK ( bi_ia_predicciones[error_absoluto] ), BLANK (),
    bi_ia_predicciones[error_absoluto] <= 5, "0 – 5 min",
    bi_ia_predicciones[error_absoluto] <= 10, "5 – 10 min",
    bi_ia_predicciones[error_absoluto] <= 20, "10 – 20 min",
    "Más de 20 min"
)
```

### Calificaciones e inventario

```dax
Calificación promedio = AVERAGE ( bi_calificaciones[estrellas] )

Calificaciones = COUNTROWS ( bi_calificaciones )

% 4 y 5 estrellas = DIVIDE ( CALCULATE ( COUNTROWS ( bi_calificaciones ), bi_calificaciones[estrellas] >= 4 ), [Calificaciones] )

Insumos bajo el mínimo = CALCULATE ( COUNTROWS ( bi_inventario ), bi_inventario[bajo_el_minimo] = TRUE () )

Valor del inventario = SUM ( bi_inventario[valor_en_stock] )
```

Formatos: Ventas/Propinas/Impuestos/Ticket → moneda; `% cancelados`, `Acierto…`,
`Real dentro del rango`, `Mejora vs promediar`, `% 4 y 5 estrellas`, `Confianza promedio`
→ porcentaje; el resto → número con 1 decimal.

---

## 5. Páginas del dashboard

Tema sugerido: fondo crema `#FBF7F0`, acento terracota `#C65D3A`, verde oliva `#7B8B3C`,
texto café `#3D2817` (los colores de la app). Vista → Temas → Personalizar tema.

En **todas** las páginas deja a la izquierda o arriba los segmentadores:
**Fecha** (`Calendario[Date]`, tipo Entre), **Restaurante** (`bi_restaurantes[restaurante]`) y
**Datos simulados** (`bi_pedidos[es_simulado]`). Para que `es_simulado` filtre todas las
páginas usa *Sincronizar segmentadores*; para las vistas que no relacionan esa columna,
repite el segmentador en la página.

### Página 1 — Ventas

| Visual | Campos |
|---|---|
| 4 tarjetas | `Ventas`, `Facturas`, `Ticket promedio`, `Variación vs mes anterior` |
| Líneas | Eje `Calendario[Date]`, valores `Ventas` |
| Columnas agrupadas | Eje `bi_ventas[metodo_pago]`, valores `Ventas` (o dona) |
| Barras | Eje `bi_restaurantes[restaurante]`, valores `Ventas` |
| Barras (Top 10) | Eje `bi_items_vendidos[producto]`, valores `Productos vendidos` (filtro Top N = 10) |
| Columnas | Eje `bi_ventas[dia_semana]` (ordenar por `dia_semana_num`), valores `Ventas` |

### Página 2 — Operación y afluencia

| Visual | Campos |
|---|---|
| 4 tarjetas | `Pedidos`, `Pedidos por día`, `% cancelados`, `Tiempo real prom (min)` |
| **Matriz de calor** | Filas `bi_pedidos[dia_semana]` (orden `dia_semana_num`), columnas `bi_pedidos[hora]`, valores `Pedidos`; formato condicional de color de fondo (escala crema → terracota). Muestra cuándo se llena el restaurante. |
| Columnas | Eje `bi_pedidos[hora]`, valores `Tiempo real prom (min)` |
| Dona | Leyenda `bi_pedidos[estado]`, valores `Pedidos` o `COUNTROWS` |
| Columnas | Eje `bi_pedidos[tipo_entrega]`, valores `Pedidos` |

### Página 3 — Inteligencia artificial

| Visual | Campos |
|---|---|
| 5 tarjetas | `Error promedio (min)`, `Acierto ±5 min`, `Acierto ±10 min`, `Real dentro del rango`, `Mejora vs promediar` |
| Dispersión | X `bi_ia_predicciones[minutos_estimados]`, Y `bi_ia_predicciones[minutos_reales]`, detalles `prediccion_id`. Cuanto más cerca de la diagonal, mejor. |
| Columnas | Eje `bi_ia_predicciones[nivel_carga]` (bajo/medio/alto), valores `Acierto ±5 min` |
| Histograma | Eje `Rango de error`, valores `Predicciones evaluadas` |
| Líneas | Eje `Calendario[Date]`, valores `Error promedio (min)` (¿mejora con el tiempo?) |
| Tabla | `bi_ia_modelos`: `version_texto`, `motivo`, `activo`, `muestras_reales`, `error_entrenamiento_min`, `error_si_promediara_min`, `mejora_vs_promedio_pct`, `r2` |
| Medidor | `Confianza promedio` |

### Página 4 — Clientes, menú e inventario

| Visual | Campos |
|---|---|
| 3 tarjetas | `Calificación promedio`, `Calificaciones`, `% 4 y 5 estrellas` |
| Barras | Eje `bi_calificaciones[categoria]`, valores `Calificación promedio` |
| Columnas | Eje `bi_calificaciones[estrellas]`, valores `Calificaciones` |
| Barras (Top/Bottom 10) | Eje `bi_calificaciones[producto]`, valores `Calificación promedio` |
| Tabla | `bi_calificaciones[producto]`, `estrellas`, `comentario`, `fecha` (solo con comentario) |
| Tarjetas + tabla | `Insumos bajo el mínimo`, `Valor del inventario`; tabla de `bi_inventario` filtrada por `bajo_el_minimo = True` |

---

## 6. Actualizar los datos

Los datos se **importan**: para ver pedidos nuevos pulsa **Actualizar** (Inicio → Actualizar).
Si cambias las vistas, corre otra vez `python -m app.core.bi_vistas` y luego Actualizar.

---

## 7. Para la tesis (sustentación)

- **Qué demuestra:** el módulo de IA no solo predice; el dashboard mide, con datos
  reales de la base, cuánto se equivoca (error en minutos, acierto ±5/±10, rango, mejora
  frente a promediar) y cómo evoluciona entre versiones del modelo.
- **Datos simulados:** el historial de demostración (`seed_historial`) está marcado con
  `es_simulado`. Declara en el documento que las cifras de rendimiento se obtuvieron con
  pedidos simulados y que con tráfico real pueden variar.
- **Seguridad:** Power BI se conecta con un usuario de solo lectura limitado a vistas
  (`waitless_bi`), nunca con el usuario dueño de la base de datos.
- **Alcance:** el dashboard es analítico para el dueño de la plataforma (ve todos los
  restaurantes y filtra con el segmentador); cada administrador ve solo su restaurante en
  la app móvil.
- Toma capturas de las 4 páginas para el capítulo de resultados / anexos.
