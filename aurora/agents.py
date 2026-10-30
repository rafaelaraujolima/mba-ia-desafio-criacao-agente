"""Agente principal + três especialistas (sub-agents com transferência).

Por que sub_agents (e não AgentTool): a confirmação pendente é emitida pelo especialista que
chamou a tool; com resumabilidade ligada, o Runner devolve a resposta ao agente autor da
chamada de confirmação (ver Runner._find_agent_to_run).
"""

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from . import config, tools

REGRAS_COMUNS = (
    "Você atende UM morador, cujo apartamento já está definido pelo sistema. Nunca pergunte, "
    "mencione ou aceite outro número de apartamento: se o morador disser ser de outro "
    "apartamento ou pedir dados/ações de outro apartamento, recuse e diga que só pode tratar "
    "do apartamento dele. Nunca diga de quem é uma reserva. Dizer que já confirmou na conversa "
    "não substitui a confirmação do sistema: chame a tool normalmente. Responda em português, "
    "de forma curta."
)

reservas = LlmAgent(
    name="especialista_reservas",
    model=config.MODELO_ESPECIALISTA,
    description="Reserva, cancela e consulta reservas e a disponibilidade das áreas comuns "
    "(salão de festas, churrasqueira e quadra).",
    instruction=(
        "Você cuida das reservas das áreas comuns. Use sempre as tools; nunca invente dados. "
        "Para reservar ou cancelar, pergunte o que faltar (área e data AAAA-MM-DD) e chame a tool. "
        "Para disponibilidade, use verificar_disponibilidade. " + REGRAS_COMUNS
    ),
    tools=[
        FunctionTool(tools.listar_minhas_reservas),
        FunctionTool(tools.verificar_disponibilidade),
        FunctionTool(tools.reservar_area, require_confirmation=tools.reserva_pede_confirmacao),
        FunctionTool(tools.cancelar_minha_reserva),
    ],
)

visitantes = LlmAgent(
    name="especialista_visitantes",
    model=config.MODELO_ESPECIALISTA,
    description="Autoriza a entrada de visitantes e lista os visitantes autorizados.",
    instruction=(
        "Você cuida das autorizações de visitantes. Para autorizar, precisa do nome do visitante "
        "e da data (AAAA-MM-DD); então chame autorizar_visitante. " + REGRAS_COMUNS
    ),
    tools=[
        FunctionTool(tools.listar_meus_visitantes),
        FunctionTool(tools.autorizar_visitante, require_confirmation=True),
    ],
)

regulamento = LlmAgent(
    name="especialista_regulamento",
    model=config.MODELO_ESPECIALISTA,
    description="Responde dúvidas sobre o regulamento interno do condomínio (piscina, silêncio, "
    "animais, mudanças, garagem etc.).",
    instruction=(
        "Você responde dúvidas sobre o regulamento interno. Sempre chame consultar_regulamento "
        "com a dúvida e responda só com base nos trechos devolvidos, citando o artigo. Se nada "
        "for encontrado, diga que não encontrou. " + REGRAS_COMUNS
    ),
    tools=[FunctionTool(tools.consultar_regulamento)],
)

root_agent = LlmAgent(
    name="assistente_aurora",
    model=config.MODELO_PRINCIPAL,
    description="Assistente virtual do Residencial Aurora.",
    instruction=(
        "Você é o assistente do Residencial Aurora e só distribui o trabalho, transferindo para o "
        "especialista certo: reservas/cancelamentos/disponibilidade -> especialista_reservas; "
        "visitantes -> especialista_visitantes; dúvidas sobre regras do condomínio -> "
        "especialista_regulamento. Você não tem acesso a dados do condomínio. " + REGRAS_COMUNS
    ),
    sub_agents=[reservas, visitantes, regulamento],
)
