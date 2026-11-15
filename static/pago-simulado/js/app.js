/* WaitLess Pay (simulado) — lógica del flujo de pago */
(function () {
  "use strict";

  const C = WL.CONFIG;
  const V = WL.V;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* ---------- Parámetros que manda la app (todos opcionales) ---------- */
  const qs = new URLSearchParams(location.search);
  const retornoRaw = qs.get("retorno") || "";
  const params = {
    monto: Math.max(1000, parseInt(qs.get("monto"), 10) || C.demo.monto),
    restaurante: (qs.get("restaurante") || C.demo.restaurante).slice(0, 60),
    pedido: (qs.get("pedido") || C.demo.pedido).slice(0, 30),
    tipo: (qs.get("tipo") || "pedido").toLowerCase(),
    retorno: /^(https?:|waitless:)/i.test(retornoRaw) ? retornoRaw : ""
  };
  const tipoTexto = { pedido: "Pedido en restaurante", domicilio: "Pedido a domicilio", reserva: "Reserva de mesa" };

  /* ---------- Estado (solo en memoria; nada se guarda) ---------- */
  const state = { method: null, card: null, bank: null, otpFails: 0, result: null, timers: [] };

  /* ---------- Navegación entre vistas ---------- */
  // credit / debit comparten el formulario de tarjeta; pse usa el de banco
  const vistaDe = { credit: "card", debit: "card", pse: "bank" };
  const stepOf = {
    method: 1, card: 2, bank: 2,
    bankapprove: 3, otp: 3, processing: 3, result: 4
  };

  function show(name, opts) {
    $$(".view").forEach(v => v.classList.add("hidden"));
    const v = $("#view-" + name);
    v.classList.remove("hidden");
    // reiniciar animación
    v.style.animation = "none"; void v.offsetWidth; v.style.animation = "";
    updateStepper(stepOf[name], opts && opts.fail);
    window.scrollTo({ top: 0, behavior: "smooth" });
    const first = $("input:not([type=hidden]), select", v);
    if (first && name !== "otp" && name !== "result") setTimeout(() => first.focus({ preventScroll: true }), 300);
  }

  function updateStepper(n, fail) {
    const st = $("#stepper");
    st.classList.toggle("fail", !!fail);
    $$("li", st).forEach(li => {
      const k = +li.dataset.step;
      li.classList.toggle("done", k < n || (k === n && n === 4 && !fail));
      li.classList.toggle("active", k === n && !(n === 4 && !fail));
    });
  }

  /* ---------- Resumen ---------- */
  function pintarResumen() {
    const total = V.formatCOP(params.monto);
    $("#sumRest").textContent = params.restaurante;
    $("#sumAvatar").textContent = params.restaurante.trim().charAt(0).toUpperCase() || "R";
    $("#sumPedido").textContent = params.pedido;
    $("#sumTipo").textContent = tipoTexto[params.tipo] || tipoTexto.pedido;
    $("#sumSub").textContent = total;
    $("#sumTotal").textContent = total;
    $("#sumTotalMini").textContent = total;
    $("#sumToggle").addEventListener("click", () => {
      const open = $("#sumBody").classList.toggle("open");
      $("#sumToggle").setAttribute("aria-expanded", open);
    });
  }

  /* ---------- Errores de formulario ---------- */
  function setErr(key, msg) {
    const el = $('[data-err="' + key + '"]');
    if (el) el.textContent = msg || "";
  }
  function mark(input, bad) { if (input) input.classList.toggle("bad", !!bad); }

  /* ---------- 1. Método ---------- */
  function initMetodos() {
    $$(".method").forEach(b => b.addEventListener("click", () => {
      state.method = b.dataset.method;
      configurarTarjeta();
      show(vistaDe[state.method]);
    }));
    $$("[data-back]").forEach(b => b.addEventListener("click", atras));
    $("#btnCancelar").addEventListener("click", () => volver("cancelado"));
  }

  /* ---------- Volver un paso (botones, y botón "atrás" de la app) ---------- */
  function vistaActual() {
    const v = $$(".view").find(x => !x.classList.contains("hidden"));
    return v ? v.id.replace("view-", "") : "method";
  }
  function atras() {
    const v = vistaActual();
    if (v === "card" || v === "bank") { clearTimers(); show("method"); return true; }
    if (v === "bankapprove") { show("bank"); return true; }
    if (v === "otp") { clearTimers(); show("card"); return true; }
    return false; // método, procesando y resultado: la app decide
  }
  // La app (Flutter) llama a esto con el botón "atrás" del celular
  window.WL_atras = atras;

  function configurarTarjeta() {
    const esCredito = state.method === "credit";
    $("#cardTitle").textContent = esCredito ? "Datos de la tarjeta de crédito" : "Datos de la tarjeta débito";
    $("#rowCuotas").classList.toggle("hidden", !esCredito);
    $("#cCuotas").value = "1";
  }

  /* ---------- 2A. Tarjeta ---------- */
  function initTarjeta() {
    const num = $("#cNum"), name = $("#cName"), exp = $("#cExp"), cvv = $("#cCvv"), doc = $("#cDoc");
    const card = $("#card3d");

    C.cuotas.forEach(n => {
      const o = document.createElement("option");
      o.value = n;
      o.textContent = n === 1 ? "1 cuota (sin interés)" : n + " cuotas";
      $("#cCuotas").appendChild(o);
    });

    function pintarMarca() {
      const m = V.marca(num.value);
      card.classList.remove("visa", "mastercard", "amex");
      if (m) card.classList.add(m);
      $("#pvBrand").textContent = V.marcaNombre[m] || "";
      cvv.maxLength = m === "amex" ? 4 : 3;
      $("#pvCvv").textContent = "•".repeat(cvv.maxLength);
    }

    num.addEventListener("input", () => {
      num.value = V.formatTarjeta(num.value);
      $("#pvNum").textContent = num.value || "•••• •••• •••• ••••";
      pintarMarca(); setErr("cNum"); mark(num, false);
    });
    name.addEventListener("input", () => {
      name.value = name.value.replace(/[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]/g, "").toUpperCase();
      $("#pvName").textContent = name.value || "NOMBRE APELLIDO";
      setErr("cName"); mark(name, false);
    });
    exp.addEventListener("input", () => {
      exp.value = V.formatVence(exp.value);
      $("#pvExp").textContent = exp.value || "MM/AA";
      setErr("cExp"); mark(exp, false);
    });
    cvv.addEventListener("input", () => {
      cvv.value = V.soloDigitos(cvv.value);
      $("#pvCvv").textContent = cvv.value ? "•".repeat(cvv.value.length) : "•".repeat(cvv.maxLength);
      setErr("cCvv"); mark(cvv, false);
    });
    cvv.addEventListener("focus", () => card.classList.add("flip"));
    cvv.addEventListener("blur", () => card.classList.remove("flip"));
    doc.addEventListener("input", () => { doc.value = V.soloDigitos(doc.value); setErr("cDoc"); mark(doc, false); });

    $$("[data-fill]").forEach(b => b.addEventListener("click", () => {
      num.value = V.formatTarjeta(b.dataset.fill);
      $("#pvNum").textContent = num.value;
      pintarMarca();
      if (!name.value) { name.value = "VALENTINA GONZALEZ"; $("#pvName").textContent = name.value; }
      if (!exp.value) { exp.value = "12/30"; $("#pvExp").textContent = exp.value; }
      if (!cvv.value) { cvv.value = "123"; $("#pvCvv").textContent = "•••"; }
      if (!doc.value) doc.value = "1012345678";
      $$("#formCard .bad").forEach(i => i.classList.remove("bad"));
      $$("#formCard .err").forEach(e => e.textContent = "");
    }));

    $("#formCard").addEventListener("submit", e => {
      e.preventDefault();
      let ok = true;
      const digits = V.soloDigitos(num.value);
      if (!V.luhn(digits)) { setErr("cNum", "Número de tarjeta no válido."); mark(num, true); ok = false; }
      if (name.value.trim().split(/\s+/).filter(Boolean).length < 2) { setErr("cName", "Escribe nombre y apellido."); mark(name, true); ok = false; }
      if (!V.venceValido(exp.value)) { setErr("cExp", "Fecha inválida o vencida."); mark(exp, true); ok = false; }
      if (cvv.value.length !== cvv.maxLength) { setErr("cCvv", "CVV de " + cvv.maxLength + " dígitos."); mark(cvv, true); ok = false; }
      if (doc.value.length < 6) { setErr("cDoc", "Documento no válido."); mark(doc, true); ok = false; }
      if (!ok) return;
      state.card = { digits, cuotas: state.method === "credit" ? +$("#cCuotas").value : 1, marca: V.marca(digits) };
      abrirOtp("Ingresa el código de 6 dígitos que enviamos al celular asociado a tu tarjeta " + V.enmascarar(digits) + ".");
    });
  }

  /* ---------- 2B. Banco ---------- */
  // Mismo ícono genérico para todos los bancos (no se usan logos ni colores de las entidades)
  const SVG_BANCO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9.5L12 4l9 5.5M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"/></svg>';

  function initBanco() {
    const cont = $("#banksList");
    C.bancos.forEach(b => {
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "bank"; btn.dataset.id = b.id;
      btn.setAttribute("role", "radio"); btn.setAttribute("aria-checked", "false");
      btn.innerHTML = "<i>" + SVG_BANCO + "</i><span></span>";
      $("span", btn).textContent = b.nombre;
      btn.addEventListener("click", () => {
        $$(".bank", cont).forEach(x => { x.classList.remove("sel"); x.setAttribute("aria-checked", "false"); });
        btn.classList.add("sel"); btn.setAttribute("aria-checked", "true");
        state.bank = { id: b.id, nombre: b.nombre }; setErr("bank");
      });
      cont.appendChild(btn);
    });
    $("#bDoc").addEventListener("input", e => { e.target.value = V.soloDigitos(e.target.value); setErr("bDoc"); mark(e.target, false); });
    $("#bClave").addEventListener("input", e => { e.target.value = V.soloDigitos(e.target.value); setErr("bClave"); mark(e.target, false); });

    $("#formBank").addEventListener("submit", e => {
      e.preventDefault();
      let ok = true;
      if (!state.bank) { setErr("bank", "Selecciona tu banco."); ok = false; }
      if ($("#bDoc").value.length < 6) { setErr("bDoc", "Documento no válido."); mark($("#bDoc"), true); ok = false; }
      if ($("#bClave").value.length < 4) { setErr("bClave", "Mínimo 4 dígitos."); mark($("#bClave"), true); ok = false; }
      if (!ok) return;
      state.bank.clave = $("#bClave").value;
      const head = $("#bankHead");
      head.innerHTML = "<i>" + SVG_BANCO + "</i><div><small>Tu banco</small><strong></strong></div>";
      $("strong", head).textContent = state.bank.nombre;
      const kv = $("#bankKv");
      kv.innerHTML = "";
      [["Comercio", params.restaurante], ["Pedido", params.pedido], ["Cuenta", "Ahorros •••• 4821"], ["Valor", V.formatCOP(params.monto)]]
        .forEach(([k, v]) => {
          const d = document.createElement("div");
          d.innerHTML = "<dt></dt><dd></dd>";
          $("dt", d).textContent = k; $("dd", d).textContent = v;
          kv.appendChild(d);
        });
      show("bankapprove");
    });
    $("#btnBankBack").addEventListener("click", atras);
    $("#btnBankOk").addEventListener("click", () => {
      if (state.bank.clave === "0000") procesar({ ok: false, motivo: "banco" });
      else procesar({ ok: true });
    });
    $("#btnBankNo").addEventListener("click", () => procesar({ ok: false, motivo: "cancelado" }, true));
  }

  /* ---------- 3. OTP ---------- */
  let resendInterval = null;
  function abrirOtp(texto) {
    $("#otpLead").textContent = texto;
    state.otpFails = 0;
    const boxes = $$("#otpBoxes input");
    boxes.forEach(b => { b.value = ""; b.classList.remove("bad"); });
    $("#otpErr").textContent = "";
    show("otp");
    setTimeout(() => boxes[0].focus(), 350);
    clearTimers();
    state.timers.push(setTimeout(() => mostrarSms(), 1100));
    iniciarReenvio();
  }

  function mostrarSms() {
    const sms = $("#sms");
    $("#smsText").textContent = C.marca + ": tu código de verificación es " + C.otpCorrecto + ". No lo compartas con nadie.";
    sms.classList.add("show");
    state.timers.push(setTimeout(() => sms.classList.remove("show"), 9000));
  }

  function iniciarReenvio() {
    const btn = $("#btnResend"), t = $("#resendT");
    let s = C.segundosReenvio;
    btn.disabled = true; t.textContent = "(" + s + "s)";
    clearInterval(resendInterval);
    resendInterval = setInterval(() => {
      s--;
      if (s <= 0) { clearInterval(resendInterval); btn.disabled = false; t.textContent = ""; }
      else t.textContent = "(" + s + "s)";
    }, 1000);
  }

  function initOtp() {
    const boxes = $$("#otpBoxes input");
    boxes.forEach((b, i) => {
      b.addEventListener("input", () => {
        b.value = V.soloDigitos(b.value).slice(-1);
        b.classList.remove("bad"); $("#otpErr").textContent = "";
        if (b.value && i < boxes.length - 1) boxes[i + 1].focus();
        if (boxes.every(x => x.value)) verificarOtp();
      });
      b.addEventListener("keydown", e => {
        if (e.key === "Backspace" && !b.value && i > 0) boxes[i - 1].focus();
        if (e.key === "Enter") verificarOtp();
      });
      b.addEventListener("paste", e => {
        const txt = V.soloDigitos((e.clipboardData || window.clipboardData).getData("text")).slice(0, 6);
        if (!txt) return;
        e.preventDefault();
        txt.split("").forEach((ch, k) => { boxes[k].value = ch; });
        boxes[Math.min(txt.length, 5)].focus();
        if (txt.length === 6) verificarOtp();
      });
    });
    $("#btnOtp").addEventListener("click", verificarOtp);
    $("#sms").addEventListener("click", () => {
      C.otpCorrecto.split("").forEach((ch, k) => { boxes[k].value = ch; });
      $("#sms").classList.remove("show");
      verificarOtp();
    });
    $("#btnResend").addEventListener("click", () => { mostrarSms(); iniciarReenvio(); });
  }

  function verificarOtp() {
    const boxes = $$("#otpBoxes input");
    const code = boxes.map(b => b.value).join("");
    if (code.length < 6) { $("#otpErr").textContent = "Ingresa los 6 dígitos."; return; }
    if (code === C.otpCorrecto) {
      $("#sms").classList.remove("show");
      clearInterval(resendInterval);
      decidir();
    } else {
      state.otpFails++;
      const restan = C.intentosOtp - state.otpFails;
      const row = $("#otpBoxes");
      row.classList.remove("shake"); void row.offsetWidth; row.classList.add("shake");
      boxes.forEach(b => b.classList.add("bad"));
      if (restan <= 0) { clearInterval(resendInterval); procesar({ ok: false, motivo: "otp" }); return; }
      $("#otpErr").textContent = "Código incorrecto. Te quedan " + restan + (restan === 1 ? " intento." : " intentos.");
      boxes.forEach(b => b.value = ""); boxes[0].focus();
    }
  }

  /* ---------- Decisión del resultado según método ---------- */
  function decidir() {
    // Tarjeta crédito / débito
    const t = C.tarjetasPrueba[state.card.digits];
    procesar(t && !t.ok ? { ok: false, motivo: t.motivo } : { ok: true });
  }

  /* ---------- 4. Procesando ---------- */
  function procesar(resultado, rapido) {
    clearTimers();
    if (rapido) { terminar(resultado); return; }
    show("processing");
    const items = $$("#procList li");
    items.forEach(li => li.className = "");
    items.forEach((li, i) => {
      state.timers.push(setTimeout(() => {
        if (i > 0) items[i - 1].className = "done";
        li.className = "on";
      }, i * 720));
    });
    state.timers.push(setTimeout(() => {
      items[items.length - 1].className = "done";
      state.timers.push(setTimeout(() => terminar(resultado), 450));
    }, items.length * 720));
  }

  /* ---------- 5. Resultado ---------- */
  const SVG_OK = '<svg viewBox="0 0 52 52" fill="none" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="26" cy="26" r="25"/><path d="M14 27l8 8 16-17"/></svg>';
  const SVG_BAD = '<svg viewBox="0 0 52 52" fill="none" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="26" cy="26" r="25"/><path d="M17 17l18 18M35 17L17 35"/></svg>';

  function metodoTexto() {
    if (state.method === "pse") return "PSE · " + state.bank.nombre;
    const m = V.marcaNombre[state.card.marca] || "Tarjeta";
    const marca = m.charAt(0) + m.slice(1).toLowerCase();
    return (state.method === "credit" ? "Crédito · " : "Débito · ") + marca + " " + V.enmascarar(state.card.digits);
  }

  /* Datos del movimiento que se muestra como en un extracto */
  function movimiento(ahora) {
    let cuenta, detalle;
    if (state.method === "pse") {
      cuenta = state.bank.nombre + " · Ahorros •••• 4821";
      detalle = "Débito aplicado";
    } else if (state.method === "debit") {
      cuenta = "Tarjeta débito " + V.enmascarar(state.card.digits);
      detalle = "Débito aplicado";
    } else {
      cuenta = "Tarjeta de crédito " + V.enmascarar(state.card.digits);
      detalle = state.card.cuotas > 1 ? "Cargo a " + state.card.cuotas + " cuotas" : "Cargo a tu tarjeta";
    }
    return { cuenta: cuenta, detalle: detalle, fecha: V.fechaHora(ahora) };
  }

  function terminar(r) {
    const body = $("#resultBody");
    body.innerHTML = "";
    const ahora = new Date();

    if (r.ok) {
      const ref = V.referencia();
      state.result = { estado: "aprobado", ref };
      body.innerHTML =
        '<div class="res-ico ok">' + SVG_OK + "</div>" +
        '<h1 class="res-title">¡Pago aprobado!</h1>' +
        '<p class="res-sub">Tu pedido fue confirmado con <b class="r-rest"></b>.</p>' +
        '<div class="ticket"><div class="watermark">SIMULADO</div>' +
        '<div class="t-amount"><small>Valor pagado</small><b class="r-monto"></b></div>' +
        '<dl class="kv"></dl>' +
        '<p class="t-note">Comprobante de prueba generado por un simulador. No tiene validez comercial ni tributaria.</p></div>' +
        '<div class="movimiento"><div class="mv-ico">−</div>' +
        '<div class="mv-txt"><small>Movimiento en tu cuenta</small><b class="mv-det"></b><span class="mv-cta"></span></div>' +
        '<div class="mv-monto"></div></div>' +
        '<div class="res-actions">' +
        '<button class="btn-primary" id="btnVolver" type="button">Volver a WaitLess</button>' +
        '<button class="btn-ghost" id="btnPrint" type="button">Imprimir comprobante</button></div>';
      $(".r-rest", body).textContent = params.restaurante;
      $(".r-monto", body).textContent = V.formatCOP(params.monto);
      const filas = [
        ["Referencia", ref],
        ["Fecha", V.fechaHora(ahora)],
        ["Pedido", params.pedido],
        ["Método", metodoTexto()]
      ];
      if (state.method === "credit" && state.card.cuotas > 1) filas.push(["Cuotas", state.card.cuotas]);
      const mv = movimiento(ahora);
      $(".mv-det", body).textContent = mv.detalle + " · " + params.restaurante;
      $(".mv-cta", body).textContent = mv.cuenta + " · " + mv.fecha;
      $(".mv-monto", body).textContent = "−" + V.formatCOP(params.monto);
      filas.push(["Movimiento", mv.detalle]);
      filas.push(["Estado", "Aprobado"]);
      const kv = $(".kv", body);
      filas.forEach(([k, v]) => {
        const d = document.createElement("div");
        d.innerHTML = "<dt></dt><dd></dd>";
        $("dt", d).textContent = k; $("dd", d).textContent = v;
        kv.appendChild(d);
      });
      $("#btnVolver").addEventListener("click", () => volver("aprobado"));
      $("#btnPrint").addEventListener("click", () => window.print());
      show("result");
    } else {
      const m = C.motivos[r.motivo] || C.motivos.declinada;
      const cancel = r.motivo === "cancelado";
      state.result = { estado: cancel ? "cancelado" : "rechazado", motivo: r.motivo };
      body.innerHTML =
        '<div class="res-ico bad">' + SVG_BAD + "</div>" +
        '<h1 class="res-title"></h1><p class="res-sub"></p>' +
        '<div class="hint-box"><small>No se hizo ningún cobro. Puedes intentar de nuevo con otro método.</small></div>' +
        '<div class="res-actions">' +
        '<button class="btn-primary" id="btnRetry" type="button">Intentar con otro método</button>' +
        '<button class="btn-ghost" id="btnSalir" type="button">Cancelar y volver a WaitLess</button></div>';
      $(".res-title", body).textContent = m.titulo;
      $(".res-sub", body).textContent = m.detalle;
      $("#btnRetry").addEventListener("click", reiniciar);
      $("#btnSalir").addEventListener("click", () => volver(state.result.estado));
      show("result", { fail: true });
    }
  }

  function reiniciar() {
    state.method = null; state.card = null; state.bank = null; state.result = null;
    ["#formCard", "#formBank"].forEach(f => $(f).reset());
    $$(".bad").forEach(x => x.classList.remove("bad"));
    $$(".err").forEach(x => x.textContent = "");
    $$(".bank").forEach(x => x.classList.remove("sel"));
    $("#pvNum").textContent = "•••• •••• •••• ••••";
    $("#pvName").textContent = "NOMBRE APELLIDO";
    $("#pvExp").textContent = "MM/AA";
    $("#card3d").classList.remove("visa", "mastercard", "amex", "flip");
    $("#pvBrand").textContent = "";
    show("method");
  }

  /* ---------- Regreso a la app ---------- */
  function volver(estado) {
    const r = state.result || {};
    const payload = {
      estado: estado,
      ref: r.ref || "",
      metodo: state.method || "",
      monto: params.monto,
      pedido: params.pedido,
      simulado: true
    };
    const json = JSON.stringify(payload);

    // 1) Canal JavaScript de Flutter (webview_flutter): JavaScriptChannel "WaitLessPay"
    try { if (window.WaitLessPay && window.WaitLessPay.postMessage) window.WaitLessPay.postMessage(json); } catch (e) {}
    // 2) Ventana que lo abrió / iframe
    try { if (window.opener) window.opener.postMessage({ waitlessPay: payload }, "*"); } catch (e) {}
    try { if (window.parent !== window) window.parent.postMessage({ waitlessPay: payload }, "*"); } catch (e) {}

    // 3) Redirección a la URL de retorno (deep link o web)
    if (params.retorno) {
      const q = new URLSearchParams({
        estado: payload.estado, ref: payload.ref, metodo: payload.metodo,
        monto: payload.monto, pedido: payload.pedido
      }).toString();
      location.href = params.retorno + (params.retorno.includes("?") ? "&" : "?") + q;
      return;
    }
    // 4) Sin retorno: avisar
    avisoFinal(estado);
  }

  function avisoFinal(estado) {
    const body = $("#resultBody");
    $$(".view").forEach(v => v.classList.add("hidden"));
    $("#view-result").classList.remove("hidden");
    body.innerHTML =
      '<div class="res-ico ' + (estado === "aprobado" ? "ok" : "bad") + '">' + (estado === "aprobado" ? SVG_OK : SVG_BAD) + "</div>" +
      '<h1 class="res-title">Ya puedes volver a la app</h1>' +
      '<p class="res-sub">Cierra esta ventana para regresar a WaitLess. ' +
      '<span style="display:block;margin-top:6px;font-size:13px;color:#8a9aa1">(Modo demostración: no se configuró una URL de retorno.)</span></p>' +
      '<div class="res-actions"><button class="btn-ghost" id="btnNuevo" type="button">Probar otro pago</button></div>';
    $("#btnNuevo").addEventListener("click", reiniciar);
  }

  /* ---------- Utilidades ---------- */
  function clearTimers() {
    state.timers.forEach(clearTimeout); state.timers = [];
    clearInterval(resendInterval);
    $("#sms").classList.remove("show");
  }

  /* ---------- Inicio ---------- */
  pintarResumen();
  initMetodos();
  initTarjeta();
  initBanco();
  initOtp();
  show("method");
})();
