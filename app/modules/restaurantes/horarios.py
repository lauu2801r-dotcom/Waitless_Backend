"""
Horarios de atención de un restaurante (HU-023).

Se guardan como JSON en restaurantes.horarios:
  {
    "semana": {"lun": {"abre": "12:00", "cierra": "22:00"}, ..., "dom": null},   # null = cerrado
    "especiales": [{"fecha": "2026-12-25", "cerrado": true, "nota": "Navidad"},
                   {"fecha": "2026-12-31", "abre": "12:00", "cierra": "16:00", "nota": "Fin de año"}]
  }
Un día especial reemplaza al horario normal de esa fecha. Si el restaurante no
configuró horarios, no se restringe nada. No se admiten horarios que crucen la medianoche.
"""
import json
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
NOMBRES = {"lun": "lunes", "mar": "martes", "mie": "miércoles", "jue": "jueves",
           "vie": "viernes", "sab": "sábado", "dom": "domingo"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _hora_valida(v: str) -> str:
    if not _HHMM.match(v or ""):
        raise ValueError("La hora debe tener formato HH:MM (24 horas)")
    return v


class Franja(BaseModel):
    abre: str
    cierra: str

    _v = field_validator("abre", "cierra")(_hora_valida)

    @model_validator(mode="after")
    def _orden(self):
        if self.abre >= self.cierra:
            raise ValueError("La hora de cierre debe ser posterior a la de apertura")
        return self


class DiaEspecial(BaseModel):
    fecha: date
    cerrado: bool = False
    abre: Optional[str] = None
    cierra: Optional[str] = None
    nota: Optional[str] = None

    @model_validator(mode="after")
    def _coherente(self):
        if not self.cerrado:
            if not (self.abre and self.cierra):
                raise ValueError("Un día especial abierto necesita hora de apertura y cierre")
            _hora_valida(self.abre)
            _hora_valida(self.cierra)
            if self.abre >= self.cierra:
                raise ValueError("La hora de cierre debe ser posterior a la de apertura")
        if self.nota:
            self.nota = self.nota.strip()[:80] or None
        return self


class Horarios(BaseModel):
    semana: Dict[str, Optional[Franja]] = {}
    especiales: List[DiaEspecial] = []

    @field_validator("semana")
    @classmethod
    def _dias(cls, v):
        malos = [d for d in v if d not in DIAS]
        if malos:
            raise ValueError(f"Día no válido: {malos[0]} (usa {', '.join(DIAS)})")
        return v

    @field_validator("especiales")
    @classmethod
    def _limite(cls, v):
        if len(v) > 60:
            raise ValueError("Máximo 60 días especiales")
        return v


def leer(texto: Optional[str]) -> Optional[dict]:
    if not texto:
        return None
    try:
        d = json.loads(texto)
        return d if isinstance(d, dict) else None
    except (ValueError, TypeError):
        return None


def ahora_colombia() -> datetime:
    return datetime.utcnow() - timedelta(hours=5)


def _franja_del_dia(h: dict, dt: datetime):
    """Devuelve (franja|None, nota|None) para esa fecha. franja None = cerrado."""
    iso = dt.date().isoformat()
    for e in h.get("especiales") or []:
        if e.get("fecha") == iso:
            if e.get("cerrado"):
                return None, (e.get("nota") or "día especial")
            return {"abre": e.get("abre"), "cierra": e.get("cierra")}, e.get("nota")
    return (h.get("semana") or {}).get(DIAS[dt.weekday()]), None


def estado_en(texto_horarios: Optional[str], dt: datetime):
    """
    ¿Está abierto en `dt` (hora de Colombia, sin zona)?
    Devuelve (abierto: bool | None, mensaje). None = el restaurante no configuró horarios.
    """
    h = leer(texto_horarios)
    if not h or not (h.get("semana") or h.get("especiales")):
        return None, ""
    franja, nota = _franja_del_dia(h, dt)
    dia = NOMBRES[DIAS[dt.weekday()]]
    if not franja:
        motivo = f" ({nota})" if nota else ""
        return False, f"El restaurante está cerrado el {dia} {dt.strftime('%d/%m')}{motivo}"
    hora = dt.strftime("%H:%M")
    if franja["abre"] <= hora < franja["cierra"]:
        return True, ""
    return False, f"Fuera del horario de atención: {franja['abre']} a {franja['cierra']}"


def serializar(h: Horarios) -> str:
    return json.dumps(h.model_dump(mode="json"), ensure_ascii=False)
