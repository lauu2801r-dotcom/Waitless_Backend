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

  // Bancos ficticios (no corresponden a entidades reales)
  bancos: [
    { id: "aurora",   nombre: "Banco Aurora",   color: "#e4572e" },
    { id: "meridian", nombre: "Banco Meridiano", color: "#2e86ab" },
    { id: "condor",   nombre: "Banco Cóndor",   color: "#6a4c93" },
    { id: "alba",     nombre: "Cooperativa Alba", color: "#3a9d5d" }
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
