/* WaitLess Pay (simulado) — configuración y datos de prueba */
window.WL = window.WL || {};

WL.CONFIG = {
  marca: "WaitLess Pay",
  otpCorrecto: "123456",
  intentosOtp: 3,
  segundosReenvio: 30,

  // Valores por defecto si la app no manda parámetros en la URL
  demo: { monto: 48500, restaurante: "Casa Solera", pedido: "WL-1042" },

  // Tarjetas de prueba (todas pasan Luhn). Cualquier otra tarjeta válida se aprueba.
  tarjetasPrueba: {
    "4242424242424242": { ok: true },
    "4000000000000002": { ok: false, motivo: "declinada" },
    "4000000000009995": { ok: false, motivo: "fondos" },
    "4000000000000069": { ok: false, motivo: "vencida" }
  },

  // Lista de bancos de Colombia: solo el NOMBRE, en texto y con el mismo estilo para todos
  // (sin logos, colores ni pantallas de las entidades). Es una simulación de WaitLess Pay.
  bancos: [
    { id: "bancolombia", nombre: "Bancolombia" },
    { id: "davivienda",  nombre: "Davivienda" },
    { id: "bogota",      nombre: "Banco de Bogotá" },
    { id: "bbva",        nombre: "BBVA Colombia" },
    { id: "occidente",   nombre: "Banco de Occidente" },
    { id: "popular",     nombre: "Banco Popular" },
    { id: "avvillas",    nombre: "Banco AV Villas" },
    { id: "cajasocial",  nombre: "Banco Caja Social" }
  ],

  cuotas: [1, 3, 6, 12],

  motivos: {
    declinada: { titulo: "Tarjeta rechazada", detalle: "El banco emisor no autorizó la transacción. Prueba con otra tarjeta o método de pago." },
    fondos:    { titulo: "Fondos insuficientes", detalle: "El saldo disponible no alcanza para completar este pago." },
    vencida:   { titulo: "Tarjeta vencida", detalle: "La tarjeta ingresada ya expiró. Usa una tarjeta vigente." },
    otp:       { titulo: "Verificación fallida", detalle: "Superaste el número de intentos del código de seguridad." },
    banco:     { titulo: "Pago no autorizado", detalle: "Tu banco rechazó la autorización de este pago." },
    cancelado: { titulo: "Pago cancelado", detalle: "Cancelaste la operación. No se realizó ningún cobro." }
  }
};
