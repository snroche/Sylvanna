"""Administración de campañas por línea de comandos.

Usa la misma configuración que la app (DATABASE_URL del entorno o .env),
así que sirve tanto para la DB local como para Neon (producción):

    python scripts/admin.py list
    python scripts/admin.py delete 3 7        # borra campañas 3 y 7
    python scripts/admin.py wipe --yes        # borra TODAS las campañas

Para correrlo contra Neon desde tu máquina:
    DATABASE_URL="postgresql://..." python scripts/admin.py list
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.db import SessionLocal, crear_tablas  # noqa: E402
from app.models import (NPC, Campaign, Character, Message,  # noqa: E402
                        PendingConsequence, Player, Quest, Roll)

# orden de borrado: hijos primero (sin FK cascade configurado)
TABLAS_HIJAS = [Roll, Message, PendingConsequence, Quest, NPC, Character, Player]


async def listar():
    async with SessionLocal() as db:
        camps = (await db.execute(select(Campaign))).scalars().all()
        if not camps:
            print("No hay campañas.")
            return
        for c in camps:
            n_players = len((await db.execute(
                select(Player).where(Player.campaign_id == c.id))).scalars().all())
            n_msgs = len((await db.execute(
                select(Message).where(Message.campaign_id == c.id))).scalars().all())
            print(f"  [{c.id}] {c.nombre!r} · estado={c.estado} · "
                  f"{n_players} jugador(es) · {n_msgs} mensajes · "
                  f"invite={c.invite_code} · creada={c.creada:%Y-%m-%d}")


async def borrar(ids: list[int]):
    async with SessionLocal() as db:
        for cid in ids:
            camp = await db.get(Campaign, cid)
            if camp is None:
                print(f"  [{cid}] no existe, salteada")
                continue
            for tabla in TABLAS_HIJAS:
                await db.execute(delete(tabla).where(tabla.campaign_id == cid))
            await db.delete(camp)
            print(f"  [{cid}] {camp.nombre!r} eliminada")
        await db.commit()


async def wipe():
    async with SessionLocal() as db:
        camps = (await db.execute(select(Campaign))).scalars().all()
        ids = [c.id for c in camps]
    if not ids:
        print("No hay campañas para borrar.")
        return
    await borrar(ids)
    print(f"Total: {len(ids)} campaña(s) eliminadas.")


def main():
    p = argparse.ArgumentParser(description="Admin de campañas")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="Listar campañas")
    d = sub.add_parser("delete", help="Borrar campañas por id")
    d.add_argument("ids", nargs="+", type=int)
    w = sub.add_parser("wipe", help="Borrar TODAS las campañas")
    w.add_argument("--yes", action="store_true",
                   help="Confirmación obligatoria")
    args = p.parse_args()

    async def run():
        await crear_tablas()
        if args.cmd == "list":
            await listar()
        elif args.cmd == "delete":
            await borrar(args.ids)
        elif args.cmd == "wipe":
            if not args.yes:
                print("Esto borra TODO. Repetí el comando con --yes")
                return
            await wipe()

    asyncio.run(run())


if __name__ == "__main__":
    main()
