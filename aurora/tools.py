"""Tools dos especialistas.

O apartamento vem SEMPRE de `tool_context.state["apartamento"]` (definido em POST /sessoes).
Nenhuma tool recebe apartamento como argumento, então o modelo não tem como escolher outro.
"""

import re

from google.adk.tools import ToolContext

from . import db, regulamento

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _apartamento(tool_context: ToolContext) -> str:
    return str(tool_context.state["apartamento"])


def _valida(area: str | None, data: str | None) -> dict | None:
    if area is not None and area not in db.areas():
        return {"erro": f"Área inválida. Áreas disponíveis: {', '.join(db.areas())}."}
    if data is not None and not _DATA.match(data):
        return {"erro": "Data inválida. Use o formato AAAA-MM-DD."}
    return None


# ---------- reservas ----------

def listar_minhas_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento do morador desta conversa."""
    return {"reservas": db.reservas_do_apartamento(_apartamento(tool_context))}


def verificar_disponibilidade(area: str, data: str, tool_context: ToolContext) -> dict:
    """Informa se a área está livre ou ocupada na data (AAAA-MM-DD). Não revela quem reservou.

    Args:
        area: id da área: salao-de-festas, churrasqueira ou quadra.
        data: data no formato AAAA-MM-DD.
    """
    if erro := _valida(area, data):
        return erro
    return {"area": area, "data": data, "disponivel": not db.data_ocupada(area, data)}


def reserva_pede_confirmacao(area: str = "", **_) -> bool:
    """Regra em código: só reserva de área com taxa > 0 (gera cobrança) pede confirmação."""
    return float(db.areas().get(area, {}).get("taxa", 0)) > 0


def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum para o apartamento do morador. Áreas com taxa geram cobrança.

    Args:
        area: id da área: salao-de-festas, churrasqueira ou quadra.
        data: data no formato AAAA-MM-DD.
    """
    if erro := _valida(area, data):
        return erro
    res = db.criar_reserva(_apartamento(tool_context), area, data)
    if not res["ok"]:
        return {"sucesso": False, "motivo": "A data já está ocupada para essa área."}
    taxa = float(db.areas()[area]["taxa"])
    return {"sucesso": True, "codigo": res["codigo"], "area": area, "data": data,
            "taxa_cobrada": taxa}


def cancelar_minha_reserva(area: str, data: str, tool_context: ToolContext) -> dict:
    """Cancela a reserva do apartamento do morador para a área e a data informadas.

    Args:
        area: id da área: salao-de-festas, churrasqueira ou quadra.
        data: data no formato AAAA-MM-DD.
    """
    if erro := _valida(area, data):
        return erro
    cancelada = db.cancelar_reserva(_apartamento(tool_context), area, data)
    if cancelada is None:
        return {"sucesso": False,
                "motivo": "Seu apartamento não tem reserva dessa área nessa data."}
    return {"sucesso": True, **cancelada}


# ---------- visitantes ----------

def listar_meus_visitantes(tool_context: ToolContext) -> dict:
    """Lista os visitantes autorizados para o apartamento do morador desta conversa."""
    return {"visitantes": db.visitantes_do_apartamento(_apartamento(tool_context))}


def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante no prédio na data informada. Exige confirmação.

    Args:
        nome: nome completo do visitante.
        data: data da visita no formato AAAA-MM-DD.
    """
    if erro := _valida(None, data):
        return erro
    nome = nome.strip()
    if not nome:
        return {"erro": "Informe o nome do visitante."}
    return {"sucesso": True, "nome": nome, "data": data,
            **db.autorizar_visitante(_apartamento(tool_context), nome, data)}


# ---------- regulamento ----------

def consultar_regulamento(consulta: str) -> dict:
    """Busca no regulamento interno os artigos relevantes para a dúvida do morador.

    Args:
        consulta: a dúvida em poucas palavras, ex.: "horário da piscina aos domingos".
    """
    return regulamento.consultar(consulta)
