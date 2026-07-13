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
  "arco_corto","arco_largo","ballesta_de_mano","lanza","mazo","mandoble","hacha_grande",
  "baston","cimitarra","garrote"];

const ARMADURAS = ["cuero","cuero_tachonado","camisa_de_mallas","coraza",
  "media_armadura","ring_mail","cota_de_mallas","armadura_de_placas"];


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
  aliento_de_dragon: {icono:"🐉", label:"Aliento de dragón", combate:true, enemigo:true},
};

const CONSUMIBLES_USABLES = new Set(["pocion_de_curacion","pocion_de_curacion_mayor"]);
const ATRS = ["FUE","DES","CON","INT","SAB","CAR"];
const TIMEOUT_TURNO = 120;

// Fallback local (el servidor es la fuente de verdad vía /api/content; esto
// asegura que la UI funcione aunque el catálogo aún no haya cargado).
const TRASFONDOS_LOCAL = {
  acolito:{nombre:"Acólito",competencias:["perspicacia","religion"],oro:15,rasgo:"Refugio de los Fieles"},
  charlatan:{nombre:"Charlatán",competencias:["engano","juego_de_manos"],oro:15,rasgo:"Identidad Falsa"},
  criminal:{nombre:"Criminal",competencias:["engano","sigilo"],oro:15,rasgo:"Contacto Criminal"},
  artista:{nombre:"Artista",competencias:["acrobacias","actuacion"],oro:15,rasgo:"Por Demanda Popular"},
  heroe_del_pueblo:{nombre:"Héroe del Pueblo",competencias:["trato_con_animales","supervivencia"],oro:10,rasgo:"Hospitalidad Rústica"},
  gremio_artesano:{nombre:"Artesano de Gremio",competencias:["perspicacia","persuasion"],oro:15,rasgo:"Membresía de Gremio"},
  ermitano:{nombre:"Ermitaño",competencias:["medicina","religion"],oro:5,rasgo:"Descubrimiento"},
  noble:{nombre:"Noble",competencias:["historia","persuasion"],oro:25,rasgo:"Posición de Privilegio"},
  forastero:{nombre:"Forastero",competencias:["atletismo","supervivencia"],oro:10,rasgo:"Errante"},
  sabio:{nombre:"Sabio",competencias:["arcanos","historia"],oro:10,rasgo:"Investigador"},
  marinero:{nombre:"Marinero",competencias:["atletismo","percepcion"],oro:10,rasgo:"Pasaje de Barco"},
  soldado:{nombre:"Soldado",competencias:["atletismo","intimidacion"],oro:10,rasgo:"Rango Militar"},
  huerfano:{nombre:"Pilluelo",competencias:["juego_de_manos","sigilo"],oro:10,rasgo:"Secretos de la Ciudad"},
};
const HAB_CLASE_LOCAL = {
  barbaro:{lista:["trato_con_animales","atletismo","intimidacion","naturaleza","percepcion","supervivencia"],cantidad:2},
  bardo:{lista:HABILIDADES,cantidad:3},
  clerigo:{lista:["historia","perspicacia","medicina","persuasion","religion"],cantidad:2},
  druida:{lista:["arcanos","trato_con_animales","perspicacia","medicina","naturaleza","percepcion","religion","supervivencia"],cantidad:2},
  guerrero:{lista:["acrobacias","trato_con_animales","atletismo","historia","perspicacia","intimidacion","percepcion","supervivencia"],cantidad:2},
  monje:{lista:["acrobacias","atletismo","historia","perspicacia","religion","sigilo"],cantidad:2},
  paladin:{lista:["atletismo","perspicacia","intimidacion","medicina","persuasion","religion"],cantidad:2},
  ranger:{lista:["trato_con_animales","atletismo","perspicacia","investigacion","naturaleza","percepcion","sigilo","supervivencia"],cantidad:3},
  picaro:{lista:["acrobacias","atletismo","engano","perspicacia","intimidacion","investigacion","percepcion","actuacion","persuasion","juego_de_manos","sigilo"],cantidad:4},
  hechicero:{lista:["arcanos","engano","perspicacia","intimidacion","persuasion","religion"],cantidad:2},
  mago:{lista:["arcanos","historia","perspicacia","investigacion","medicina","religion"],cantidad:2},
  brujo:{lista:["arcanos","engano","historia","intimidacion","investigacion","naturaleza","religion"],cantidad:2},
};
const GENEROS = ["", "masculino", "femenino", "helicoptero apache"];
const getTrasfondos = () => CATALOGO?.trasfondos || TRASFONDOS_LOCAL;
const getHabClase = (clase) =>
  CATALOGO?.habilidades_clase?.[clase] || HAB_CLASE_LOCAL[clase] || {lista:HABILIDADES,cantidad:2};

// Categorías de armas/armaduras y competencias por clase (fallback local para
// que el filtro de proeficiencia funcione aunque el catálogo aún no cargue).
const ARMAS_CAT_LOCAL = {daga:"simple",espada_corta:"marcial",espada_larga:"marcial",
  hacha_de_mano:"simple",hacha_de_batalla:"marcial",arco_corto:"simple",
  arco_largo:"marcial",ballesta_de_mano:"marcial",lanza:"simple",mazo:"simple",
  mandoble:"marcial",hacha_grande:"marcial",baston:"simple",cimitarra:"marcial",
  garrote:"simple"};
const ARMADURAS_CAT_LOCAL = {cuero:"ligera",cuero_tachonado:"ligera",
  camisa_de_mallas:"media",coraza:"media",media_armadura:"media",ring_mail:"pesada",
  cota_de_mallas:"pesada",armadura_de_placas:"pesada"};
const COMP_CLASE_LOCAL = {
  barbaro:{armas:["simple","marcial"],armaduras:["ligera","media","escudo"]},
  guerrero:{armas:["simple","marcial"],armaduras:["ligera","media","pesada","escudo"]},
  paladin:{armas:["simple","marcial"],armaduras:["ligera","media","pesada","escudo"]},
  ranger:{armas:["simple","marcial"],armaduras:["ligera","media","escudo"]},
  clerigo:{armas:["simple"],armaduras:["ligera","media","escudo"]},
  druida:{armas:["simple"],armaduras:["ligera","media","escudo"]},
  bardo:{armas:["simple"],armaduras:["ligera"]},
  monje:{armas:["simple"],armaduras:[]},
  picaro:{armas:["simple"],armaduras:["ligera"]},
  hechicero:{armas:["simple"],armaduras:[]},
  mago:{armas:["simple"],armaduras:[]},
  brujo:{armas:["simple"],armaduras:["ligera"]},
};
const getArmaCat  = (a) => CATALOGO?.armas_info?.[a]?.categoria || ARMAS_CAT_LOCAL[a];
const getArmadCat = (a) => CATALOGO?.armaduras_info?.[a]?.categoria || ARMADURAS_CAT_LOCAL[a];
const getCompClase = (c) =>
  CATALOGO?.competencias_clase?.[c] || COMP_CLASE_LOCAL[c] || {armas:[],armaduras:[]};

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
  const primeraVez = !sel.options.length;

  // Trasfondo y género NO dependen de la clase: se poblan siempre que estén
  // vacíos, incluso al re-entrar a la pantalla (así nunca quedan vacíos).
  const st = $("pj-trasfondo");
  if (!st.options.length) {
    st.add(new Option("(sin trasfondo)", ""));
    for (const [k, t] of Object.entries(getTrasfondos()))
      st.add(new Option(t.nombre, k));
    st.onchange = () => {
      const t = getTrasfondos()[st.value];
      $("pj-trasfondo-info").textContent = t
        ? `Competencias: ${t.competencias.map(c => c.replaceAll("_", " ")).join(", ")}`
          + ` · ${t.oro} mo · ${t.rasgo}`
        : "";
      montarHabilidades();   // el trasfondo fuerza sus habilidades
    };
  }
  const sg = $("pj-genero");
  if (!sg.options.length)
    for (const g of GENEROS) sg.add(new Option(g || "(sin especificar)", g));

  if (!primeraVez) { actualizarPB(); return; }

  // --- lo que sigue solo hace falta la primera vez ---
  for (const c of Object.keys(CLASES)) sel.add(new Option(c, c));
  sel.onchange = () => {
    $("pj-clase-info").textContent = CLASES[sel.value];
    $("lbl-estilo").hidden = sel.value !== "guerrero";
    $("pj-estilo-info").textContent = sel.value === "guerrero"
      ? ESTILOS[$("pj-estilo").value] : "";
    const nvSub = CATALOGO?.nivel_subclase?.[sel.value];
    $("lbl-subclase-crea").hidden = nvSub !== 1;
    if (nvSub === 1) {
      const ss = $("pj-subclase-crea"); ss.innerHTML = "";
      for (const s of (CATALOGO?.subclases?.[sel.value] || []))
        ss.add(new Option(s.replaceAll("_"," "), s));
    }
    filtrarEquipo();          // solo armas/armaduras que la clase domina
    montarHabilidades();      // solo habilidades de la lista de la clase
    cargarConjurosCreacion(); // solo conjuros que la clase/raza puede aprender
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
    actualizarEleccion();
    actualizarPB();
    cargarConjurosCreacion();   // alto elfo puede un truco de mago
  };
  const actualizarEleccion = () => {
    const r = RAZAS[$("pj-raza").value];
    let n = r.eleccion || 0;
    if (!$("lbl-subraza").hidden && r.subInfo) {
      const sv = r.subInfo[$("pj-subraza").value];
      if (sv && sv.bonos_a_eleccion !== undefined) n = sv.bonos_a_eleccion;
    }
    $("lbl-eleccion").hidden = !n;
    if (n) {
      for (const id of ["pj-eleccion-1","pj-eleccion-2"]) {
        const e = $(id); e.innerHTML = "";
        for (const a of ATRS) if (!(a in r.bonos)) e.add(new Option(a, a));
      }
      $("pj-eleccion-2").selectedIndex = 1;
    }
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
  $("pj-subraza").addEventListener("change", () => {
    infoSubraza(); actualizarEleccion(); actualizarPB();
    cargarConjurosCreacion(); });
  ["pj-eleccion-1","pj-eleccion-2"].forEach(id=>$(id).addEventListener("change", actualizarPB));

  // toggle método
  $("modo-puntos").onclick = () => setModo("puntos");
  $("modo-libre").onclick = () => setModo("libre");
  setModo("puntos");

  montarHabilidades();
  cargarConjurosCreacion();
  filtrarEquipo();
}

// Habilidades: chips de la lista de la clase (elegís la cantidad del PHB) más
// las que fuerza el trasfondo (pre-marcadas y bloqueadas).
function montarHabilidades() {
  const hc = getHabClase($("pj-clase").value);
  const forzadas = new Set(getTrasfondos()[$("pj-trasfondo").value]?.competencias || []);
  const cont = $("pj-habilidades"); cont.innerHTML = "";
  const cap = hc.cantidad;
  const todas = [...new Set([...hc.lista, ...forzadas])];
  for (const it of todas) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.dataset.valor = it;
    b.textContent = it.replaceAll("_", " ");
    if (forzadas.has(it)) {
      b.classList.add("activo", "chip-forzada");
      b.title = "Otorgada por tu trasfondo";
      b.style.opacity = ".85"; b.style.cursor = "default";
    } else {
      b.onclick = () => {
        const elegidas = cont.querySelectorAll(".activo:not(.chip-forzada)").length;
        if (!b.classList.contains("activo") && elegidas >= cap) return;
        b.classList.toggle("activo");
      };
    }
    cont.appendChild(b);
  }
  $("hab-hint").textContent = `(elegí ${cap})`;
  const nombresForz = [...forzadas].map(f => f.replaceAll("_", " "));
  $("hab-forzadas").textContent = nombresForz.length
    ? `Tu trasfondo ya te da: ${nombresForz.join(", ")}.` : "";
}

const habilidadesElegidas = () =>
  [...$("pj-habilidades").querySelectorAll(".activo:not(.chip-forzada)")]
    .map(b => b.dataset.valor);

// Rearma los selects de arma/armadura con SOLO lo que la clase domina (SRD:
// tu clase determina tus competencias; no podés equipar lo que no dominás).
function filtrarEquipo() {
  const comp = getCompClase($("pj-clase").value);

  const sw = $("pj-arma"); const armaPrev = sw.value; sw.innerHTML = "";
  for (const a of ARMAS) {
    const cat = getArmaCat(a);
    if (cat && (comp.armas.includes(cat) || comp.armas.includes(a)))
      sw.add(new Option(a.replaceAll("_", " "), a));
  }
  if (!sw.options.length) sw.add(new Option("(sin arma)", ""));
  if ([...sw.options].some(o => o.value === armaPrev)) sw.value = armaPrev;

  const sa = $("pj-armadura"); const armadPrev = sa.value; sa.innerHTML = "";
  sa.add(new Option("Sin armadura", ""));
  for (const a of ARMADURAS) {
    const cat = getArmadCat(a);
    if (cat && comp.armaduras.includes(cat))
      sa.add(new Option(a.replaceAll("_", " "), a));
  }
  if ([...sa.options].some(o => o.value === armadPrev)) sa.value = armadPrev;

  const esc = $("pj-escudo");
  const puedeEscudo = comp.armaduras.includes("escudo");
  esc.disabled = !puedeEscudo;
  if (!puedeEscudo) esc.checked = false;
  const escLbl = esc.closest("label");
  if (escLbl) escLbl.style.opacity = puedeEscudo ? "" : ".5";
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

const MAX_CONJUROS_CREACION = 4;

// Trucos y conjuros de nivel 1 que la clase (o la raza) puede aprender.
function conjurosDisponibles() {
  const clase = $("pj-clase").value;
  const subraza = $("lbl-subraza").hidden ? null : $("pj-subraza").value;
  const altoElfo = subraza === "alto_elfo" || subraza === "descendiente_alto_elfo";
  const src = CONJUROS_SERVER || {};
  const trucos = [], nivel1 = [];
  for (const [k, v] of Object.entries(src)) {
    if (v.nivel > 1) continue;
    const clases = v.clases || [];
    let ok = clases.includes(clase);
    if (!ok && altoElfo && v.nivel === 0 && clases.includes("mago")) ok = true;
    if (!ok) continue;
    (v.nivel === 0 ? trucos : nivel1).push(k);
  }
  const porNombre = (a, b) =>
    (src[a]?.nombre || a).localeCompare(src[b]?.nombre || b);
  trucos.sort(porNombre); nivel1.sort(porNombre);
  return { trucos, nivel1 };
}

async function cargarConjurosCreacion() {
  if (!CONJUROS_SERVER) {
    try {
      const r = await fetch("/api/content");
      CONJUROS_SERVER = (await r.json()).conjuros;
    } catch {}
  }
  const cont = $("pj-conjuros");
  cont.innerHTML = "";
  const { trucos, nivel1 } = conjurosDisponibles();
  // el bloque de magia solo aparece si la clase/raza tiene algo para aprender
  $("pj-magia").hidden = !(trucos.length || nivel1.length);
  if (trucos.length + nivel1.length === 0) return;

  const totalSel = () => cont.querySelectorAll(".chip.activo").length;
  const filtroTxt = () =>
    ($("filtro-conjuros")?.value || "").toLowerCase();

  const grupo = (titulo, claves) => {
    if (!claves.length) return;
    const h = document.createElement("div");
    h.textContent = titulo;
    h.style.cssText = "font-weight:600;margin:.5rem 0 .2rem;opacity:.75";
    cont.appendChild(h);
    const fila = document.createElement("div");
    fila.className = "chips";
    for (const k of claves) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip chip-arcano"; b.dataset.valor = k;
      b.textContent = CONJUROS_SERVER[k]?.nombre || k.replaceAll("_", " ");
      b.onclick = () => {
        if (!b.classList.contains("activo") && totalSel() >= MAX_CONJUROS_CREACION)
          return;
        b.classList.toggle("activo");
      };
      fila.appendChild(b);
    }
    cont.appendChild(fila);
  };
  grupo(`Trucos (${trucos.length})`, trucos);
  grupo(`Nivel 1 (${nivel1.length})`, nivel1);

  // filtro de texto reutilizable si hay muchos conjuros
  let inp = $("filtro-conjuros");
  if (trucos.length + nivel1.length > 16) {
    if (!inp) {
      inp = document.createElement("input");
      inp.id = "filtro-conjuros"; inp.placeholder = "Filtrar conjuros…";
      inp.style.marginBottom = ".4rem";
      cont.before(inp);
      inp.oninput = () => {
        const q = filtroTxt();
        cont.querySelectorAll(".chip").forEach(c =>
          c.style.display = c.dataset.valor.includes(q) ||
                            c.classList.contains("activo") ? "" : "none");
      };
    }
    inp.hidden = false;
  } else if (inp) {
    inp.hidden = true; inp.value = "";
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
    const conEleccion = !$("lbl-eleccion").hidden;
    await api("POST","/characters",{
      nombre: $("pj-nombre").value.trim() || "Aventurero",
      raza: $("pj-raza").value,
      subraza: $("lbl-subraza").hidden ? null : $("pj-subraza").value,
      bonos_eleccion: conEleccion
        ? [$("pj-eleccion-1").value, $("pj-eleccion-2").value] : [],
      subclase: $("lbl-subclase-crea").hidden ? null : $("pj-subclase-crea").value,
      metodo: modoAtributos,
      genero: $("pj-genero").value || null,
      trasfondo: $("pj-trasfondo").value || null,
      alineamiento: $("pj-alineamiento").value,
      estilo_combate: $("pj-clase").value === "guerrero" ? $("pj-estilo").value : null,
      clase: $("pj-clase").value, atributos,
      habilidades: habilidadesElegidas(),
      armadura: $("pj-armadura").value || null,
      escudo: $("pj-escudo").checked,
      arma_equipada: $("pj-arma").value || null,
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

// ---------- panel de admin (DM humano)
$("btn-admin").onclick = async () => {
  let tok = localStorage.getItem("adminToken");
  if (!tok) {
    tok = prompt("Token de admin (ADMIN_TOKEN del servidor):");
    if (!tok) return;
    localStorage.setItem("adminToken", tok.trim());
  }
  await abrirPanelAdmin();
};

async function apiAdmin(metodo, ruta, body) {
  const r = await fetch(`/api/admin/campaigns/${S.campaignId}${ruta}`, {
    method: metodo,
    headers: {"Content-Type": "application/json",
              "X-Admin-Token": localStorage.getItem("adminToken") || ""},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    if (r.status === 401) localStorage.removeItem("adminToken");
    throw new Error((await r.json()).detail || r.status);
  }
  return r.json();
}

async function abrirPanelAdmin() {
  let d;
  try { d = await apiAdmin("GET", "/full"); }
  catch(e) { return avisoSistema("Admin: " + e.message); }

  const ov = document.createElement("div");
  ov.className = "panel-conjuros";
  const filaPJ = (p) => `<div class="admin-fila" data-pj="${p.id}">
    <b>${esc(p.nombre)}</b>
    PG <input type="number" data-c="pg_actual" value="${p.pg_actual}" style="width:4rem">
    /<input type="number" data-c="pg_max" value="${p.pg_max}" style="width:4rem">
    Oro <input type="number" data-c="oro" value="${p.oro}" style="width:5rem">
    XP <input type="number" data-c="xp" value="${p.xp}" style="width:5rem">
    <button class="btn-mini" data-guardar-pj="${p.id}">💾</button>
    <button class="btn-mini" data-limpiar-cond="${p.id}"
      title="Quitar todas las condiciones">🧹 ${p.condiciones.length}</button>
    <button class="btn-mini" data-item-pj="${p.id}" title="Dar/quitar item">🎒</button>
  </div>`;
  const filaNPC = (n) => `<div class="admin-fila" data-npc="${n.id}">
    <b>${esc(n.nombre)}</b> <span class="party-meta">${esc(n.tipo)} ·
    ${n.vivo ? (n.pg_actual ?? "?") + " PG" : "muerto"}</span>
    <select data-c="actitud">
      ${["amistoso","neutral","hostil"].map(a =>
        `<option ${a===n.actitud?"selected":""}>${a}</option>`).join("")}
    </select>
    <label style="display:inline"><input type="checkbox" data-c="en_escena"
      ${n.en_escena?"checked":""}> en escena</label>
    <button class="btn-mini" data-guardar-npc="${n.id}">💾</button>
    <button class="btn-mini" data-borrar-npc="${n.id}" title="Eliminar NPC">🗑</button>
  </div>`;

  ov.innerHTML = `<div class="caja">
    <h2>⚙ Panel del DM — ${esc(d.campania.nombre)}
      <span class="party-meta">${esc(d.campania.estado)}</span></h2>

    <h3>Hablar como el DM</h3>
    <textarea id="adm-dm-texto" rows="2" style="width:100%"
      placeholder="Este mensaje aparece como narración del DM; la IA construye sobre él."></textarea>
    <button class="btn" id="adm-dm-enviar">Narrar</button>
    ${d.campania.en_combate ? '<button class="btn" id="adm-fin-combate">⚔ Forzar fin del combate</button>' : ""}

    <h3>Personajes</h3>
    ${d.personajes.map(filaPJ).join("")}

    <h3>NPCs</h3>
    ${d.npcs.map(filaNPC).join("") || '<p class="nota">Sin NPCs.</p>'}

    <h3>Misiones</h3>
    ${d.quests.map(q => `<div class="admin-fila"><b>${esc(q.titulo)}</b>
      <select data-quest="${q.id}">
        ${["activa","completada","fallida"].map(e =>
          `<option ${e===q.estado?"selected":""}>${e}</option>`).join("")}
      </select></div>`).join("") || '<p class="nota">Sin misiones.</p>'}

    <h3>Consecuencias pendientes</h3>
    ${d.consecuencias.map(x => `<div class="admin-fila">
      <span>${esc(x.descripcion.slice(0,90))}</span>
      <button class="btn-mini" data-borrar-con="${x.id}">🗑</button>
    </div>`).join("") || '<p class="nota">Ninguna.</p>'}

    <h3>Crónica (resumen que ve la IA)</h3>
    <textarea id="adm-cronica" rows="5" style="width:100%">${esc(d.campania.resumen || "")}</textarea>
    <button class="btn" id="adm-guardar-cronica">💾 Guardar crónica</button>

    <div class="ficha-acciones"><button class="btn" id="adm-cerrar">Cerrar</button></div>
  </div>`;
  document.body.appendChild(ov);

  const refrescar = async () => { ov.remove(); await abrirPanelAdmin(); };
  const seguro = (fn) => async (ev) => {
    try { await fn(ev); } catch(e) { alert("Admin: " + e.message); } };

  ov.querySelector("#adm-cerrar").onclick = () => ov.remove();
  ov.querySelector("#adm-dm-enviar").onclick = seguro(async () => {
    const t = ov.querySelector("#adm-dm-texto").value.trim();
    if (!t) return;
    await apiAdmin("POST", "/say-as-dm", {texto: t});
    ov.remove(); acelerarPolling(); await pintarMensajes();
  });
  ov.querySelector("#adm-fin-combate")?.addEventListener("click", seguro(async () => {
    if (!confirm("¿Terminar el combate por decreto?")) return;
    await apiAdmin("POST", "/end-combat", {}); await refrescar();
  }));
  ov.querySelectorAll("[data-guardar-pj]").forEach(b => b.onclick = seguro(async () => {
    const fila = b.closest(".admin-fila");
    const campos = {};
    fila.querySelectorAll("input[data-c]").forEach(i => campos[i.dataset.c] = +i.value);
    await apiAdmin("POST", `/character/${b.dataset.guardarPj}`, {campos});
    b.textContent = "✓"; setTimeout(()=>b.textContent="💾", 1200);
  }));
  ov.querySelectorAll("[data-limpiar-cond]").forEach(b => b.onclick = seguro(async () => {
    await apiAdmin("POST", `/character/${b.dataset.limpiarCond}`,
                   {campos: {condiciones: []}});
    await refrescar();
  }));
  ov.querySelectorAll("[data-item-pj]").forEach(b => b.onclick = seguro(async () => {
    const pj = d.personajes.find(p => p.id == b.dataset.itemPj);
    const inv = pj.inventario.map((i,x)=>`${x+1}. ${i.nombre} x${i.cantidad}`).join("\n") || "(vacío)";
    const acc = prompt(`Inventario de ${pj.nombre}:\n${inv}\n\n` +
      `Escribí "+ nombre" para agregar o "- número" para quitar:`);
    if (!acc) return;
    let nuevo = [...pj.inventario];
    if (acc.startsWith("+")) nuevo.push({nombre: acc.slice(1).trim(), cantidad: 1});
    else if (acc.startsWith("-")) nuevo.splice(+acc.slice(1).trim() - 1, 1);
    else return;
    await apiAdmin("POST", `/character/${pj.id}`, {campos: {inventario: nuevo}});
    await refrescar();
  }));
  ov.querySelectorAll("[data-guardar-npc]").forEach(b => b.onclick = seguro(async () => {
    const fila = b.closest(".admin-fila");
    const campos = {
      actitud: fila.querySelector("select[data-c]").value,
      en_escena: fila.querySelector("input[type=checkbox]").checked,
    };
    await apiAdmin("POST", `/npc/${b.dataset.guardarNpc}`, {campos});
    b.textContent = "✓"; setTimeout(()=>b.textContent="💾", 1200);
  }));
  ov.querySelectorAll("[data-borrar-npc]").forEach(b => b.onclick = seguro(async () => {
    if (!confirm("¿Eliminar este NPC para siempre?")) return;
    await apiAdmin("DELETE", `/npc/${b.dataset.borrarNpc}`); await refrescar();
  }));
  ov.querySelectorAll("[data-quest]").forEach(s => s.onchange = seguro(async () => {
    await apiAdmin("POST", `/quest/${s.dataset.quest}/${s.value}`, {});
  }));
  ov.querySelectorAll("[data-borrar-con]").forEach(b => b.onclick = seguro(async () => {
    await apiAdmin("DELETE", `/consequence/${b.dataset.borrarCon}`); await refrescar();
  }));
  ov.querySelector("#adm-guardar-cronica").onclick = seguro(async () => {
    await apiAdmin("POST", "/edit",
                   {campos: {resumen_actual: ov.querySelector("#adm-cronica").value}});
    alert("Crónica actualizada: la IA la usa desde la próxima narración.");
  });
}

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
  pintarTiradaPedida(camp);
  pintarEscribiendo();
  // deshacer/regenerar de OTRO jugador: el server tiene menos mensajes que yo
  if (S.campania?.ultimo_mensaje_id !== undefined
      && S.campania.ultimo_mensaje_id < S.ultimoMsg) {
    await pintarMensajes(true);
  }
  const otros = (S.campania?.escribiendo || [])
    .filter(n => n !== S.miNombrePersonaje);
  const elEsc = $("ui-escribiendo");
  if (elEsc) elEsc.textContent = otros.length
    ? (otros.length === 1 ? `${otros[0]} está escribiendo…`
                          : `${otros.join(", ")} están escribiendo…`) : "";
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

// Banner: el DM te pide una tirada (con su CD). Botón para responderla.
function pintarTiradaPedida(camp) {
  const el = $("ui-tirada-pedida");
  if (!el) return;
  const pend = (camp.tiradas_pendientes || []).find(p => p.me_toca);
  if (!pend) { el.hidden = true; el.innerHTML = ""; return; }
  const nombre = pend.habilidad.replaceAll("_", " ");
  el.hidden = false;
  el.innerHTML = `<span>🎲 El DM te pide una tirada de <b>${esc(nombre)}</b> `
    + `(CD ${pend.cd})</span>`
    + `<button class="btn btn-ambar" id="btn-tirada-pedida">Tirar ${esc(nombre)}</button>`;
  $("btn-tirada-pedida").onclick = async () => {
    $("btn-tirada-pedida").disabled = true;
    try {
      const d = await enviarSkill(pend.habilidad, pend.cd, "");
      if (d.narrando === false)
        avisoSistema(`Tirada registrada; faltan ${d.faltan} por tirar.`);
    } catch(e){ avisoSistema(e.message); $("btn-tirada-pedida").disabled = false; }
  };
}

// ---------- log

async function pintarMensajes(reset = false) {
  if (reset) {
    // deshacer/regenerar BORRAN mensajes: re-render completo desde cero
    S.ultimoMsg = 0;
    const log0 = $("ui-log");
    [...log0.querySelectorAll(".msg")].forEach(m => m.remove());
  }
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

// heartbeat de "estoy escribiendo" (throttle 3s, solo con texto)
let ultimoTyping = 0;
$("inp-accion").addEventListener("input", () => {
  if (!$("inp-accion").value.trim() || !S.campaignId) return;
  const ahora = Date.now();
  if (ahora - ultimoTyping < 3000) return;
  ultimoTyping = ahora;
  api("POST", `/campaigns/${S.campaignId}/typing`, {}).catch(()=>{});
});

$("btn-regen").onclick = async () => {
  if (!confirm("¿Regenerar la última narración del DM?")) return;
  try {
    await api("POST", `/campaigns/${S.campaignId}/narration/regenerate`, {});
    S.narrando = true; pintarEscribiendo(); acelerarPolling();
    await pintarMensajes(true);
  } catch(e){ avisoSistema(e.message); }
};
$("btn-undo").onclick = async () => {
  if (!confirm("¿Deshacer tu última acción y la respuesta del DM?\n(Los efectos ya aplicados no se revierten.)")) return;
  try {
    await api("POST", `/campaigns/${S.campaignId}/narration/undo`, {});
    await pintarMensajes(true);
  } catch(e){ avisoSistema(e.message); }
};

$("btn-say").onclick = () => enviarAccion(false);
$("btn-party").onclick = () => enviarAccion(true);
$("inp-accion").addEventListener("keydown",(e)=>{
  if (e.key==="Enter" && !e.shiftKey){ e.preventDefault(); enviarAccion(false); }
});

let enviando = false;
async function enviarAccion(entreJugadores) {
  if (enviando) return;               // anti doble-envío (Enter + click, etc.)
  const texto = $("inp-accion").value.trim();
  if (!texto) return;
  enviando = true;
  setTimeout(()=>{ enviando = false; }, 800);
  $("inp-accion").value = "";
  try {
    await api("POST", `/campaigns/${S.campaignId}/say`,
              { texto, entre_jugadores: entreJugadores });
    if (!entreJugadores) { S.narrando = true; pintarEscribiendo(); }
    acelerarPolling(8);
    await pintarMensajes();
  } catch(e){ avisoSistema(e.message); }
}

async function enviarSkill(habilidad, cd, desc) {
  const d = await api("POST", `/campaigns/${S.campaignId}/skill-check`, {
    habilidad, cd, descripcion: desc || ""});
  sellarResolucion(d.resolucion);
  if (d.narrando) { S.narrando = true; pintarEscribiendo(); }
  acelerarPolling();
  await refrescarTodo(false);   // refresca el estado de tiradas pendientes
  return d;
}

$("btn-skill").onclick = async () => {
  $("btn-skill").disabled = true;
  try {
    await enviarSkill($("inp-habilidad").value, +$("inp-cd-dificultad").value,
                      $("inp-desc-habilidad").value.trim());
    $("inp-desc-habilidad").value = "";
  } catch(e){ avisoSistema(e.message); }
  $("btn-skill").disabled = false;
};

$("btn-save").onclick = async () => {
  $("btn-save").disabled = true;
  try {
    const d = await api("POST", `/campaigns/${S.campaignId}/saving-throw`, {
      atributo: $("inp-salvacion").value,
      descripcion: $("inp-desc-salvacion").value.trim()});
    sellarResolucion(d.resolucion);
    $("inp-desc-salvacion").value = "";
    S.narrando = true; pintarEscribiendo(); acelerarPolling();
  } catch(e){ avisoSistema(e.message); }
  $("btn-save").disabled = false;
};

// ---------- ficha

function pintarFicha(f) {
  S.miNombrePersonaje = f.nombre;
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
    <div class="linea-dato"><span>Monedas</span><span class="monedas"><span title="Oro">${f.monedas?.mo ?? 0} <b class="mo">mo</b></span> · <span title="Plata">${f.monedas?.mp ?? 0} <b class="mp">mp</b></span> · <span title="Cobre">${f.monedas?.mc ?? 0} <b class="mc">mc</b></span></span></div>
    ${slotsHTML ? "<h3 style='margin:.8rem 0 .2rem'>Espacios de conjuro</h3>"+slotsHTML : ""}
    ${f.concentracion ? `<div class="linea-dato"><span>Concentración</span><span>${esc(f.concentracion.hechizo)}</span></div>` : ""}
    ${(f.habilidades_activas||[]).length ?
      "<h3 style='margin:.8rem 0 .2rem'>Rasgos de clase</h3>" +
      f.habilidades_activas.map(h=>{
        const ui = HABILIDADES_CLASE_UI[h.nombre] || {icono:"✦", label:h.nombre.replaceAll("_"," ")};
        const estado = h.max !== null ? `${h.restante}/${h.max}` : "";
        const agotado = h.max !== null && h.restante <= 0;
        const fueraDeCombate = h.combate && S.campania?.estado !== "combate";
        return `<div class="recurso-linea">
          <span>${ui.label} <span class="party-pg">${estado}</span></span>
          <button class="btn" data-clase-hab="${h.nombre}"
            ${agotado || fueraDeCombate ? "disabled" : ""}
            title="${fueraDeCombate ? "Solo en combate" : ""}">${ui.icono} Usar</button>
        </div>`;
      }).join("") +
      (f.subclase && "<p class='nota'>"+esc(f.subclase.replaceAll("_"," "))+"</p>" || "") : ""}
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
    const ui = {...(HABILIDADES_CLASE_UI[nombre] || {}),
                ...((f.habilidades_activas||[]).find(h=>h.nombre===nombre) || {})};
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
    if (ui.enemigo) {
      // en combate: el select de objetivo ya tiene a los enemigos vivos
      const sel = $("inp-objetivo");
      if (!sel || !sel.value) return avisoSistema("No hay objetivo en combate");
      body.objetivo_npc_id = +sel.value;
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
  S.mundo = st;                       // lo usan los modales de info
  const quests = st.quests.filter(q=>q.estado==="activa");
  const hechas = st.quests.filter(q=>q.estado!=="activa");
  const abiertos = S.seccionesAbiertas || (S.seccionesAbiertas = {party:true, misiones:true});
  const sec = (id, titulo, badge, html) => `
    <details data-sec="${id}" ${abiertos[id] ? "open" : ""}>
      <summary>${titulo} <span class="badge">${badge}</span></summary>
      <div class="sec-cuerpo">${html}</div>
    </details>`;

  const party = (S.campania?.personajes || []).map(p => {
    const conds = p.condiciones?.length ? " · " + p.condiciones.join(", ") : "";
    return `<div class="party-linea">
      <span><b>${esc(p.nombre)}</b>${p.vivo ? "" : " 💀"}
        <div class="party-meta">${esc(p.raza)} ${esc(p.clase)} nv${p.nivel} ·
        ${esc((p.alineamiento||"").replaceAll("_"," "))}${conds}</div></span>
      <span class="party-pg">${p.pg_actual}/${p.pg_max} PG</span>
    </div>`;
  }).join("") || '<p class="nota">Nadie en la mesa.</p>';

  const misiones = quests.map(q =>
    `<p class="quest"><b>${esc(q.titulo)}</b> — ${esc(q.descripcion)}</p>`
  ).join("") + (hechas.length
    ? `<p class="nota">${hechas.length} completada(s)</p>` : "")
    || '<p class="nota">Sin misiones activas.</p>';

  // Personajes conocidos, Presagios y Crónica ahora viven en modales
  // (botones en la barra de info); acá quedan solo party y misiones.
  $("ui-mundo").innerHTML =
    sec("party", "La party", (S.campania?.personajes||[]).length, party) +
    sec("misiones", "Misiones", quests.length, misiones);

  // recordar qué secciones dejó abiertas el jugador
  $("ui-mundo").querySelectorAll("details").forEach(d =>
    d.addEventListener("toggle", () =>
      S.seccionesAbiertas[d.dataset.sec] = d.open));
}

// ---------------------------------------------------------------- modales de info

function abrirModal(titulo, htmlCuerpo) {
  cerrarModal();
  const ov = document.createElement("div");
  ov.className = "panel-conjuros modal-info";
  ov.id = "modal-info";
  ov.innerHTML = `<div class="caja">
    <button class="modal-cerrar" aria-label="Cerrar">✕</button>
    <h2>${esc(titulo)}</h2>
    <div class="modal-cuerpo">${htmlCuerpo}</div>
  </div>`;
  ov.querySelector(".modal-cerrar").onclick = cerrarModal;
  ov.addEventListener("click", (e) => { if (e.target === ov) cerrarModal(); });
  document.body.appendChild(ov);
}

function cerrarModal() {
  const ov = $("modal-info");
  if (ov) ov.remove();
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") cerrarModal();
});

const _pretty = (s) => esc((s ?? "—").toString().replaceAll("_", " "));

function _tags(lista, vacio) {
  if (!lista || !lista.length) return `<p class="info-vacio">${vacio}</p>`;
  return `<div class="info-tags">${lista.map(x =>
    `<span class="info-tag">${_pretty(x)}</span>`).join("")}</div>`;
}

function fichaCompletaHTML(f) {
  if (!f) return '<p class="info-vacio">Todavía no cargaste tu personaje.</p>';
  const opc = f.opciones_clase || {};
  const comp = f.competencias || {};
  const mon = f.monedas || {};
  const linea = (k, v) => `<div class="info-linea"><span>${k}</span><span>${v}</span></div>`;
  const stats = ATRS.map(a => `<div class="info-celda">
    <span class="n">${a}</span>
    <span class="v">${f.atributos[a].valor}</span>
    <span class="m">${signo(f.atributos[a].mod)}</span></div>`).join("");
  const inv = (f.inventario || []).length
    ? `<div class="info-tags">${f.inventario.map(it =>
        `<span class="info-tag">${_pretty(it.nombre)}${it.cantidad>1?` ×${it.cantidad}`:""}</span>`
      ).join("")}</div>`
    : '<p class="info-vacio">Sin objetos.</p>';
  const trasfondo = opc.trasfondo
    ? `${_pretty(opc.trasfondo)}${opc.rasgo_trasfondo ? ` — <i>${esc(opc.rasgo_trasfondo)}</i>` : ""}`
    : "—";

  return `
    <p class="info-sub">${_pretty(f.raza)} · ${_pretty(f.clase)}${
      f.subclase ? ` (${_pretty(f.subclase)})` : ""} · nivel ${f.nivel} · ${
      _pretty(f.alineamiento)}${f.genero ? ` · ${_pretty(f.genero)}` : ""}</p>

    <div class="info-grid">${stats}</div>

    <div class="info-grid" style="grid-template-columns:repeat(auto-fit,minmax(5.5rem,1fr))">
      <div class="info-celda"><span class="n">PG</span><span class="v">${f.pg_actual}/${f.pg_max}</span></div>
      <div class="info-celda"><span class="n">CA</span><span class="v">${f.ca}</span></div>
      <div class="info-celda"><span class="n">Inic.</span><span class="v">${signo(f.iniciativa_mod)}</span></div>
      <div class="info-celda"><span class="n">Comp.</span><span class="v">${signo(f.bc)}</span></div>
      <div class="info-celda"><span class="n">Vel.</span><span class="v">${f.velocidad_m}m</span></div>
      <div class="info-celda"><span class="n">D. golpe</span><span class="v">${f.dados_golpe_disp}${f.dado_golpe}</span></div>
    </div>

    <h3>Identidad</h3>
    ${linea("Nombre", esc(f.nombre))}
    ${linea("Raza / subraza", _pretty(f.raza))}
    ${linea("Clase / subclase", `${_pretty(f.clase)}${f.subclase ? ` (${_pretty(f.subclase)})` : ""}`)}
    ${opc.multiclase ? linea("Multiclase", _pretty(opc.multiclase)) : ""}
    ${linea("Trasfondo", trasfondo)}
    ${linea("Alineamiento", _pretty(f.alineamiento))}
    ${f.estilo_combate ? linea("Estilo de combate", _pretty(f.estilo_combate)) : ""}
    ${linea("XP", `${f.xp}${f.nivel_por_xp>f.nivel ? ` · puede subir a nv ${f.nivel_por_xp}` : ""}`)}

    <h3>Salvaciones</h3>
    ${_tags(comp.salvaciones, "Ninguna competencia de salvación.")}

    <h3>Habilidades competentes</h3>
    ${_tags(comp.habilidades, "Ninguna.")}
    ${(opc.expertise||[]).length ? `<h3>Pericia (expertise)</h3>${_tags(opc.expertise,"")}` : ""}

    <h3>Competencias de equipo</h3>
    ${linea("Armas", comp.armas ? comp.armas.map(x=>_pretty(x)).join(", ") : "—")}
    ${linea("Armaduras", comp.armaduras && comp.armaduras.length ? comp.armaduras.map(x=>_pretty(x)).join(", ") : "—")}

    ${(opc.invocaciones||[]).length ? `<h3>Invocaciones</h3>${_tags(opc.invocaciones,"")}` : ""}
    ${(opc.metamagia||[]).length ? `<h3>Metamagia</h3>${_tags(opc.metamagia,"")}` : ""}
    ${(f.feats||[]).length ? `<h3>Dotes</h3>${_tags(f.feats,"")}` : ""}

    <h3>Equipo</h3>
    ${linea("Arma", _pretty(f.arma_equipada))}
    ${linea("Armadura", `${_pretty(f.armadura)}${f.escudo ? " + escudo" : ""}`)}
    ${linea("Monedas", `<span class="monedas"><span title="Oro">${mon.mo??0} <b class="mo">mo</b></span> · <span title="Plata">${mon.mp??0} <b class="mp">mp</b></span> · <span title="Cobre">${mon.mc??0} <b class="mc">mc</b></span></span>`)}

    <h3>Inventario</h3>
    ${inv}

    ${(f.conocidos||[]).length || (f.preparados||[]).length
      ? `<h3>Conjuros</h3>${_tags((f.preparados&&f.preparados.length)?f.preparados:f.conocidos,"")}`
      : ""}
  `;
}

$("btn-ver-personaje").onclick = () =>
  abrirModal(S.ficha ? S.ficha.nombre : "Personaje", fichaCompletaHTML(S.ficha));

$("btn-ver-conocidos").onclick = () => {
  const st = S.mundo || {};
  const npcs = (st.npcs_conocidos || []);
  const html = npcs.length
    ? npcs.map(n => `<div class="info-linea">
        <span><b>${esc(n.nombre)}</b>${n.rol ? ` · ${esc(n.rol)}` : ""}</span>
        <span class="party-meta">${_pretty(n.actitud)}${n.en_escena ? " · presente" : ""}</span>
      </div>`).join("")
    : '<p class="info-vacio">Todavía no conocés a nadie.</p>';
  abrirModal("Personajes conocidos", html);
};

$("btn-ver-presagios").onclick = () => {
  const st = S.mundo || {};
  const n = st.consecuencias_pendientes || 0;
  const html = n > 0
    ? `<p>Pesan <b>${n}</b> consecuencia(s) pendiente(s) sobre el grupo. Algo se está gestando…</p>`
    : '<p class="info-vacio">El horizonte está despejado. Por ahora.</p>';
  abrirModal("Presagios", html);
};

$("btn-ver-cronica").onclick = () => {
  const st = S.mundo || {};
  const html = st.resumen
    ? `<div class="cronica-caja">${esc(st.resumen)}</div>`
    : '<p class="info-vacio">La historia recién empieza.</p>';
  abrirModal("Crónica", html);
};

// ---------- tabs móvil

document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("activo",x===t));
  document.querySelectorAll("[data-panel]").forEach(p=>
    p.classList.toggle("visible", p.dataset.panel===t.dataset.tab));
});
document.querySelector('[data-panel="juego"]')?.classList.add("visible");

for (const h of HABILIDADES) $("inp-habilidad").add(new Option(h.replaceAll("_"," "), h));
const DIFICULTADES = [["Muy fácil (5)",5],["Fácil (10)",10],["Media (15)",15],
  ["Difícil (20)",20],["Muy difícil (25)",25],["Casi imposible (30)",30]];
for (const [lbl,v] of DIFICULTADES) $("inp-cd-dificultad").add(new Option(lbl, v));
$("inp-cd-dificultad").value = "15";
const SALV_LABEL = {FUE:"Fuerza", DES:"Destreza", CON:"Constitución",
  INT:"Inteligencia", SAB:"Sabiduría", CAR:"Carisma"};
for (const a of ATRS) $("inp-salvacion").add(new Option(SALV_LABEL[a], a));

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
