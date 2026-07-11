/* La Mesa — cliente vanilla JS (versión completa).
   Polling adaptativo, narración en background, descansos, inventario,
   subida de nivel, retomar campaña, reemplazo tras muerte. */

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
  narrando: false,
  rapidoHasta: 0,      // epoch ms: pollear rápido hasta este momento
  timerId: null,
};

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- catálogos

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
const CON_MAGIA_NV1 = ["mago","hechicero","brujo","clerigo","druida","bardo"];

const HABILIDADES = ["atletismo","acrobacias","juego_de_manos","sigilo","arcanos",
  "historia","investigacion","naturaleza","religion","perspicacia","medicina",
  "percepcion","supervivencia","trato_con_animales","engano","intimidacion",
  "actuacion","persuasion"];

const ARMAS = ["daga","espada_corta","espada_larga","hacha_de_mano","hacha_de_batalla",
  "arco_corto","arco_largo","ballesta_de_mano","lanza","mazo","mandoble","baston","cimitarra"];

const ARMADURAS = ["cuero","cuero_tachonado","camisa_de_mallas","coraza",
  "media_armadura","ring_mail","cota_de_mallas","armadura_de_placas"];

const CONJUROS_V1 = ["rayo_de_escarcha","llama_sagrada","toque_helado","luz",
  "proyectil_magico","curar_heridas","palabra_de_curacion","manos_ardientes",
  "escudo","armadura_de_mago","bendecir","perdicion","dormir","onda_atronadora",
  "hechizar_persona","marca_del_cazador","rociada_de_color","rayo_abrasador",
  "inmovilizar_persona","invisibilidad","paso_brumoso"];

let CONJUROS_SERVER = null;  // {clave: {nivel, nombre}} desde /api/content
let CATALOGO = null;         // /api/content completo (razas, subclases...)

async function cargarCatalogo() {
  if (CATALOGO) return CATALOGO;
  try {
    const r = await fetch("/api/content");
    CATALOGO = await r.json();
    CONJUROS_SERVER = CATALOGO.conjuros;
    // el server es la fuente de verdad de razas: pisar el espejo local
    if (CATALOGO.razas) {
      for (const k of Object.keys(RAZAS)) delete RAZAS[k];
      for (const [k, r] of Object.entries(CATALOGO.razas)) {
        RAZAS[k] = {
          bonos: r.bonos,
          sub: Object.fromEntries(Object.entries(r.subrazas)
                 .map(([sk, sv]) => [sk, sv.bonos])),
          subInfo: r.subrazas,
          eleccion: r.bonos_a_eleccion || undefined,
          info: infoRaza(r),
        };
      }
    }
  } catch {}
  return CATALOGO;
}

function fmtBonos(bonos) {
  return Object.entries(bonos || {})
    .map(([a, b]) => `+${b} ${a}`).join(", ");
}

function infoRaza(r) {
  const partes = [fmtBonos(r.bonos)];
  if (r.bonos_a_eleccion) partes.push(`+1 a ${r.bonos_a_eleccion} atributos a elección`);
  partes.push(`${r.velocidad_m}m`);
  if (r.rasgo) partes.push(r.rasgo);
  return partes.filter(Boolean).join(" · ");
}
const RAZAS = {
  humano:   {bonos:{FUE:1,DES:1,CON:1,INT:1,SAB:1,CAR:1}, sub:{}, info:"+1 a todo · 9m"},
  elfo:     {bonos:{DES:2}, sub:{alto_elfo:{INT:1}, elfo_de_los_bosques:{SAB:1}, drow:{CAR:1}}, info:"+2 DES · visión nocturna"},
  enano:    {bonos:{CON:2}, sub:{enano_de_las_colinas:{SAB:1}, enano_de_las_montanas:{FUE:2}}, info:"+2 CON · 7m · resiste veneno"},
  mediano:  {bonos:{DES:2}, sub:{piesligeros:{CAR:1}, fornido:{CON:1}}, info:"+2 DES · 7m · suertudo"},
  gnomo:    {bonos:{INT:2}, sub:{gnomo_del_bosque:{DES:1}, gnomo_de_las_rocas:{CON:1}}, info:"+2 INT · 7m"},
  semielfo: {bonos:{CAR:2}, sub:{}, eleccion:2, info:"+2 CAR y +1 a dos atributos a elección"},
  semiorco: {bonos:{FUE:2,CON:1}, sub:{}, info:"+2 FUE +1 CON · aguante implacable"},
  draconido:{bonos:{FUE:2,CAR:1}, sub:{}, info:"+2 FUE +1 CAR · aliento de dragón"},
  tiflin:   {bonos:{CAR:2,INT:1}, sub:{}, info:"+2 CAR +1 INT · resiste fuego"},
};
const COSTO_PB = {8:0,9:1,10:2,11:3,12:4,13:5,14:7,15:9};

const ALINEAMIENTOS = ["legal_bueno","neutral_bueno","caotico_bueno",
  "legal_neutral","neutral","caotico_neutral",
  "legal_malvado","neutral_malvado","caotico_malvado"];
const ESTILOS = {defensa:"+1 CA con armadura", duelo:"+2 daño melé a una mano",
  arqueria:"+2 ataque a distancia"};
const HABILIDADES_CLASE_UI = {
  furia:            {icono:"💢", label:"Furia", combate:true},
  nuevo_aliento:    {icono:"❤️", label:"Nuevo aliento", combate:false},
  oleada_de_accion: {icono:"⚡", label:"Oleada de acción", combate:true},
  canalizar_divinidad:{icono:"✝️", label:"Canalizar divinidad", combate:false, aliado:true},
  imposicion_de_manos:{icono:"🙏", label:"Imposición de manos", combate:false, aliado:true, cantidad:true},
  inspiracion_bardica:{icono:"🎵", label:"Inspiración", combate:false, aliado:true, requiere_aliado:true},
};

const CONSUMIBLES_USABLES = new Set(["pocion_de_curacion","pocion_de_curacion_mayor"]);
const ATRS = ["FUE","DES","CON","INT","SAB","CAR"];
const TIMEOUT_TURNO = 120;

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

function acelerarPolling(seg = 25) { S.rapidoHasta = Date.now() + seg * 1000; }

// ---------------------------------------------------------------- pantallas

function mostrar(p) {
  for (const x of ["inicio","personaje","mesa"]) $("pantalla-"+x).hidden = x !== p;
}

function guardarSesion(d) {
  S.token = d.player_token ?? S.token;
  S.campaignId = d.campaign_id; S.playerId = d.player_id;
  if (d.invite_code) S.inviteCode = d.invite_code;
  localStorage.setItem("token", S.token);
  localStorage.setItem("campaignId", S.campaignId);
  localStorage.setItem("playerId", S.playerId);
  localStorage.setItem("inviteCode", S.inviteCode);
}

function mostrarError(id, msg) { const el = $(id); el.textContent = msg; el.hidden = false; }

// ---------- inicio

$("btn-crear-camp").onclick = async () => {
  try {
    const d = await api("POST","/campaigns",{
      nombre: $("inp-camp-nombre").value.trim() || "Campaña sin nombre",
      descripcion: $("inp-camp-desc").value.trim(),
      nombre_jugador: $("inp-jugador-1").value.trim() || "Jugador"});
    guardarSesion(d);
    alert("Guardá tu llave de jugador (sirve para retomar la campaña en "
        + "cualquier dispositivo):\n\n" + S.token);
    prepararCreacionPJ(); mostrar("personaje");
  } catch(e){ mostrarError("inicio-error", e.message); }
};

$("btn-unirse").onclick = async () => {
  try {
    const d = await api("POST","/campaigns/join",{
      invite_code: $("inp-invite").value.trim(),
      nombre_jugador: $("inp-jugador-2").value.trim() || "Jugador"});
    guardarSesion(d);
    alert("Guardá tu llave de jugador:\n\n" + S.token);
    prepararCreacionPJ(); mostrar("personaje");
  } catch(e){ mostrarError("inicio-error", e.message); }
};

$("btn-retomar").onclick = async () => {
  const llave = $("inp-llave").value.trim();
  if (!llave) return;
  S.token = llave; localStorage.setItem("token", llave);
  try {
    const me = await api("GET","/campaigns/me");
    guardarSesion({campaign_id: me.campaign_id, player_id: me.player_id,
                   invite_code: me.invite_code});
    if (me.character_id) await entrarALaMesa();
    else { prepararCreacionPJ(); mostrar("personaje"); }
  } catch(e){
    S.token = null; localStorage.removeItem("token");
    mostrarError("inicio-error", "Llave inválida: " + e.message);
  }
};

// ---------- creación de personaje

async function prepararCreacionPJ() {
  await cargarCatalogo();
  const sel = $("pj-clase");
  if (sel.options.length) { actualizarPB(); return; }
  for (const c of Object.keys(CLASES)) sel.add(new Option(c, c));
  sel.onchange = () => {
    $("pj-clase-info").textContent = CLASES[sel.value];
    $("pj-magia").hidden = !CON_MAGIA_NV1.includes(sel.value);
    $("lbl-estilo").hidden = sel.value !== "guerrero";
    $("pj-estilo-info").textContent = sel.value === "guerrero"
      ? ESTILOS[$("pj-estilo").value] : "";
  };
  const sal = $("pj-alineamiento");
  for (const a of ALINEAMIENTOS) sal.add(new Option(a.replaceAll("_"," "), a));
  sal.value = "neutral";
  const se = $("pj-estilo");
  for (const e of Object.keys(ESTILOS)) se.add(new Option(e, e));
  se.onchange = () => $("pj-estilo-info").textContent = ESTILOS[se.value];
  sel.onchange();

  // razas
  const sr = $("pj-raza");
  for (const r of Object.keys(RAZAS)) sr.add(new Option(r.replaceAll("_"," "), r));
  const infoSubraza = () => {
    const r = RAZAS[$("pj-raza").value];
    const base = r.info;
    if (!$("lbl-subraza").hidden && r.subInfo) {
      const sv = r.subInfo[$("pj-subraza").value];
      if (sv) {
        const extra = [fmtBonos(sv.bonos), sv.velocidad_m ? `${sv.velocidad_m}m` : "",
                       sv.rasgo].filter(Boolean).join(" · ");
        $("pj-raza-info").textContent = base + "\n↳ Subraza: " + extra;
        return;
      }
    }
    $("pj-raza-info").textContent = base;
  };
  sr.onchange = () => {
    const r = RAZAS[sr.value];
    const conSub = Object.keys(r.sub).length > 0;
    $("lbl-subraza").hidden = !conSub;
    if (conSub) {
      const ss = $("pj-subraza"); ss.innerHTML = "";
      for (const s of Object.keys(r.sub)) ss.add(new Option(s.replaceAll("_"," "), s));
    }
    infoSubraza();
    $("lbl-eleccion").hidden = !r.eleccion;
    if (r.eleccion) {
      for (const id of ["pj-eleccion-1","pj-eleccion-2"]) {
        const e = $(id); e.innerHTML = "";
        for (const a of ATRS) if (!(a in r.bonos)) e.add(new Option(a, a));
      }
      $("pj-eleccion-2").selectedIndex = 1;
    }
    actualizarPB();
  };
  sr.onchange();

  // atributos
  const ga = $("pj-atributos");
  for (const a of ATRS) {
    const l = document.createElement("label");
    l.innerHTML = `${a}<input type="number" min="8" max="15" value="8" data-atr="${a}">
                   <span class="mod-vista"></span>`;
    ga.appendChild(l);
  }
  ga.addEventListener("input", actualizarPB);
  $("pj-subraza").addEventListener("change", () => { infoSubraza(); actualizarPB(); });
  ["pj-eleccion-1","pj-eleccion-2"].forEach(id=>$(id).addEventListener("change", actualizarPB));

  // toggle método
  $("modo-puntos").onclick = () => setModo("puntos");
  $("modo-libre").onclick = () => setModo("libre");
  setModo("puntos");

  montarChips("pj-habilidades", HABILIDADES, 4);
  cargarConjurosCreacion();

  const sa = $("pj-armadura");
  for (const a of ARMADURAS) sa.add(new Option(a.replaceAll("_"," "), a));
  const sw = $("pj-arma");
  for (const a of ARMAS) sw.add(new Option(a.replaceAll("_"," "), a));
  sw.value = "espada_larga";
}

let modoAtributos = "puntos";
function setModo(m) {
  modoAtributos = m;
  $("modo-puntos").classList.toggle("activo", m === "puntos");
  $("modo-libre").classList.toggle("activo", m === "libre");
  document.querySelectorAll("#pj-atributos input").forEach(i=>{
    i.min = m === "puntos" ? 8 : 3;
    i.max = m === "puntos" ? 15 : 18;
    i.value = Math.max(+i.min, Math.min(+i.max, +i.value || 8));
  });
  actualizarPB();
}

function bonosRacialesActuales() {
  const r = RAZAS[$("pj-raza").value];
  const bonos = {...r.bonos};
  if (!$("lbl-subraza").hidden) {
    const sb = r.sub[$("pj-subraza").value] || {};
    for (const [a,b] of Object.entries(sb)) bonos[a] = (bonos[a]||0) + b;
  }
  if (r.eleccion) {
    for (const id of ["pj-eleccion-1","pj-eleccion-2"])
      bonos[$(id).value] = (bonos[$(id).value]||0) + 1;
  }
  return bonos;
}

function actualizarPB() {
  const bonos = bonosRacialesActuales();
  let gastado = 0;
  document.querySelectorAll("#pj-atributos input").forEach(i=>{
    const base = +i.value || 8;
    if (modoAtributos === "puntos") gastado += COSTO_PB[base] ?? 99;
    const final = base + (bonos[i.dataset.atr] || 0);
    const m = Math.floor((final - 10) / 2);
    i.nextElementSibling.textContent =
      (bonos[i.dataset.atr] ? `→${final} ` : "") + (m>=0?"+":"") + m;
  });
  const info = $("pj-puntos-info");
  if (modoAtributos === "puntos") {
    info.textContent = `Puntos usados: ${gastado} / 27` +
      (gastado > 27 ? " ⚠ te pasaste" : "");
    info.style.color = gastado > 27 ? "var(--brasa)" : "";
  } else {
    info.textContent = "Modo libre: valores 3–18 a criterio de la mesa.";
    info.style.color = "";
  }
}

async function cargarConjurosCreacion() {
  let lista = CONJUROS_V1;
  try {
    if (!CONJUROS_SERVER) {
      const r = await fetch("/api/content");
      CONJUROS_SERVER = (await r.json()).conjuros;
    }
    // en creación (nivel 1): trucos y nivel 1
    lista = Object.entries(CONJUROS_SERVER)
      .filter(([,v]) => v.nivel <= 1)
      .sort((a,b) => a[1].nivel - b[1].nivel || a[0].localeCompare(b[0]))
      .map(([k]) => k);
  } catch {}
  montarChips("pj-conjuros", lista, 4, "chip-arcano");
  // filtro de texto si hay muchos
  if (lista.length > 30 && !$("filtro-conjuros")) {
    const inp = document.createElement("input");
    inp.id = "filtro-conjuros"; inp.placeholder = "Filtrar conjuros…";
    inp.style.marginBottom = ".4rem";
    $("pj-conjuros").before(inp);
    inp.oninput = () => {
      const q = inp.value.toLowerCase();
      $("pj-conjuros").querySelectorAll(".chip").forEach(c =>
        c.style.display = c.dataset.valor.includes(q) ||
                          c.classList.contains("activo") ? "" : "none");
    };
  }
}

function montarChips(id, items, max, extra="") {
  const cont = $(id); cont.innerHTML = "";
  for (const it of items) {
    const b = document.createElement("button");
    b.type="button"; b.className="chip "+extra;
    b.textContent = it.replaceAll("_"," "); b.dataset.valor = it;
    b.onclick = () => {
      if (!b.classList.contains("activo") &&
          cont.querySelectorAll(".activo").length >= max) return;
      b.classList.toggle("activo");
    };
    cont.appendChild(b);
  }
}
const chipsElegidos = (id) => [...$(id).querySelectorAll(".activo")].map(b=>b.dataset.valor);

$("btn-crear-pj").onclick = async () => {
  const atributos = {};
  document.querySelectorAll("#pj-atributos input").forEach(i=>atributos[i.dataset.atr]=+i.value);
  const conjuros = chipsElegidos("pj-conjuros");
  try {
    const razaSel = RAZAS[$("pj-raza").value];
    await api("POST","/characters",{
      nombre: $("pj-nombre").value.trim() || "Aventurero",
      raza: $("pj-raza").value,
      subraza: $("lbl-subraza").hidden ? null : $("pj-subraza").value,
      bonos_eleccion: razaSel.eleccion
        ? [$("pj-eleccion-1").value, $("pj-eleccion-2").value] : [],
      metodo: modoAtributos,
      alineamiento: $("pj-alineamiento").value,
      estilo_combate: $("pj-clase").value === "guerrero" ? $("pj-estilo").value : null,
      clase: $("pj-clase").value, atributos,
      habilidades: chipsElegidos("pj-habilidades"),
      armadura: $("pj-armadura").value || null,
      escudo: $("pj-escudo").checked,
      arma_equipada: $("pj-arma").value,
      conocidos: conjuros, preparados: conjuros,
    });
    await entrarALaMesa();
  } catch(e){ mostrarError("pj-error", e.message); }
};

// ---------------------------------------------------------------- mesa

async function entrarALaMesa() {
  mostrar("mesa");
  $("ui-invite").textContent = "invitación: " + S.inviteCode;
  pintarNarrador();
  await refrescarTodo(true);
  programarPolling();
}

async function pintarNarrador() {
  try {
    const r = await fetch("/api/health"); const h = await r.json();
    const el = $("ui-dm");
    if (h.narrador === "dummy") {
      el.textContent = "DM dummy (falta API key)";
      el.classList.add("dummy");
    } else {
      el.textContent = "DM: " + (h.modelo || "").split("/").pop();
      el.classList.remove("dummy");
    }
  } catch {}
}

$("ui-dm").style.cursor = "pointer";
$("ui-dm").title = "Click: probar el narrador (llamada real de test)";
$("ui-dm").onclick = async () => {
  const el = $("ui-dm");
  const antes = el.textContent;
  el.textContent = "probando…";
  try {
    const r = await fetch("/api/health/narrator");
    const d = await r.json();
    if (d.ok) alert(`✅ Narrador OK\nModelos: ${d.modelos.join(", ")}\nRespuesta: ${d.respuesta}`);
    else alert(`❌ Narrador con problemas\n\n${d.detalle}\n\nDetalle técnico: ${d.crudo ?? "-"}`);
  } catch(e) { alert("No se pudo probar: " + e.message); }
  el.textContent = antes;
  pintarNarrador();
};

$("btn-salir").onclick = () => {
  if (!confirm("¿Volver al menú principal?\n\nTu llave 🔑 te permite retomar "
             + "esta campaña cuando quieras. ¿La tenés guardada?")) return;
  if (S.timerId) clearTimeout(S.timerId);
  localStorage.clear();
  location.reload();
};

$("btn-llave").onclick = async () => {
  try { await navigator.clipboard.writeText(S.token); alert("Llave copiada. Guardala para retomar la campaña."); }
  catch { alert("Tu llave:\n\n" + S.token); }
};

function programarPolling() {
  if (S.timerId) clearTimeout(S.timerId);
  const tick = async () => {
    try { await refrescarTodo(false); marcarConexion(true); }
    catch { marcarConexion(false); }
    const rapido = S.narrando || Date.now() < S.rapidoHasta ||
                   (S.campania && S.campania.estado === "combate");
    S.timerId = setTimeout(tick, rapido ? 1300 : 5000);
  };
  S.timerId = setTimeout(tick, 1000);
}

let contadorMundo = 0;
async function refrescarTodo(inicial) {
  const camp = await api("GET", `/campaigns/${S.campaignId}`);
  S.campania = camp;
  S.narrando = !!camp.narrando;

  const mio = camp.personajes.filter(p => p.player_id === S.playerId).at(-1);
  if (mio && !mio.vivo) {
    // muerte: ofrecer nuevo personaje
    if (confirmarMuerte(mio)) return;
  }
  if (mio && mio.vivo) {
    S.characterId = mio.id;
    S.ficha = await api("GET", `/characters/${mio.id}/sheet`);
    pintarFicha(S.ficha);
  }

  pintarCabecera(camp);
  pintarCombate(camp);
  pintarEscribiendo();
  await pintarMensajes();
  if (inicial || ++contadorMundo % 4 === 0)
    pintarMundo(await api("GET", `/campaigns/${S.campaignId}/state`));
}

let muerteAvisada = false;
function confirmarMuerte(mio) {
  if (muerteAvisada) return false;
  muerteAvisada = true;
  setTimeout(() => {
    if (confirm(`${mio.nombre} ha muerto. ¿Forjar un nuevo personaje para seguir jugando?`)) {
      document.querySelectorAll("#pj-atributos input").forEach(i=>{i.value=10;});
      $("pj-nombre").value = "";
      prepararCreacionPJ(); mostrar("personaje");
      muerteAvisada = false;
    }
  }, 400);
  return false;
}

function pintarCabecera(c) {
  $("ui-camp-nombre").textContent = c.nombre;
  $("ui-ubicacion").textContent = c.ubicacion ? "— " + c.ubicacion : "";
  const est = $("ui-estado");
  est.textContent = c.estado;
  est.classList.toggle("en-combate", c.estado === "combate");
}

// ---------- log

async function pintarMensajes() {
  const nuevos = await api("GET",
    `/campaigns/${S.campaignId}/messages?since=${S.ultimoMsg}`);
  if (!nuevos.length) return;
  const log = $("ui-log");
  const abajo = log.scrollHeight - log.scrollTop - log.clientHeight < 90;
  for (const m of nuevos) {
    S.ultimoMsg = Math.max(S.ultimoMsg, m.id);
    const div = document.createElement("div");
    div.className = "msg msg-" + m.autor;
    div.innerHTML = m.autor === "sistema"
      ? `<span class="msg-texto">${esc(m.contenido)}</span>`
      : `<span class="msg-autor">${esc(m.autor_nombre)}</span>
         <span class="msg-texto">${esc(m.contenido)}</span>`;
    log.insertBefore(div, $("dm-typing"));
  }
  if (abajo) log.scrollTop = log.scrollHeight;
}

function pintarEscribiendo() {
  let t = $("dm-typing");
  if (!t) {
    t = document.createElement("div");
    t.id = "dm-typing"; t.className = "dm-escribiendo";
    t.textContent = "El DM narra";
    $("ui-log").appendChild(t);
  }
  t.hidden = !S.narrando;
  if (S.narrando) $("ui-log").scrollTop = $("ui-log").scrollHeight;
}

const esc = (t)=>{const d=document.createElement("div");d.textContent=t??"";return d.innerHTML;};
const signo = (n)=>(n>=0?"+":"")+n;

function sellarResolucion(r) {
  if (!r) return;
  const div = document.createElement("div");
  div.className = "msg";
  div.innerHTML = selloHTML(r);
  if (!div.innerHTML) return;
  $("ui-log").insertBefore(div, $("dm-typing"));
  $("ui-log").scrollTop = $("ui-log").scrollHeight;
}

function selloHTML(r) {
  if (r.tipo === "ataque" || r.tipo === "ataque_magico") {
    const ok = r.impacta, cls = r.critico ? "critico" : ok ? "exito" : "fallo";
    let s = `<span class="sello ${cls}">🎲 d20 ${r.natural}${signo(r.bono_ataque ?? r.bono)}=`
          + `<b>${r.total}</b> vs CA ${r.ca_objetivo} → <b>${ok?(r.critico?"¡CRÍTICO!":"IMPACTA"):"FALLA"}</b></span>`;
    if (r.danio) s += ` <span class="sello">⚔ <b>${r.danio.total_final}</b> daño</span>`;
    return s;
  }
  if (r.tipo === "habilidad") {
    const cls = r.critico ? "critico" : r.exito ? "exito" : "fallo";
    return `<span class="sello ${cls}">🎲 ${esc(r.habilidad)} d20 ${r.natural}${signo(r.bono)}=`
         + `<b>${r.total}</b> vs CD ${r.cd} → <b>${r.exito?"ÉXITO":esc(r.grado).replaceAll("_"," ").toUpperCase()}</b></span>`;
  }
  if (r.tipo === "curacion")
    return `<span class="sello exito">✦ curación <b>+${r.curado ?? r.total_final}</b> PG</span>`;
  if (r.tipo === "danio_auto")
    return `<span class="sello exito">✦ <b>${r.total_final}</b> daño automático</span>`;
  if (r.tipo === "danio_conjuro")
    return `<span class="sello">✦ daño <b>${r.final}</b></span>`;
  if (r.tipo === "salvacion")
    return `<span class="sello ${r.exito?"fallo":"exito"}">🛡 salvación enemiga <b>${r.total}</b> vs CD ${r.cd} → <b>${r.exito?"RESISTE":"FALLA"}</b></span>`;
  if (r.tipo === "condicion_aplicada")
    return `<span class="sello exito">✦ condición aplicada (${esc(r.conjuro)})</span>`;
  if (r.tipo === "efecto_auto")
    return `<span class="sello">✦ ${esc(r.efecto)}</span>`;
  return "";
}

function avisoSistema(txt) {
  const d = document.createElement("div");
  d.className = "msg msg-sistema"; d.textContent = "⚠ " + txt;
  $("ui-log").insertBefore(d, $("dm-typing"));
  $("ui-log").scrollTop = $("ui-log").scrollHeight;
}

// ---------- combate

function pintarCombate(c) {
  const barra = $("ui-combate-barra");
  const enCombate = c.estado === "combate" && c.combate;
  barra.hidden = !enCombate;
  $("composer-exploracion").hidden = enCombate;
  $("composer-combate").hidden = !enCombate;
  if (!enCombate) return;

  const orden = c.combate.orden, idx = c.combate.turno_idx;
  const segRestantes = c.combate.turno_ts
    ? Math.max(0, TIMEOUT_TURNO - Math.floor(Date.now()/1000 - c.combate.turno_ts)) : null;

  barra.innerHTML = `<b>Ronda ${c.combate.ronda}</b> · ` + orden.map((e,i)=>{
    const esNpc = e.tipo === "npc";
    const npc = esNpc && c.npcs_en_escena.find(n=>"npc_"+n.id===e.id);
    const nombre = esNpc ? (npc?npc.nombre:e.id)
      : (c.personajes.find(p=>"pj_"+p.id===e.id)?.nombre ?? e.id);
    const salud = npc && npc.salud ? ` · ${npc.salud}` : "";
    return `<span class="turno-item ${esNpc?"enemigo":""} ${i===idx?"actual":""}">${esc(nombre)}${salud}</span>`;
  }).join("") + (segRestantes !== null && orden[idx]?.tipo==="pj"
    ? ` <span class="contador-turno">⏱ ${segRestantes}s</span>` : "");

  const sel = $("inp-objetivo");
  const vivos = c.npcs_en_escena.filter(n=>n.vivo && n.actitud==="hostil");
  const actual = sel.value;
  sel.innerHTML = "";
  for (const n of vivos)
    sel.add(new Option(`${n.nombre}${n.salud?" ("+n.salud+")":""}`, n.id));
  if ([...sel.options].some(o=>o.value===actual)) sel.value = actual;

  const conConjuros = S.ficha && (S.ficha.preparados.length || S.ficha.conocidos.length);
  $("fila-conjuro").hidden = !conConjuros;
  if (conConjuros) {
    const sc = $("inp-conjuro");
    const lista = S.ficha.preparados.length ? S.ficha.preparados : S.ficha.conocidos;
    const antes = sc.value; sc.innerHTML = "";
    for (const cj of lista) sc.add(new Option(cj.replaceAll("_"," "), cj));
    if ([...sc.options].some(o=>o.value===antes)) sc.value = antes;
  }

  const miTurno = orden[idx]?.id === "pj_" + S.characterId;
  for (const id of ["btn-atacar","btn-cast","btn-dodge","btn-help","btn-shove","btn-flee"])
    $(id).disabled = !miTurno;
  $("ui-turno-info").textContent = miTurno
    ? "Es tu turno. Elegí objetivo y actuá."
    : "Esperando el turno de los demás…";
}

$("btn-atacar").onclick = () => accionCombate("attack",
  { objetivo_npc_id: +$("inp-objetivo").value });
$("btn-dodge").onclick = () => accionCombate("dodge", {});
$("btn-shove").onclick = () => accionCombate("shove",
  { objetivo_npc_id: +$("inp-objetivo").value });
$("btn-flee").onclick = () => {
  if (confirm("¿Intentar huir? (Acrobacias CD 12; si fallás te castigan)"))
    accionCombate("flee", {});
};
$("btn-help").onclick = () => {
  const aliados = S.campania.personajes.filter(p =>
    p.vivo && p.pg_actual > 0 && p.id !== S.characterId);
  if (!aliados.length) return avisoSistema("No hay aliados para ayudar");
  const nombres = aliados.map((a,i)=>`${i+1}. ${a.nombre}`).join("\n");
  const n = prompt("¿A quién ayudás? (número)\n" + nombres);
  const el = aliados[+n - 1];
  if (el) accionCombate("help", { aliado_character_id: el.id });
};
$("btn-cast").onclick = () => accionCombate("cast", {
  conjuro: $("inp-conjuro").value,
  objetivo_npc_id: +$("inp-objetivo").value || null });

async function accionCombate(tipo, body) {
  const btns = ["btn-atacar","btn-cast","btn-dodge","btn-help","btn-shove","btn-flee"].map($);
  btns.forEach(b=>b.disabled=true);
  try {
    const d = await api("POST", `/campaigns/${S.campaignId}/combat/${tipo}`, body);
    for (const r of (d.resoluciones ?? [d.resolucion])) sellarResolucion(r);
    for (const ev of d.turnos_npc ?? []) {
      if (ev.ataque) sellarResolucion(ev.ataque);
      if (ev.concentracion) sellarResolucion({...ev.concentracion, tipo:"habilidad", habilidad:"concentración"});
      if (ev.salvacion_muerte) avisoSistema(`salvación de muerte de ${ev.actor}: d20 ${ev.salvacion_muerte.natural}`);
    }
    acelerarPolling();
    await refrescarTodo(false);
  } catch(e) {
    avisoSistema(e.message);
    btns.forEach(b=>b.disabled=false);
  }
}

// ---------- exploración

$("btn-say").onclick = () => enviarAccion(false);
$("btn-party").onclick = () => enviarAccion(true);
$("inp-accion").addEventListener("keydown",(e)=>{
  if (e.key==="Enter" && !e.shiftKey){ e.preventDefault(); enviarAccion(false); }
});

async function enviarAccion(entreJugadores) {
  const texto = $("inp-accion").value.trim();
  if (!texto) return;
  $("inp-accion").value = "";
  try {
    await api("POST", `/campaigns/${S.campaignId}/say`,
              { texto, entre_jugadores: entreJugadores });
    if (!entreJugadores) { S.narrando = true; pintarEscribiendo(); }
    acelerarPolling(8);
    await pintarMensajes();
  } catch(e){ avisoSistema(e.message); }
}

$("btn-skill").onclick = async () => {
  $("btn-skill").disabled = true;
  try {
    const d = await api("POST", `/campaigns/${S.campaignId}/skill-check`, {
      habilidad: $("inp-habilidad").value,
      descripcion: $("inp-desc-habilidad").value.trim()});
    sellarResolucion(d.resolucion);
    $("inp-desc-habilidad").value = "";
    S.narrando = true; pintarEscribiendo(); acelerarPolling();
  } catch(e){ avisoSistema(e.message); }
  $("btn-skill").disabled = false;
};

// ---------- ficha

function pintarFicha(f) {
  const pgPct = Math.round(100 * f.pg_actual / f.pg_max);
  const slotsHTML = Object.entries(f.slots).map(([nv,s])=>{
    const puntos = Array.from({length:s.max},(_,i)=>
      `<span class="punto-slot ${i < s.max - s.usados ? "lleno" : ""}"></span>`).join("");
    return `<div class="slots-fila">Nv${nv} ${puntos}</div>`;
  }).join("");
  const conds = f.condiciones.map(c=>`<span class="condicion-tag">${esc(c.tipo)}</span>`).join("");
  const puedeSubir = f.nivel_por_xp > f.nivel;
  const enCombate = S.campania?.estado === "combate";

  const inventarioHTML = (f.inventario||[]).map(it => {
    const usable = CONSUMIBLES_USABLES.has(it.nombre);
    const equipable = ARMAS.includes(it.nombre) && it.nombre !== f.arma_equipada;
    return `<div class="item-linea">
      <span>${esc(it.nombre.replaceAll("_"," "))} ×${it.cantidad}</span>
      <span>
        ${usable ? `<button class="btn" data-usar="${esc(it.nombre)}">Usar</button>` : ""}
        ${equipable && !enCombate ? `<button class="btn" data-equipar="${esc(it.nombre)}">Equipar</button>` : ""}
      </span></div>`;
  }).join("");

  $("ui-ficha").innerHTML = `
    <h2>${esc(f.nombre)}</h2>
    <p class="clase-linea">${esc(f.raza)} ${esc(f.clase)}${f.subclase ? " ("+esc(f.subclase.replaceAll("_"," "))+")" : ""} · nivel ${f.nivel} · ${f.xp} XP</p>
    ${puedeSubir ? `<button class="btn btn-nivel" id="btn-subir-nivel">⭐ Subir a nivel ${f.nivel_por_xp}</button>` : ""}
    <div class="barra-pg"><div style="width:${pgPct}%"></div></div>
    <span class="pg-texto">${f.pg_actual} / ${f.pg_max} PG</span>
    ${conds ? "<div>"+conds+"</div>" : ""}
    <div class="stat-grid">
      ${ATRS.map(a=>`<div class="stat"><span class="n">${a}</span>
        <span class="v">${f.atributos[a].valor}</span>
        <span class="m">${signo(f.atributos[a].mod)}</span></div>`).join("")}
    </div>
    <div class="linea-dato"><span>CA</span><span>${f.ca}</span></div>
    <div class="linea-dato"><span>Iniciativa</span><span>${signo(f.iniciativa_mod)}</span></div>
    <div class="linea-dato"><span>Dados de golpe</span><span>${f.dados_golpe_disp}${f.dado_golpe}</span></div>
    <div class="linea-dato"><span>Arma</span><span>${esc(f.arma_equipada ?? "—")}</span></div>
    <div class="linea-dato"><span>Armadura</span><span>${esc(f.armadura ?? "—")}${f.escudo?" + escudo":""}</span></div>
    <div class="linea-dato"><span>Monedas</span><span>${f.monedas?.mo ?? 0} mo</span></div>
    ${slotsHTML ? "<h3 style='margin:.8rem 0 .2rem'>Espacios de conjuro</h3>"+slotsHTML : ""}
    ${f.concentracion ? `<div class="linea-dato"><span>Concentración</span><span>${esc(f.concentracion.hechizo)}</span></div>` : ""}
    ${Object.keys(f.recursos_clase||{}).length ?
      "<h3 style='margin:.8rem 0 .2rem'>Rasgos de clase</h3>" +
      Object.entries(f.recursos_clase).map(([n,rec])=>{
        const ui = HABILIDADES_CLASE_UI[n];
        const estado = "pool" in rec ? `${rec.pool}/${rec.pool_max}`
                     : `${rec.max - rec.usados}/${rec.max}`;
        const agotado = "pool" in rec ? rec.pool <= 0 : rec.usados >= rec.max;
        const boton = ui ? `<button class="btn" data-clase-hab="${n}"
          ${agotado ? "disabled" : ""}>${ui.icono} Usar</button>` : "";
        return `<div class="recurso-linea">
          <span>${ui ? ui.label : esc(n.replaceAll("_"," "))}
          <span class="party-pg">${estado}</span></span>${boton}</div>`;
      }).join("") : ""}
    <div class="ficha-acciones">
      ${(f.preparados.length || f.conocidos.length || Object.keys(f.slots).length) ?
        `<button class="btn" id="btn-gestionar-conjuros" ${enCombate?"disabled":""}>📜 Conjuros</button>` : ""}
      <button class="btn" id="btn-rest-short" ${enCombate||!f.dados_golpe_disp?"disabled":""}>🔥 Descanso corto (1 dado)</button>
      <button class="btn" id="btn-rest-long" ${enCombate?"disabled":""}>🌙 Descanso largo</button>
    </div>
    <h3 style='margin:.6rem 0 .2rem'>Mochila</h3>
    ${inventarioHTML || '<p class="nota">Vacía.</p>'}
  `;

  $("btn-rest-short")?.addEventListener("click", async ()=>{
    try {
      const r = await api("POST", `/campaigns/${S.campaignId}/rest/short`, {dados:1});
      avisoSistema(`Descanso corto: +${r.curado} PG`); acelerarPolling();
      await refrescarTodo(false);
    } catch(e){ avisoSistema(e.message); }
  });
  $("btn-rest-long")?.addEventListener("click", async ()=>{
    if (!confirm("¿Descanso largo de 8 horas para todo el grupo?")) return;
    try {
      await api("POST", `/campaigns/${S.campaignId}/rest/long`);
      acelerarPolling(); await refrescarTodo(false);
    } catch(e){ avisoSistema(e.message); }
  });
  $("btn-subir-nivel")?.addEventListener("click", async ()=>{
    const tirar = confirm("¿Tirar el dado de golpe para los PG? (Aceptar = tirar, Cancelar = valor fijo)");
    const body = {metodo: tirar ? "tirar" : "fijo"};
    const nvSub = CATALOGO?.nivel_subclase?.[f.clase];
    if (nvSub === f.nivel + 1 && !f.subclase) {
      const ops = (CATALOGO?.subclases?.[f.clase] || []).join(", ");
      const s = prompt(`Nivel ${f.nivel + 1}: elegí tu subclase.\n` +
                       `Del SRD: ${ops}\n(o escribí la tuya)`);
      if (!s) return;
      body.subclase = s.trim().toLowerCase().replaceAll(" ", "_");
    }
    if ([4, 8].includes(f.nivel + 1)) {
      const rep = prompt("Mejora de atributos: +2 puntos a repartir.\n" +
        'Formato: "FUE" (para +2) o "DES,CON" (+1 y +1)');
      if (!rep) return;
      const partes = rep.toUpperCase().split(",").map(s=>s.trim()).filter(Boolean);
      body.asi = partes.length === 1 ? {[partes[0]]: 2}
               : {[partes[0]]: 1, [partes[1]]: 1};
    }
    try {
      const r = await api("POST", `/campaigns/${S.campaignId}/level-up`, body);
      avisoSistema(`¡Nivel ${r.nivel}! +${r.pg_ganados} PG máx.`);
      await refrescarTodo(false);
    } catch(e){ avisoSistema(e.message); }
  });
  $("btn-gestionar-conjuros")?.addEventListener("click", ()=>abrirPanelConjuros(f));
  document.querySelectorAll("[data-clase-hab]").forEach(b=>b.onclick = async ()=>{
    const nombre = b.dataset.claseHab;
    const ui = HABILIDADES_CLASE_UI[nombre] || {};
    const body = { nombre };
    if (ui.aliado) {
      const candidatos = S.campania.personajes.filter(p =>
        p.vivo && (ui.requiere_aliado ? p.id !== S.characterId : true));
      const lista = candidatos.map((a,i)=>`${i+1}. ${a.nombre} (${a.pg_actual}/${a.pg_max})`).join("\n");
      const n = prompt(`¿Objetivo de ${ui.label}? (número)\n` + lista);
      const el = candidatos[+n - 1];
      if (!el) return;
      body.objetivo_character_id = el.id;
    }
    if (ui.cantidad) {
      const c = prompt("¿Cuántos PG curás del pool?");
      if (!c || +c <= 0) return;
      body.cantidad = +c;
    }
    try {
      const r = await api("POST", `/campaigns/${S.campaignId}/class-ability`, body);
      if (r.curado !== undefined) sellarResolucion({tipo:"curacion", curado:r.curado});
      acelerarPolling(); await refrescarTodo(false);
    } catch(e){ avisoSistema(e.message); }
  });
  document.querySelectorAll("[data-usar]").forEach(b=>b.onclick = async ()=>{
    try {
      const r = await api("POST", `/campaigns/${S.campaignId}/inventory/use`,
                          {nombre: b.dataset.usar});
      if (r.curado !== undefined) sellarResolucion({tipo:"curacion", curado:r.curado});
      acelerarPolling(); await refrescarTodo(false);
    } catch(e){ avisoSistema(e.message); }
  });
  document.querySelectorAll("[data-equipar]").forEach(b=>b.onclick = async ()=>{
    try {
      await api("POST", `/campaigns/${S.campaignId}/inventory/equip`,
                {arma: b.dataset.equipar});
      await refrescarTodo(false);
    } catch(e){ avisoSistema(e.message); }
  });
}

// ---------- gestión de conjuros

async function abrirPanelConjuros(f) {
  await cargarCatalogo();
  if (!CONJUROS_SERVER) return avisoSistema("No pude cargar el catálogo");
  const actuales = new Set(f.preparados.length ? f.preparados : f.conocidos);
  const overlay = document.createElement("div");
  overlay.className = "panel-conjuros";
  overlay.innerHTML = `<div class="caja">
    <h2>Conjuros de ${esc(f.nombre)}</h2>
    <p class="nota" id="pc-limite">…</p>
    <input id="pc-filtro" placeholder="Filtrar…" style="margin:.4rem 0">
    <div class="chips" id="pc-chips"></div>
    <div class="ficha-acciones">
      <button class="btn btn-ambar" id="pc-guardar">Guardar</button>
      <button class="btn" id="pc-cerrar">Cancelar</button>
    </div></div>`;
  document.body.appendChild(overlay);

  const chips = overlay.querySelector("#pc-chips");
  const entradas = Object.entries(CONJUROS_SERVER)
    .sort((a,b)=>a[1].nivel-b[1].nivel || a[0].localeCompare(b[0]));
  for (const [k, v] of entradas) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip chip-arcano" + (actuales.has(k) ? " activo" : "");
    b.dataset.valor = k;
    b.innerHTML = `${esc(k.replaceAll("_"," "))}<span class="nv">nv${v.nivel}</span>`;
    b.onclick = () => { b.classList.toggle("activo"); actualizarContador(); };
    chips.appendChild(b);
  }
  const actualizarContador = () => {
    const sel = [...chips.querySelectorAll(".activo")].map(c=>c.dataset.valor);
    const conNivel = sel.filter(k=>CONJUROS_SERVER[k].nivel > 0).length;
    const trucos = sel.length - conNivel;
    overlay.querySelector("#pc-limite").textContent =
      `Seleccionados: ${conNivel} con nivel + ${trucos} trucos. ` +
      `El servidor valida tu límite de clase y el nivel máximo lanzable.`;
  };
  actualizarContador();
  overlay.querySelector("#pc-filtro").oninput = (e) => {
    const q = e.target.value.toLowerCase();
    chips.querySelectorAll(".chip").forEach(c =>
      c.style.display = c.dataset.valor.includes(q) ||
                        c.classList.contains("activo") ? "" : "none");
  };
  overlay.querySelector("#pc-cerrar").onclick = () => overlay.remove();
  overlay.querySelector("#pc-guardar").onclick = async () => {
    const lista = [...chips.querySelectorAll(".activo")].map(c=>c.dataset.valor);
    try {
      const r = await api("POST", `/campaigns/${S.campaignId}/spells/manage`,
                          { lista });
      avisoSistema(`Conjuros guardados (${r.lista.length}, máx nivel ${r.nivel_max}).`);
      overlay.remove();
      await refrescarTodo(false);
    } catch(e) { avisoSistema(e.message); }
  };
}

// ---------- mundo

function pintarMundo(st) {
  const quests = st.quests.filter(q=>q.estado==="activa");
  const hechas = st.quests.filter(q=>q.estado!=="activa");
  const party = (S.campania?.personajes || []).map(p => {
    const conds = p.condiciones?.length ? " · " + p.condiciones.join(", ") : "";
    return `<div class="party-linea">
      <span><b>${esc(p.nombre)}</b>${p.vivo ? "" : " 💀"}
        <div class="party-meta">${esc(p.raza)} ${esc(p.clase)} nv${p.nivel} ·
        ${esc((p.alineamiento||"").replaceAll("_"," "))}${conds}</div></span>
      <span class="party-pg">${p.pg_actual}/${p.pg_max} PG</span>
    </div>`;
  }).join("");
  $("ui-mundo").innerHTML = `
    <h3>La party</h3>${party || '<p class="nota">Nadie en la mesa.</p>'}` + `
    <h3>Misiones</h3>
    ${quests.length ? "<ul>"+quests.map(q=>
      `<li class="${q.principal?"q-principal":""}"><b>${esc(q.titulo)}</b>
       ${q.descripcion?"— "+esc(q.descripcion):""}</li>`).join("")+"</ul>"
      : '<p class="nota">Ninguna todavía. Salí a buscar problemas.</p>'}
    ${hechas.length ? `<p class="nota">${hechas.length} completada(s)/fallida(s)</p>` : ""}
    <h3>Personajes conocidos</h3>
    ${st.npcs_conocidos.length ? "<ul>"+st.npcs_conocidos.map(n=>
      `<li><b>${esc(n.nombre)}</b> ${n.rol?"· "+esc(n.rol):""}
       <span class="actitud">${esc(n.actitud)}${n.en_escena?" · presente":""}</span></li>`).join("")+"</ul>"
      : '<p class="nota">Nadie con nombre, aún.</p>'}
    ${st.consecuencias_pendientes ? `<h3>Presagios</h3>
      <p class="nota">Hay ${st.consecuencias_pendientes} consecuencia(s) pendiente(s) sobre el grupo…</p>` : ""}
    ${st.resumen ? `<h3>Crónica</h3><div class="resumen-caja">${esc(st.resumen)}</div>` : ""}
  `;
}

// ---------- tabs móvil

document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("activo",x===t));
  document.querySelectorAll("[data-panel]").forEach(p=>
    p.classList.toggle("visible", p.dataset.panel===t.dataset.tab));
});
document.querySelector('[data-panel="juego"]')?.classList.add("visible");

for (const h of HABILIDADES) $("inp-habilidad").add(new Option(h.replaceAll("_"," "), h));

// ---------------------------------------------------------------- arranque

(async function init() {
  if (!S.token) { mostrar("inicio"); return; }
  try {
    const me = await api("GET","/campaigns/me");
    guardarSesion({campaign_id: me.campaign_id, player_id: me.player_id,
                   invite_code: me.invite_code});
    if (me.character_id) await entrarALaMesa();
    else { prepararCreacionPJ(); mostrar("personaje"); }
  } catch(e) {
    if (e.status === 401) { localStorage.clear(); mostrar("inicio"); }
    else {
      mostrar("inicio");
      mostrarError("inicio-error","Despertando el servidor… reintentá en unos segundos.");
    }
  }
})();
