"""Armazenamento de reservas e visitantes (SQLite).

A exclusividade de (área, data) é garantida pelo banco: índice único parcial sobre as
reservas ativas. Cancelar não apaga a linha (status 'cancelada'), então o código nunca
é reaproveitado; novos códigos vêm de uma sequência AUTOINCREMENT.
"""

import json
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sequencia_codigo (n INTEGER PRIMARY KEY AUTOINCREMENT);
CREATE TABLE IF NOT EXISTS reservas (
    codigo TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL,
    area TEXT NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'cancelada'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_reserva_ativa
    ON reservas (area, data) WHERE status = 'ativa';
CREATE TABLE IF NOT EXISTS visitantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apartamento TEXT NOT NULL,
    nome TEXT NOT NULL,
    data TEXT NOT NULL,
    UNIQUE (apartamento, nome, data)
);
"""

# Os códigos gerados começam acima de qualquer código do estado inicial.
OFFSET_CODIGO = 10000


@contextmanager
def conexao():
    config.ESTADO_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_NEGOCIO, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    try:
        yield con
    finally:
        con.close()


def inicializar() -> None:
    """Cria o schema e carrega `dados/` se o banco ainda não foi populado."""
    with conexao() as con:
        con.executescript(SCHEMA)
        con.execute("BEGIN IMMEDIATE")
        try:
            vazio = con.execute("SELECT COUNT(*) FROM reservas").fetchone()[0] == 0 and (
                con.execute("SELECT COUNT(*) FROM visitantes").fetchone()[0] == 0
            )
            if vazio:
                _carregar_dados_iniciais(con)
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise


def _carregar_dados_iniciais(con: sqlite3.Connection) -> None:
    for r in json.loads((config.DADOS_DIR / "reservas.json").read_text(encoding="utf-8")):
        con.execute(
            "INSERT INTO reservas (codigo, apartamento, area, data) VALUES (?,?,?,?)",
            (r["codigo"], r["apartamento"], r["area"], r["data"]),
        )
    for v in json.loads((config.DADOS_DIR / "visitantes.json").read_text(encoding="utf-8")):
        con.execute(
            "INSERT OR IGNORE INTO visitantes (apartamento, nome, data) VALUES (?,?,?)",
            (v["apartamento"], v["nome"], v["data"]),
        )


def restaurar() -> None:
    """Volta reservas e visitantes ao estado de `dados/` (a sequência de códigos é mantida)."""
    with conexao() as con:
        con.executescript(SCHEMA)
        con.execute("BEGIN IMMEDIATE")
        try:
            con.execute("DELETE FROM reservas")
            con.execute("DELETE FROM visitantes")
            _carregar_dados_iniciais(con)
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise


# ---------- dados de referência (somente leitura) ----------

def areas() -> dict[str, dict]:
    lista = json.loads((config.DADOS_DIR / "areas.json").read_text(encoding="utf-8"))
    return {a["id"]: a for a in lista}


# ---------- consultas ----------

def reservas_do_apartamento(apartamento: str) -> list[dict]:
    with conexao() as con:
        rows = con.execute(
            "SELECT codigo, area, data FROM reservas "
            "WHERE apartamento=? AND status='ativa' ORDER BY data, codigo",
            (apartamento,),
        ).fetchall()
    return [dict(r) for r in rows]


def visitantes_do_apartamento(apartamento: str) -> list[dict]:
    with conexao() as con:
        rows = con.execute(
            "SELECT nome, data FROM visitantes WHERE apartamento=? ORDER BY data, nome",
            (apartamento,),
        ).fetchall()
    return [dict(r) for r in rows]


def data_ocupada(area: str, data: str) -> bool:
    """Só livre/ocupado: nunca devolve de quem é a reserva."""
    with conexao() as con:
        row = con.execute(
            "SELECT 1 FROM reservas WHERE area=? AND data=? AND status='ativa'", (area, data)
        ).fetchone()
    return row is not None


# ---------- gravações ----------

def criar_reserva(apartamento: str, area: str, data: str) -> dict:
    """Grava a reserva. A exclusividade vale no INSERT (índice único), sem checagem prévia.

    Retorna {"ok": True, "codigo": ...} ou {"ok": False, "motivo": "data_ocupada"}.
    """
    with conexao() as con:
        cur = con.execute("INSERT INTO sequencia_codigo DEFAULT VALUES")
        codigo = f"RSV-{OFFSET_CODIGO + cur.lastrowid}"
        try:
            con.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data) VALUES (?,?,?,?)",
                (codigo, apartamento, area, data),
            )
        except sqlite3.IntegrityError:
            return {"ok": False, "motivo": "data_ocupada"}
    return {"ok": True, "codigo": codigo}


def cancelar_reserva(apartamento: str, area: str, data: str) -> dict | None:
    """Cancela a reserva ativa do próprio apartamento. Devolve a reserva ou None."""
    with conexao() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT codigo FROM reservas "
            "WHERE apartamento=? AND area=? AND data=? AND status='ativa'",
            (apartamento, area, data),
        ).fetchone()
        if row is None:
            con.execute("COMMIT")
            return None
        con.execute("UPDATE reservas SET status='cancelada' WHERE codigo=?", (row["codigo"],))
        con.execute("COMMIT")
    return {"codigo": row["codigo"], "area": area, "data": data}


def autorizar_visitante(apartamento: str, nome: str, data: str) -> dict:
    with conexao() as con:
        try:
            con.execute(
                "INSERT INTO visitantes (apartamento, nome, data) VALUES (?,?,?)",
                (apartamento, nome, data),
            )
        except sqlite3.IntegrityError:
            return {"ok": True, "ja_autorizado": True}
    return {"ok": True}
