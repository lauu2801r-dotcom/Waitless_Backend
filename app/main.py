from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import Base, engine
from app.modules.auth.router import router as auth_router
from app.modules.mesas.router import router as mesas_router
from app.modules.menu.router import router as menu_router

# Crear tablas en la base de datos
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WaitLess API",
    description="Backend API REST para el sistema de gestión de restaurantes WaitLess",
    version="1.0.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(auth_router, prefix="/auth", tags=["Autenticación"])
app.include_router(mesas_router, prefix="/mesas", tags=["Mesas"])
app.include_router(menu_router, prefix="/menu", tags=["Menú"])

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