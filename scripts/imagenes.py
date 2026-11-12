"""
Imágenes fijas de platos y restaurantes.

Se ejecuta desde la carpeta Waitless_Backend:

    python -m scripts.imagenes listar      -> muestra tus platos y restaurantes, el nombre de archivo
                                              que debe tener cada foto y un prompt listo para generarla
                                              (también lo guarda en static/imagenes/PROMPTS.md)
    python -m scripts.imagenes optimizar   -> reduce las fotos a 900 px y las pasa a JPG liviano (requiere Pillow)
    python -m scripts.imagenes asignar     -> asigna cada foto encontrada a su plato / restaurante en la base de datos

Dónde van las fotos:
    static/imagenes/platos/<nombre-del-plato>.jpg
    static/imagenes/restaurantes/<nombre-del-restaurante>.jpg
Si el mismo plato existe en dos restaurantes y quieres fotos distintas, nombra la foto
<restaurante>__<plato>.jpg (por ejemplo corona__agua-mineral.jpg).
"""
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE = RAIZ / "static" / "imagenes"
EXTENSIONES = (".jpg", ".jpeg", ".png", ".webp")


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def buscar_archivo(carpeta: Path, *nombres: str):
    for n in nombres:
        for ext in EXTENSIONES:
            f = carpeta / f"{n}{ext}"
            if f.exists():
                return f
    return None


def prompt_plato(p) -> str:
    desc = f" ({p.descripcion.strip()})" if (p.descripcion or "").strip() else ""
    bebida = (p.categoria or "").lower() in ("bebidas", "bebida", "cocteles", "cócteles", "vinos")
    servido = "servida en un vaso o copa elegante" if bebida else "emplatado con cuidado en un plato de cerámica"
    return (
        f"Fotografía profesional de comida para el menú de un restaurante: {p.nombre}{desc}, {servido}. "
        "Vista a 45 grados, luz natural suave, fondo de mesa de madera ligeramente desenfocado, colores cálidos, "
        "aspecto apetitoso y realista, sin texto, sin logotipos, sin manos, formato cuadrado 1:1."
    )


def prompt_restaurante(r) -> str:
    tipo = f" de cocina {r.tipo_cocina}" if r.tipo_cocina else ""
    return (
        f"Fotografía profesional del interior de un restaurante{tipo} llamado «{r.nombre}»: ambiente acogedor, "
        "mesas de madera, luz cálida, decoración cuidada, sin personas en primer plano, sin texto ni letreros "
        "legibles, estilo editorial, formato horizontal 16:9."
    )


def _abrir():
    from app.core.database import SessionLocal
    return SessionLocal()


def cmd_listar():
    from app.modules.auth.models import Restaurante
    from app.modules.menu.models import Producto
    (BASE / "platos").mkdir(parents=True, exist_ok=True)
    (BASE / "restaurantes").mkdir(parents=True, exist_ok=True)
    db = _abrir()
    restaurantes = db.query(Restaurante).order_by(Restaurante.nombre).all()
    productos = db.query(Producto).filter(Producto.activo.is_(True)).order_by(Producto.nombre).all()

    salida = ["# Imágenes pendientes de WaitLess\n",
              "Genera cada imagen con tu herramienta de IA, guárdala con el **nombre de archivo indicado** "
              "(jpg, png o webp) en la carpeta indicada y luego ejecuta `python -m scripts.imagenes asignar`.\n",
              "## Restaurantes (carpeta `static/imagenes/restaurantes/`)\n"]
    for r in restaurantes:
        tiene = buscar_archivo(BASE / "restaurantes", slug(r.nombre))
        salida.append(f"### {r.nombre}  {'✅ ya tiene foto' if tiene else '⬜ falta'}\n"
                      f"- Archivo: `{slug(r.nombre)}.jpg`\n- Prompt: {prompt_restaurante(r)}\n")
    salida.append("## Platos (carpeta `static/imagenes/platos/`)\n")
    vistos = {}
    for p in productos:
        vistos.setdefault(slug(p.nombre), []).append(p)
    faltan = 0
    for s, lista in sorted(vistos.items()):
        p = lista[0]
        rests = ", ".join(sorted({x.restaurante_nombre or "-" for x in lista}))
        tiene = buscar_archivo(BASE / "platos", s, *[f"{slug(x.restaurante_nombre or '')}__{s}" for x in lista])
        if not tiene:
            faltan += 1
        salida.append(f"### {p.nombre}  {'✅' if tiene else '⬜ falta'}  ·  {p.categoria or 'Sin categoría'}  ·  {rests}\n"
                      f"- Archivo: `{s}.jpg`\n- Prompt: {prompt_plato(p)}\n")
    texto = "\n".join(salida)
    (BASE / "PROMPTS.md").write_text(texto, encoding="utf-8")
    print(f"{len(restaurantes)} restaurantes y {len(vistos)} platos distintos ({faltan} sin foto).")
    print(f"Prompts y nombres de archivo guardados en: {BASE / 'PROMPTS.md'}")
    db.close()


def cmd_optimizar():
    try:
        from PIL import Image
    except ImportError:
        print("Falta Pillow. Instálalo con:  pip install pillow")
        return
    n = 0
    for carpeta in ("platos", "restaurantes"):
        for f in sorted((BASE / carpeta).glob("*")):
            if f.suffix.lower() not in EXTENSIONES:
                continue
            img = Image.open(f).convert("RGB")
            img.thumbnail((900, 900))
            destino = f.with_suffix(".jpg")
            img.save(destino, "JPEG", quality=82, optimize=True)
            if destino != f:
                f.unlink()
            n += 1
    print(f"{n} imágenes optimizadas (máx. 900 px, JPG).")


def cmd_asignar():
    from app.modules.auth.models import Restaurante
    from app.modules.menu.models import Producto
    db = _abrir()
    ok_p = ok_r = 0
    sin = []
    for r in db.query(Restaurante).all():
        f = buscar_archivo(BASE / "restaurantes", slug(r.nombre))
        if f:
            r.imagen_url = f"/static/imagenes/restaurantes/{f.name}"
            ok_r += 1
        else:
            sin.append(f"restaurante: {r.nombre}")
    for p in db.query(Producto).all():
        s = slug(p.nombre)
        f = buscar_archivo(BASE / "platos", f"{slug(p.restaurante_nombre or '')}__{s}", s)
        if f:
            p.imagen_url = f"/static/imagenes/platos/{f.name}"
            ok_p += 1
        elif p.activo:
            sin.append(f"plato: {p.nombre} ({p.restaurante_nombre or '-'})")
    db.commit()
    db.close()
    print(f"Asignadas: {ok_r} restaurantes y {ok_p} platos.")
    if sin:
        print(f"Sin foto todavía ({len(sin)}):")
        for x in sin[:60]:
            print("  -", x)


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    {"listar": cmd_listar, "optimizar": cmd_optimizar, "asignar": cmd_asignar}.get(
        comando, lambda: print(__doc__))()
