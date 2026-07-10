/* La Mesa — cliente vanilla JS.
   Polling contra la API (WebSockets = paso 4). Sesión en localStorage.
   El cliente NUNCA calcula reglas: solo muestra lo que el servidor resolvió. */

"use strict";

// ---------------------------------------------------------------- estado

const S = {
  token: localStorage.getItem("token"),
  campaignId: +localStorage.getItem("campaignId") || null,
  playerId: +localStorage.getItem("playerId") || null,
  inviteCode: localStorage.getItem("inviteCode") || "",
  characterId: null,
  ultimoMsg: 0,
  campania: null,
  ficha: null,
  timer: null,
};

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- datos v1
// Solo catálogos para armar formularios; las reglas viven en el servidor.

const CLASES = {
  guerrero: "d10 · sin magia · tanque versátil",
  barbaro: "d12 · sin magia · furia y aguante",
  picaro: "d8 · sin magia · sigilo y precisión",
  monje: "d8 · sin magia · artes marciales",
  mago: "d6 · magia INT · arsenal arcano (preparados)",
  hechicero: "d8 · magia CAR · poder innato (conocidos)",
  brujo: "d6 · magia CAR · pacto, slots con descanso corto",
  clerigo: "d8 · magia SAB · fe y curación (preparados)",
  druida: "d8 · magia SAB · naturaleza (preparados)",
  bardo: "d8 · magia CAR · apoyo y encanto (conocidos)",
  paladin: "d10 · media magia CAR desde nv2 · juramento",
  ranger: "d10 · media magia SAB desde nv2 · cazador",
};
const CON_MAGIA_NV1 = ["mago", "hechicero", "brujo", "clerigo", "druida", "bardo"];

const HABILIDADES = ["atletismo","acrobacias","juego_de_manos","sigilo","arcanos",
  "historia","investigacion","naturaleza","religion","perspicacia","medicina",
  "percepcion","supervivencia","trato_con_animales","engano","intimidacion",
  "actuacion","persuasion"];

const ARMAS = ["daga","espada_corta","espada_larga","hacha_de_mano","hacha_de_batalla",
  "arco_corto","arco_largo","ballesta_de_mano","lanza","mazo","mandoble","baston","cimitarra"];

const ARMADURAS = ["cuero","cuero_tachonado","cota_de_malla_camisa","coraza",
  "media_armadura","cota_de_anillas","cota_de_malla","cota_de_placas"];

const CONJUROS_V1 = ["rayo_de_escarcha","llama_sagrada","toque_helado","luz",
  "proyectil_magico","curar_heridas","palabra_de_curacion","manos_ardientes",
  "escudo","armadura_de_mago","bendecir","perdicion","dormir","onda_atronadora",
  "hechizar_persona","marca_del_cazador","rociada_de_color","rayo_abrasador",
  "inmovilizar_persona","invisibilidad","paso_brumoso"];

const ATRS = ["FUE","DES","CON","INT","SAB","CAR"];

// ---------------------------------------------------------------- fetch

async function api(metodo, ruta, body) {
  const opts = { method: metodo, headers: {} };
  if (S.token) opts.headers["X-Player-Token"] = S.token;
  if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch("/api" + ruta, opts);
  if (!r.ok) {
    let det = "";
    try { det = (await r.json()).detail || ""; } catch {}
    const e = new Error(det || `HTTP ${r.status}`); e.status = r.status; throw e;
  }
  return r.json();
}

function marcarConexion(ok) {
  const el = $("ui-conexion");
  el.textContent = ok ? "● en línea" : "○ reconectando…";
  el.className = "pastilla pastilla-tenue " + (ok ? "ok" : "mal");
}

// ---------------------------------------------------------------- pantallas

function mostrar(pantalla) {
  for (const p of ["inicio", "personaje", "mesa"])
    $("pantalla-" + p).hidden = p !== pantalla;
}

function guardarSesion(d) {
  S.token = d.player_token; S.campaignId = d.campaign_id; S.playerId = d.player_id;
  if (d.invite_code) S.inviteCode = d.invite_code;
  localStorage.setItem("token", S.token);
  localStorage.setItem("campaignId", S.campaignId);
  localStorage.setItem("playerId", S.playerId);
  localStorage.setItem("inviteCode", S.inviteCode);
}

// ---------- inicio

$("btn-crear-camp").onclick = async () => {
  try {
    const d = await api("POST", "/campaigns", {
      nombre: $("inp-camp-nombre").value.trim() || "Campaña sin nombre",
      nombre_jugador: $("inp-jugador-1").value.trim() || "Jugador",
    });
    guardarSesion(d);
    prepararCreacionPJ(); mostrar("personaje");
  } catch (e) { mostrarError("inicio-error", e.message); }
};

$("btn-unirse").onclick = async () => {
  try {
    const d = await api("POST", "/campaigns/join", {
      invite_code: $("inp-invite").value.trim(),
      nombre_jugador: $("inp-jugador-2").value.trim() || "Jugador",
    });
    guardarSesion(d);
    prepararCreacionPJ(); mostrar("personaje");
  } catch (e) { mostrarError("inicio-error", e.message); }
};

function mostrarError(id, msg) { const el = $(id); el.textContent = msg; el.hidden = false; }

// ---------- creación de personaje

function prepararCreacionPJ() {
  const sel = $("pj-clase");
  if (!sel.options.length) {
    for (const c of Object.keys(CLASES)) sel.add(new Option(c, c));
    sel.onchange = () => {
      $("pj-clase-info").textContent = CLASES[sel.value];
      $("pj-magia").hidden = !CON_MAGIA_NV1.includes(sel.value);
    };
    sel.onchange();

    const ga = $("pj-atributos");
    for (const a of ATRS) {
      const l = document.createElement("label");
      l.innerHTML = `${a}<input type="number" min="3" max="18" value="10" data-atr="${a}">
                     <span class="mod-vista"></span>`;
      ga.appendChild(l);
    }
    ga.addEventListener("input", (ev) => {
      const v = +ev.target.value || 10;
      const m = Math.floor((v - 10) / 2);
      ev.target.nextElementSibling.textContent = (m >= 0 ? "+" : "") + m;
    });
    ga.querySelectorAll("input").forEach(i => i.dispatchEvent(new Event("input", {bubbles:true})));

    montarChips("pj-habilidades", HABILIDADES, 4);
    montarChips("pj-conjuros", CONJUROS_V1, 4, "chip-arcano");

    const sa = $("pj-armadura");
    for (const a of ARMADURAS) sa.add(new Option(a.replaceAll("_"," "), a));
    const sw = $("pj-arma");
    for (const a of ARMAS) sw.add(new Option(a.replaceAll("_"," "), a));
    sw.value = "espada_larga";
  }
}

function montarChips(id, items, max, extra = "") {
  const cont = $(id);
  cont.innerHTML = "";
  for (const it of items) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip " + extra; b.textContent = it.replaceAll("_", " ");
    b.dataset.valor = it;
    b.onclick = () => {
      if (!b.classList.contains("activo") &&
          cont.querySelectorAll(".activo").length >= max) return;
      b.classList.toggle("activo");
    };
    cont.appendChild(b);
  }
}

function chipsElegidos(id) {
  return [...$(id).querySelectorAll(".activo")].map(b => b.dataset.valor);
}

$("btn-crear-pj").onclick = async () => {
  const atributos = {};
  document.querySelectorAll("#pj-atributos input").forEach(i => atributos[i.dataset.atr] = +i.value);
  const clase = $("pj-clase").value;
  const conjuros = chipsElegidos("pj-conjuros");
  const cuerpo = {
    nombre: $("pj-nombre").value.trim() || "Aventurero",
    raza: $("pj-raza").value.trim() || "Humano",
    clase, atributos,
    habilidades: chipsElegidos("pj-habilidades"),
    armadura: $("pj-armadura").value || null,
    escudo: $("pj-escudo").checked,
    arma_equipada: $("pj-arma").value,
    // el server decide si son conocidos o preparados según clase; mandamos ambos
    conocidos: conjuros, preparados: conjuros,
  };
  try {
    await api("POST", "/characters", cuerpo);
    await entrarALaMesa();
  } catch (e) { mostrarError("pj-error", e.message); }
};

// ---------------------------------------------------------------- mesa

async function entrarALaMesa() {
  mostrar("mesa");
  $("ui-invite").textContent = "invitación: " + S.inviteCode;
  await refrescarTodo(true);
  if (S.timer) clearInterval(S.timer);
  S.timer = setInterval(() => refrescarTodo(false).catch(() => marcarConexion(false)), 3500);
}

async function refrescarTodo(inicial) {
  const camp = await api("GET", `/campaigns/${S.campaignId}`);
  marcarConexion(true);
  S.campania = camp;

  // mi personaje
  const mio = camp.personajes.find(p => p.player_id === S.playerId);
  if (mio) {
    S.characterId = mio.id;
    S.ficha = await api("GET", `/characters/${mio.id}/sheet`);
    pintarFicha(S.ficha);
  }

  pintarCabecera(camp);
  pintarCombate(camp);
  await pintarMensajes();
  if (inicial || Math.random() < 0.25)  // el mundo cambia lento: no en cada tick
    pintarMundo(await api("GET", `/campaigns/${S.campaignId}/state`));
}

function pintarCabecera(c) {
  $("ui-camp-nombre").textContent = c.nombre;
  $("ui-ubicacion").textContent = c.ubicacion ? "— " + c.ubicacion : "";
  const est = $("ui-estado");
  est.textContent = c.estado;
  est.classList.toggle("en-combate", c.estado === "combate");
}

// ---------- log de mensajes

async function pintarMensajes() {
  const nuevos = await api("GET",
    `/campaigns/${S.campaignId}/messages?since=${S.ultimoMsg}`);
  if (!nuevos.length) return;
  const log = $("ui-log");
  const abajo = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
  for (const m of nuevos) {
    S.ultimoMsg = Math.max(S.ultimoMsg, m.id);
    const div = document.createElement("div");
    div.className = "msg msg-" + m.autor;
    if (m.autor === "sistema") {
      div.innerHTML = `<span class="msg-texto">${esc(m.contenido)}</span>`;
    } else {
      div.innerHTML = `<span class="msg-autor">${esc(m.autor_nombre)}</span>
                       <span class="msg-texto">${esc(m.contenido)}</span>`;
    }
    log.appendChild(div);
  }
  if (abajo) log.scrollTop = log.scrollHeight;
}

function esc(t) {
  const d = document.createElement("div"); d.textContent = t ?? ""; return d.innerHTML;
}

// firma visual: sello de tirada insertado en el log tras cada acción propia
function sellarResolucion(r) {
  if (!r) return;
  const log = $("ui-log");
  const div = document.createElement("div");
  div.className = "msg";
  div.innerHTML = selloHTML(r);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function selloHTML(r) {
  if (r.tipo === "ataque" || r.tipo === "ataque_magico") {
    const ok = r.impacta;
    const cls = r.critico ? "critico" : ok ? "exito" : "fallo";
    let s = `<span class="sello ${cls}">🎲 d20 ${r.natural}${signo(r.bono_ataque ?? r.bono)}=`
          + `<b>${r.total}</b> vs CA ${r.ca_objetivo} → <b>${ok ? (r.critico ? "¡CRÍTICO!" : "IMPACTA") : "FALLA"}</b></span>`;
    if (r.danio) s += ` <span class="sello">⚔ ${r.danio.expr ?? ""} → <b>${r.danio.total_final}</b> daño</span>`;
    return s;
  }
  if (r.tipo === "habilidad") {
    const cls = r.critico ? "critico" : r.exito ? "exito" : "fallo";
    return `<span class="sello ${cls}">🎲 ${esc(r.habilidad)} d20 ${r.natural}${signo(r.bono)}=`
         + `<b>${r.total}</b> vs CD ${r.cd} → <b>${r.exito ? "ÉXITO" : esc(r.grado).replaceAll("_"," ").toUpperCase()}</b></span>`;
  }
  if (r.tipo === "curacion")
    return `<span class="sello exito">✦ curación <b>+${r.total_final ?? r.curado}</b> PG</span>`;
  if (r.tipo === "danio_auto")
    return `<span class="sello exito">✦ <b>${r.total_final}</b> daño automático</span>`;
  if (r.tipo === "danio_conjuro")
    return `<span class="sello">✦ daño <b>${r.final}</b></span>`;
  if (r.tipo === "salvacion")
    return `<span class="sello ${r.exito ? "fallo" : "exito"}">🛡 salvación enemiga d20 ${r.natural}${signo(r.bono)}=`
         + `<b>${r.total}</b> vs CD ${r.cd} → <b>${r.exito ? "RESISTE" : "FALLA"}</b></span>`;
  if (r.tipo === "condicion_aplicada")
    return `<span class="sello exito">✦ condición aplicada (${esc(r.conjuro)})</span>`;
  return "";
}
const signo = (n) => (n >= 0 ? "+" : "") + n;

// ---------- combate

function pintarCombate(c) {
  const barra = $("ui-combate-barra");
  const enCombate = c.estado === "combate" && c.combate;
  barra.hidden = !enCombate;
  $("composer-exploracion").hidden = enCombate;
  $("composer-combate").hidden = !enCombate;
  if (!enCombate) return;

  const orden = c.combate.orden;
  const idx = c.combate.turno_idx;
  barra.innerHTML = `<b>Ronda ${c.combate.ronda}</b> · ` + orden.map((e, i) => {
    const esNpc = e.tipo === "npc";
    const npc = esNpc && c.npcs_en_escena.find(n => "npc_" + n.id === e.id);
    const nombre = esNpc ? (npc ? npc.nombre : e.id)
      : (c.personajes.find(p => "pj_" + p.id === e.id)?.nombre ?? e.id);
    const salud = npc && npc.salud ? ` · ${npc.salud}` : "";
    return `<span class="turno-item ${esNpc ? "enemigo" : ""} ${i === idx ? "actual" : ""}">${esc(nombre)}${salud}</span>`;
  }).join("");

  // objetivos
  const sel = $("inp-objetivo");
  const vivos = c.npcs_en_escena.filter(n => n.vivo && n.actitud === "hostil");
  const actual = sel.value;
  sel.innerHTML = "";
  for (const n of vivos)
    sel.add(new Option(`${n.nombre}${n.salud ? " (" + n.salud + ")" : ""}`, n.id));
  if ([...sel.options].some(o => o.value === actual)) sel.value = actual;

  // conjuros
  const conConjuros = S.ficha && (S.ficha.preparados.length || S.ficha.conocidos.length);
  $("fila-conjuro").hidden = !conConjuros;
  if (conConjuros) {
    const sc = $("inp-conjuro");
    const lista = S.ficha.preparados.length ? S.ficha.preparados : S.ficha.conocidos;
    const antes = sc.value;
    sc.innerHTML = "";
    for (const cj of lista) sc.add(new Option(cj.replaceAll("_", " "), cj));
    if ([...sc.options].some(o => o.value === antes)) sc.value = antes;
  }

  const miTurno = orden[idx]?.id === "pj_" + S.characterId;
  $("btn-atacar").disabled = !miTurno;
  $("btn-cast").disabled = !miTurno;
  $("ui-turno-info").textContent = miTurno
    ? "Es tu turno. Elegí objetivo y actuá."
    : "Esperando el turno de los demás…";
}

$("btn-atacar").onclick = () => accionCombate("attack",
  { objetivo_npc_id: +$("inp-objetivo").value });

$("btn-cast").onclick = () => accionCombate("cast", {
  conjuro: $("inp-conjuro").value,
  objetivo_npc_id: +$("inp-objetivo").value || null,
});

async function accionCombate(tipo, body) {
  const btns = [$("btn-atacar"), $("btn-cast")];
  btns.forEach(b => b.disabled = true);
  try {
    const d = await api("POST", `/campaigns/${S.campaignId}/combat/${tipo}`, body);
    for (const r of (d.resoluciones ?? [d.resolucion])) sellarResolucion(r);
    for (const ev of d.turnos_npc ?? []) {
      if (ev.ataque) sellarResolucion(ev.ataque);
      if (ev.concentracion) sellarResolucion({ ...ev.concentracion, tipo: "habilidad", habilidad: "concentración" });
    }
    await refrescarTodo(false);
  } catch (e) {
    avisoSistema(e.message);
    btns.forEach(b => b.disabled = false);
  }
}

function avisoSistema(txt) {
  const log = $("ui-log");
  const d = document.createElement("div");
  d.className = "msg msg-sistema";
  d.textContent = "⚠ " + txt;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
}

// ---------- exploración

$("btn-say").onclick = enviarAccion;
$("inp-accion").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarAccion(); }
});

async function enviarAccion() {
  const texto = $("inp-accion").value.trim();
  if (!texto) return;
  $("inp-accion").value = "";
  $("btn-say").disabled = true;
  try {
    await api("POST", `/campaigns/${S.campaignId}/say`, { texto });
    await refrescarTodo(false);
  } catch (e) { avisoSistema(e.message); }
  $("btn-say").disabled = false;
}

$("btn-skill").onclick = async () => {
  $("btn-skill").disabled = true;
  try {
    const d = await api("POST", `/campaigns/${S.campaignId}/skill-check`, {
      habilidad: $("inp-habilidad").value,
      descripcion: $("inp-desc-habilidad").value.trim(),
    });
    sellarResolucion(d.resolucion);
    $("inp-desc-habilidad").value = "";
    await refrescarTodo(false);
  } catch (e) { avisoSistema(e.message); }
  $("btn-skill").disabled = false;
};

// ---------- ficha

function pintarFicha(f) {
  const pgPct = Math.round(100 * f.pg_actual / f.pg_max);
  const slotsHTML = Object.entries(f.slots).map(([nv, s]) => {
    const puntos = Array.from({ length: s.max }, (_, i) =>
      `<span class="punto-slot ${i < s.max - s.usados ? "lleno" : ""}"></span>`).join("");
    return `<div class="slots-fila">Nv${nv} ${puntos}</div>`;
  }).join("");
  const conds = f.condiciones.map(c =>
    `<span class="condicion-tag">${esc(c.tipo)}</span>`).join("");

  $("ui-ficha").innerHTML = `
    <h2>${esc(f.nombre)}</h2>
    <p class="clase-linea">${esc(f.raza)} ${esc(f.clase)} · nivel ${f.nivel} · ${f.xp} XP</p>
    <div class="barra-pg"><div style="width:${pgPct}%"></div></div>
    <span class="pg-texto">${f.pg_actual} / ${f.pg_max} PG</span>
    ${conds ? "<div>" + conds + "</div>" : ""}
    <div class="stat-grid">
      ${ATRS.map(a => `<div class="stat"><span class="n">${a}</span>
        <span class="v">${f.atributos[a].valor}</span>
        <span class="m">${signo(f.atributos[a].mod)}</span></div>`).join("")}
    </div>
    <div class="linea-dato"><span>CA</span><span>${f.ca}</span></div>
    <div class="linea-dato"><span>Iniciativa</span><span>${signo(f.iniciativa_mod)}</span></div>
    <div class="linea-dato"><span>Competencia</span><span>+${f.bc}</span></div>
    <div class="linea-dato"><span>Dados de golpe</span><span>${f.dados_golpe_disp}${f.dado_golpe}</span></div>
    <div class="linea-dato"><span>Arma</span><span>${esc(f.arma_equipada ?? "—")}</span></div>
    <div class="linea-dato"><span>Armadura</span><span>${esc(f.armadura ?? "—")}${f.escudo ? " + escudo" : ""}</span></div>
    ${slotsHTML ? "<h3 style='margin:.8rem 0 .2rem'>Espacios de conjuro</h3>" + slotsHTML : ""}
    ${f.concentracion ? `<div class="linea-dato"><span>Concentración</span><span>${esc(f.concentracion.hechizo)}</span></div>` : ""}
    ${f.competencias.habilidades.length ?
      `<h3 style='margin:.8rem 0 .2rem'>Competente en</h3>
       <p class="nota">${f.competencias.habilidades.map(h => esc(h.replaceAll("_"," "))).join(" · ")}</p>` : ""}
  `;
}

// ---------- mundo

function pintarMundo(st) {
  const quests = st.quests.filter(q => q.estado === "activa");
  const hechas = st.quests.filter(q => q.estado !== "activa");
  $("ui-mundo").innerHTML = `
    <h3>Misiones</h3>
    ${quests.length ? "<ul>" + quests.map(q =>
      `<li class="${q.principal ? "q-principal" : ""}"><b>${esc(q.titulo)}</b>
       ${q.descripcion ? "— " + esc(q.descripcion) : ""}</li>`).join("") + "</ul>"
      : '<p class="nota">Ninguna todavía. Salí a buscar problemas.</p>'}
    ${hechas.length ? `<p class="nota">${hechas.length} completada(s)/fallida(s)</p>` : ""}
    <h3>Personajes conocidos</h3>
    ${st.npcs_conocidos.length ? "<ul>" + st.npcs_conocidos.map(n =>
      `<li><b>${esc(n.nombre)}</b> ${n.rol ? "· " + esc(n.rol) : ""}
       <span class="actitud">${esc(n.actitud)}${n.en_escena ? " · presente" : ""}</span></li>`).join("") + "</ul>"
      : '<p class="nota">Nadie con nombre, aún.</p>'}
    ${st.consecuencias_pendientes ? `<h3>Presagios</h3>
      <p class="nota">Hay ${st.consecuencias_pendientes} consecuencia(s) pendiente(s) sobre el grupo…</p>` : ""}
    ${st.resumen ? `<h3>Crónica</h3><div class="resumen-caja">${esc(st.resumen)}</div>` : ""}
  `;
}

// ---------- tabs móvil

document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("activo", x === t));
  document.querySelectorAll("[data-panel]").forEach(p =>
    p.classList.toggle("visible", p.dataset.panel === t.dataset.tab));
});
document.querySelector('[data-panel="juego"]')?.classList.add("visible");

// ---------- selector de habilidades del composer

for (const h of HABILIDADES) $("inp-habilidad").add(new Option(h.replaceAll("_"," "), h));

// ---------------------------------------------------------------- arranque

(async function init() {
  if (!S.token || !S.campaignId) { mostrar("inicio"); return; }
  try {
    const camp = await api("GET", `/campaigns/${S.campaignId}`);
    const mio = camp.personajes.find(p => p.player_id === S.playerId);
    if (mio) { await entrarALaMesa(); }
    else { prepararCreacionPJ(); mostrar("personaje"); }
  } catch (e) {
    if (e.status === 401 || e.status === 403) {
      localStorage.clear(); mostrar("inicio");
    } else {
      // probablemente cold start de Render: reintentar
      mostrar("inicio");
      mostrarError("inicio-error", "Despertando el servidor… reintentá en unos segundos.");
    }
  }
})();
