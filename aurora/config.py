"""Caminhos e configuração. Os dados em `dados/` são só leitura (estado inicial)."""

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

DADOS_DIR = RAIZ / "dados"
# Armazenamento durável das mudanças (reservas, visitantes e sessões).
ESTADO_DIR = Path(os.getenv("AURORA_ESTADO_DIR", RAIZ / "estado"))
DB_NEGOCIO = ESTADO_DIR / "condominio.db"
DB_SESSOES = ESTADO_DIR / "sessoes.db"

MODELO_PRINCIPAL = os.getenv("AURORA_MODELO_PRINCIPAL", "gemini-2.5-flash")
MODELO_ESPECIALISTA = os.getenv("AURORA_MODELO_ESPECIALISTA", "gemini-2.5-flash")
