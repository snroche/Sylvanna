"""Competencias: no podés equipar lo que tu clase no domina; salvaciones."""
import pytest

MAGO = {
    "nombre": "Elara", "raza": "humano", "subraza": "estandar", "clase": "mago",
    "metodo": "libre",
    "atributos": {"FUE": 8, "DES": 14, "CON": 12, "INT": 15, "SAB": 10, "CAR": 10},
    "habilidades": ["arcanos", "investigacion"], "arma_equipada": "daga",
}
GUERRERO = {
    "nombre": "Bran", "raza": "humano", "subraza": "estandar", "clase": "guerrero",
    "metodo": "libre", "estilo_combate": "defensa",
    "atributos": {"FUE": 15, "DES": 12, "CON": 14, "INT": 8, "SAB": 10, "CAR": 10},
    "habilidades": ["atletismo"], "arma_equipada": "espada_larga",
    "armadura": "coraza", "escudo": True,
}


async def _campos(client, body):
    r = await client.post("/api/campaigns", json={
        "nombre": "C", "nombre_jugador": "S"})
    d = r.json()
    h = {"X-Player-Token": d["player_token"]}
    return d["campaign_id"], h, await client.post("/api/characters",
                                                  json=body, headers=h)


@pytest.mark.anyio
async def test_mago_no_puede_arma_marcial(client):
    _, _, r = await _campos(client, {**MAGO, "arma_equipada": "espada_larga"})
    assert r.status_code == 400
    assert "competente" in r.text.lower()


@pytest.mark.anyio
async def test_mago_no_puede_armadura_pesada(client):
    _, _, r = await _campos(client, {**MAGO, "armadura": "cota_de_mallas"})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_mago_no_puede_escudo(client):
    _, _, r = await _campos(client, {**MAGO, "escudo": True})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_guerrero_si_puede_todo(client):
    _, _, r = await _campos(client, GUERRERO)
    assert r.status_code == 200, r.text


@pytest.mark.anyio
async def test_equipar_arma_no_competente_falla(client):
    # el mago tiene un mandoble en el inventario (loot) pero no sabe usarlo
    cid, h, r = await _campos(client, {
        **MAGO, "inventario": [{"nombre": "mandoble", "cantidad": 1}]})
    assert r.status_code == 200
    r = await client.post(f"/api/campaigns/{cid}/inventory/equip",
                          json={"arma": "mandoble"}, headers=h)
    assert r.status_code == 400
    assert "competente" in r.text.lower()


@pytest.mark.anyio
async def test_saving_throw_competente_suma_bc(client):
    cid, h, r = await _campos(client, GUERRERO)
    assert r.status_code == 200
    # guerrero humano estándar: FUE 15+1=16 => +3 ; BC(1)=2 => bono 5
    r = await client.post(f"/api/campaigns/{cid}/saving-throw",
                          json={"atributo": "FUE", "cd": 10}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["resolucion"]["bono"] == 5
    # INT no es salvación competente: mod(8+1) = -1, sin BC
    r = await client.post(f"/api/campaigns/{cid}/saving-throw",
                          json={"atributo": "INT", "cd": 10}, headers=h)
    assert r.json()["resolucion"]["bono"] == -1


@pytest.mark.anyio
async def test_saving_throw_atributo_invalido(client):
    cid, h, _ = await _campos(client, GUERRERO)
    r = await client.post(f"/api/campaigns/{cid}/saving-throw",
                          json={"atributo": "XXX", "cd": 10}, headers=h)
    assert r.status_code == 400


@pytest.mark.anyio
async def test_content_expone_trasfondos_y_competencias(client):
    d = (await client.get("/api/content")).json()
    assert "trasfondos" in d and "acolito" in d["trasfondos"]
    assert d["competencias_clase"]["mago"]["armas"] == ["simple"]
    assert d["armas_info"]["espada_larga"]["categoria"] == "marcial"
    assert d["armaduras_info"]["cuero"]["categoria"] == "ligera"
    assert d["habilidades_clase"]["picaro"]["cantidad"] == 4
    assert "atletismo" in d["habilidades_clase"]["guerrero"]["lista"]


@pytest.mark.anyio
async def test_trasfondo_soldado_fuerza_habilidades(client):
    cid, h, r = await _campos(client, {
        **GUERRERO, "trasfondo": "soldado", "habilidades": ["percepcion"],
        "genero": "femenino"})
    assert r.status_code == 200, r.text
    cid_char = r.json()["character_id"]
    ficha = (await client.get(f"/api/characters/{cid_char}/sheet",
                              headers=h)).json()
    habs = ficha["competencias"]["habilidades"]
    # soldado siempre da atletismo + intimidación; más la elegida de clase
    assert "atletismo" in habs and "intimidacion" in habs
    assert "percepcion" in habs
    assert ficha["genero"] == "femenino"


@pytest.mark.anyio
async def test_habilidad_fuera_de_lista_de_clase_falla(client):
    # sigilo no está en la lista de habilidades del mago
    _, _, r = await _campos(client, {**MAGO, "habilidades": ["sigilo"]})
    assert r.status_code == 400
    assert "lista de habilidades" in r.text.lower()


@pytest.mark.anyio
async def test_demasiadas_habilidades_de_clase_falla(client):
    # el mago elige 2; mandar 3 debe fallar
    _, _, r = await _campos(client, {
        **MAGO, "habilidades": ["arcanos", "historia", "medicina"]})
    assert r.status_code == 400
