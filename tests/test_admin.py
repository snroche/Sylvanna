"""Panel de admin: no debe reventar con consecuencias pendientes presentes."""
import pytest

from app.models import PendingConsequence


@pytest.fixture
def admin_token(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    get_settings.cache_clear()
    yield "secret"
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_full_con_consecuencia_pendiente(client, admin_token):
    d = (await client.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    cid = d["campaign_id"]

    from app.db import SessionLocal
    async with SessionLocal() as s:
        s.add(PendingConsequence(
            campaign_id=cid, evento="Investigar La Raíz Podrida",
            efecto="emboscada de matones", activacion="si van al callejón"))
        await s.commit()

    r = await client.get(f"/api/admin/campaigns/{cid}/full",
                         headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200, r.text
    cons = r.json()["consecuencias"]
    assert len(cons) == 1
    assert "emboscada de matones" in cons[0]["descripcion"]
    assert "La Raíz Podrida" in cons[0]["descripcion"]
