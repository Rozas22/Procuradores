"""Ajustes del usuario y lista de escritos (todo en el propio ordenador)."""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NOMBRE = "Escritos Procura"


def carpeta_datos() -> Path:
    base = os.environ.get("ESCRITOS_PROCURA_DATOS") or os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / "EscritosProcura"
    p.mkdir(parents=True, exist_ok=True)
    return p


PORTALES = {
    "Justizia.eus (País Vasco)": "https://psp.justizia.eus/PSP/app/index.html#/",
    "LexNET": "https://lexnet.justicia.es/",
    "Otro": "",
}


@dataclass
class Ajustes:
    carpeta_escritos: str = ""
    formato_carpeta: str = "{num}.{aa}"
    portal_nombre: str = "Justizia.eus (País Vasco)"
    portal_url: str = PORTALES["Justizia.eus (País Vasco)"]
    escribir_ficha: bool = True
    revisar_siempre: bool = False

    @property
    def configurado(self) -> bool:
        return bool(self.carpeta_escritos)

    @classmethod
    def cargar(cls) -> "Ajustes":
        f = carpeta_datos() / "ajustes.json"
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()

    def guardar(self):
        f = carpeta_datos() / "ajustes.json"
        f.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")


ESTADOS = ["Pendiente de firmar", "Firmado", "Presentado"]


@dataclass
class Escrito:
    id: int | None = None
    recibido: str = ""          # ISO
    tipo_escrito: str = ""
    procedimiento: str = ""
    organo: str = ""
    plaza: str = ""
    demandante: str = ""
    demandado: str = ""
    carpeta: str = ""
    principal: str = ""
    anexos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    estado: str = "Pendiente de firmar"
    estado_manual: bool = False
    origen: str = ""
    clave: str = ""

    @property
    def recibido_ts(self) -> float:
        try:
            return dt.datetime.fromisoformat(self.recibido).timestamp()
        except ValueError:
            return 0.0


class Almacen:
    def __init__(self, ruta: Path | None = None):
        self.ruta = ruta or carpeta_datos() / "escritos.db"
        self.db = sqlite3.connect(str(self.ruta))
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS escritos(
            id INTEGER PRIMARY KEY, recibido TEXT, tipo_escrito TEXT, procedimiento TEXT,
            organo TEXT, plaza TEXT, demandante TEXT, demandado TEXT, carpeta TEXT,
            principal TEXT, anexos TEXT, avisos TEXT, estado TEXT, estado_manual INTEGER,
            origen TEXT, clave TEXT UNIQUE)""")
        self.db.commit()

    def _a_escrito(self, r) -> Escrito:
        d = dict(r)
        d["anexos"] = json.loads(d["anexos"] or "[]")
        d["avisos"] = json.loads(d["avisos"] or "[]")
        d["estado_manual"] = bool(d["estado_manual"])
        return Escrito(**d)

    def existe(self, clave: str) -> Escrito | None:
        r = self.db.execute("SELECT * FROM escritos WHERE clave=?", (clave,)).fetchone()
        return self._a_escrito(r) if r else None

    def guardar(self, e: Escrito) -> Escrito:
        d = asdict(e)
        d["anexos"] = json.dumps(e.anexos, ensure_ascii=False)
        d["avisos"] = json.dumps(e.avisos, ensure_ascii=False)
        d["estado_manual"] = int(e.estado_manual)
        if e.id is None:
            d.pop("id")
            cols = ",".join(d)
            cur = self.db.execute(f"INSERT INTO escritos({cols}) VALUES({','.join('?' * len(d))})", list(d.values()))
            e.id = cur.lastrowid
        else:
            sets = ",".join(f"{k}=?" for k in d if k != "id")
            self.db.execute(f"UPDATE escritos SET {sets} WHERE id=?", [v for k, v in d.items() if k != "id"] + [e.id])
        self.db.commit()
        return e

    def borrar(self, id_: int):
        self.db.execute("DELETE FROM escritos WHERE id=?", (id_,))
        self.db.commit()

    def todos(self) -> list[Escrito]:
        return [self._a_escrito(r) for r in self.db.execute("SELECT * FROM escritos ORDER BY recibido DESC")]
