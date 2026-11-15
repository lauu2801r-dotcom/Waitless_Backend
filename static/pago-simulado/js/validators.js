/* WaitLess Pay (simulado) — utilidades y validaciones */
window.WL = window.WL || {};

WL.V = (function () {
  const cop = new Intl.NumberFormat("es-CO", {
    style: "currency", currency: "COP", maximumFractionDigits: 0
  });

  function formatCOP(n) { return cop.format(n); }

  function soloDigitos(s) { return String(s || "").replace(/\D+/g, ""); }

  // Algoritmo de Luhn
  function luhn(num) {
    const d = soloDigitos(num);
    if (d.length < 13) return false;
    let suma = 0, doble = false;
    for (let i = d.length - 1; i >= 0; i--) {
      let n = parseInt(d[i], 10);
      if (doble) { n *= 2; if (n > 9) n -= 9; }
      suma += n; doble = !doble;
    }
    return suma % 10 === 0;
  }

  function marca(num) {
    const d = soloDigitos(num);
    if (/^3[47]/.test(d)) return "amex";
    if (/^4/.test(d)) return "visa";
    if (/^(5[1-5]|2(2[2-9][1-9]|2[3-9]|[3-6]|7[01]|720))/.test(d)) return "mastercard";
    return "";
  }

  const marcaNombre = { visa: "VISA", mastercard: "MASTERCARD", amex: "AMEX", "": "" };

  function formatTarjeta(num) {
    const d = soloDigitos(num).slice(0, marca(num) === "amex" ? 15 : 16);
    if (marca(d) === "amex") {
      return [d.slice(0, 4), d.slice(4, 10), d.slice(10, 15)].filter(Boolean).join(" ");
    }
    return d.replace(/(.{4})/g, "$1 ").trim();
  }

  function formatVence(v) {
    const d = soloDigitos(v).slice(0, 4);
    if (d.length >= 3) return d.slice(0, 2) + "/" + d.slice(2);
    return d;
  }

  function venceValido(v) {
    const m = /^(\d{2})\/(\d{2})$/.exec(v);
    if (!m) return false;
    const mes = parseInt(m[1], 10), anio = 2000 + parseInt(m[2], 10);
    if (mes < 1 || mes > 12) return false;
    const hoy = new Date();
    const finMes = new Date(anio, mes, 0, 23, 59, 59);
    return finMes >= hoy && anio <= hoy.getFullYear() + 20;
  }

  function enmascarar(num) {
    const d = soloDigitos(num);
    return "•••• " + d.slice(-4);
  }

  function referencia() {
    const base = Math.random().toString(36).slice(2, 10).toUpperCase();
    return "WLP-" + base;
  }

  function fechaHora(d) {
    return d.toLocaleString("es-CO", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", hour12: true
    });
  }

  return {
    formatCOP, soloDigitos, luhn, marca, marcaNombre,
    formatTarjeta, formatVence, venceValido, enmascarar, referencia, fechaHora
  };
})();
