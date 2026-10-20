from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Base de datos
    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Email
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"

    # Registro de administradores (se valida en el servidor)
    CODIGO_NEGOCIO: str = ""

    # Ambiente
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"


settings = Settings()
