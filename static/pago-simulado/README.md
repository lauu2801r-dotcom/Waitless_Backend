# WaitLess Pay (simulado)

Portal de pago de demostración para el proyecto WaitLess. **No procesa pagos reales**, no guarda
ni envía datos a ningún servidor y usa una marca y bancos ficticios.

## Estructura
```
pago-simulado/
├── index.html
├── css/styles.css
└── js/
    ├── config.js      (tarjetas de prueba, bancos ficticios, textos)
    ├── validators.js  (Luhn, formatos, fechas)
    └── app.js         (flujo: método → datos → verificación → resultado)
```

## Cómo abrirlo
- Local: doble clic en `index.html`.
- En Render (si lo pones en `static/pago-simulado/` del backend):
  `https://waitless-backend-zbr9.onrender.com/static/pago-simulado/index.html`

## Parámetros en la URL (todos opcionales)
| Parámetro | Ejemplo | Para qué |
|---|---|---|
| `monto` | `48500` | Valor a pagar en COP |
| `restaurante` | `Casa%20Solera` | Nombre del comercio |
| `pedido` | `WL-1042` | Referencia del pedido |
| `tipo` | `pedido`, `domicilio`, `reserva` | Texto del concepto |
| `retorno` | `https://…` o `waitless://pago` | A dónde vuelve al terminar |
| `sesion` | `600` | Segundos que dura la sesión de pago (por defecto 10 min). Para probar: `?sesion=10` |

Al terminar redirige a `retorno` agregando `estado` (`aprobado`, `rechazado`, `cancelado`),
`ref`, `metodo`, `monto`, `pedido` y, si no se aprobó, `motivo` y `motivo_texto`. También envía ese mismo resultado como JSON al canal
JavaScript `WaitLessPay` (webview_flutter) y por `postMessage`.

## Datos de prueba
Métodos: tarjeta de crédito (con cuotas), tarjeta débito y PSE · transferencia bancaria.
- Tarjeta aprobada: `4242 4242 4242 4242`
- Rechazada: `4000 0000 0000 0002`
- Fondos insuficientes: `4000 0000 0000 9995`
- Código de verificación (SMS simulado): `123456`
- PSE: lista de bancos de Colombia (solo el nombre, sin logos ni colores). Cualquier documento y
  clave de prueba funcionan; con la clave `0000` el banco rechaza.
- Botón "atrás": la app llama a `window.WL_atras()` para retroceder un paso dentro del portal.
