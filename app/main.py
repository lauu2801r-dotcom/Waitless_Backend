import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import Base, engine
from app.modules.auth.router import router as auth_router
from app.modules.mesas.router import router as mesas_router
from app.modules.menu.router import router as menu_router
from app.modules.reservas.router import router as reservas_router
from app.modules.pedidos.router import router as pedidos_router
from app.modules.reportes.router import router as reportes_router
from app.websocket.router import router as ws_router
from app.websocket.manager import manager
from app.ia.router import router as ia_router    
from app.ia import models as ia_models
from app.modules.auditoria.router import router as auditoria_router
from app.modules.auditoria import models as auditoria_models
from app.modules.usuarios.router import router as usuarios_router
from app.modules.inventario.router import router as inventario_router
from app.modules.inventario import models as inventario_models
from app.modules.compras.router import router as compras_router
from app.modules.compras import models as compras_models
from app.modules.pagos.router import router as pagos_router
from app.modules.pagos import models as pagos_models
from app.modules.clientes.router import router as clientes_router
from app.modules.clientes import models as clientes_models

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WaitLess API",
    description="Backend API REST para el sistema de gestión de restaurantes WaitLess",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # usamos Bearer token, no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,     prefix="/auth",      tags=["Autenticación"])
app.include_router(mesas_router,    prefix="/mesas",     tags=["Mesas"])
app.include_router(menu_router,     prefix="/menu",      tags=["Menú"])
app.include_router(reservas_router, prefix="/reservas",  tags=["Reservas"])
app.include_router(pedidos_router,  prefix="/pedidos",   tags=["Pedidos"])
app.include_router(reportes_router, prefix="/reportes",  tags=["Reportes"])
app.include_router(ws_router,       prefix="/ws",        tags=["WebSocket"])
app.include_router(ia_router,       prefix="/ia",        tags=["IA"])
app.include_router(auditoria_router, prefix="/auditoria", tags=["Auditoría"])
app.include_router(usuarios_router,  prefix="/usuarios",  tags=["Personal y usuarios"])
app.include_router(inventario_router, prefix="/inventario", tags=["Inventario y proveedores"])
app.include_router(compras_router,     prefix="/compras",    tags=["Órdenes de compra"])
app.include_router(pagos_router,       prefix="/pagos",      tags=["Pagos y facturación"])
app.include_router(clientes_router,    prefix="/clientes",   tags=["Perfil del cliente"])

from app.core.seed import seed_mesas

@app.on_event("startup")
async def startup_event():
    # Guardamos el bucle de eventos para poder emitir WebSocket desde endpoints síncronos
    manager.set_loop(asyncio.get_running_loop())
    seed_mesas()

@app.get("/")
def root():
    return {
        "message": "WaitLess API funcionando",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}