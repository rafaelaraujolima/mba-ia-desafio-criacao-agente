"""API FastAPI sobre Runner + App do ADK, com sessões persistidas em SQLite."""

import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from google.adk.apps import App, ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from pydantic import BaseModel

from . import config, db
from .agents import root_agent

APP_NAME = "aurora"
CONFIRMACAO = "adk_request_confirmation"


class NovaSessao(BaseModel):
    apartamento: str


class NovaMensagem(BaseModel):
    texto: str


class RespostaConfirmacao(BaseModel):
    id: str
    confirmado: bool


_locks: dict[str, asyncio.Lock] = {}


def _lock(session_id: str) -> asyncio.Lock:
    return _locks.setdefault(session_id, asyncio.Lock())


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.inicializar()
    config.ESTADO_DIR.mkdir(parents=True, exist_ok=True)
    app.state.sessions = DatabaseSessionService(
        db_url=f"sqlite+aiosqlite:///{config.DB_SESSOES.as_posix()}"
    )
    adk_app = App(
        name=APP_NAME,
        root_agent=root_agent,
        # Necessário para que a resposta da confirmação volte ao agente que a pediu.
        resumability_config=ResumabilityConfig(is_resumable=True),
    )
    app.state.runner = Runner(app=adk_app, session_service=app.state.sessions)
    yield


app = FastAPI(title="Assistente Residencial Aurora", lifespan=lifespan)


async def _sessao_ou_404(session_id: str):
    sessao = await app.state.sessions.get_session(
        app_name=APP_NAME, user_id=_user_id_de(session_id), session_id=session_id
    )
    if sessao is None:
        raise HTTPException(404, "Sessão não encontrada")
    return sessao


def _user_id_de(session_id: str) -> str:
    # O user_id é gravado dentro do id da sessão para localizá-la sem índice extra.
    return session_id.split(".", 1)[0] if "." in session_id else ""


def _confirmacoes(sessao) -> tuple[dict[str, dict], set[str]]:
    """Pedidos de confirmação da sessão e os já respondidos (lidos dos eventos persistidos)."""
    pedidos: dict[str, dict] = {}
    respondidos: set[str] = set()
    for ev in sessao.events:
        for fc in ev.get_function_calls():
            if fc.name == CONFIRMACAO:
                original = (fc.args or {}).get("originalFunctionCall", {})
                pedidos[fc.id] = {
                    "id": fc.id,
                    "acao": original.get("name", ""),
                    "detalhes": original.get("args", {}),
                    "_invocation_id": ev.invocation_id,
                }
        for fr in ev.get_function_responses():
            if fr.name == CONFIRMACAO:
                respondidos.add(fr.id)
    return pedidos, respondidos


def _pendentes(sessao) -> list[dict]:
    pedidos, respondidos = _confirmacoes(sessao)
    return [
        {k: v for k, v in p.items() if not k.startswith("_")}
        for i, p in pedidos.items()
        if i not in respondidos
    ]


async def _executar(sessao, content: types.Content, invocation_id: str | None = None) -> dict:
    textos: list[str] = []
    async for ev in app.state.runner.run_async(
        user_id=sessao.user_id,
        session_id=sessao.id,
        new_message=content,
        invocation_id=invocation_id,
    ):
        if ev.partial or ev.author == "user" or not ev.is_final_response():
            continue
        if ev.content and ev.content.parts:
            textos.extend(p.text for p in ev.content.parts if p.text and not p.thought)
    atual = await app.state.sessions.get_session(
        app_name=APP_NAME, user_id=sessao.user_id, session_id=sessao.id
    )
    return {"resposta": "\n".join(textos).strip(), "confirmacoes_pendentes": _pendentes(atual)}


@app.post("/sessoes", status_code=201)
async def criar_sessao(corpo: NovaSessao):
    user_id = f"apto-{corpo.apartamento}"
    session_id = f"{user_id}.{uuid.uuid4().hex}"
    await app.state.sessions.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={"apartamento": corpo.apartamento},
    )
    return {"session_id": session_id}


@app.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(session_id: str, corpo: NovaMensagem):
    sessao = await _sessao_ou_404(session_id)
    async with _lock(session_id):
        content = types.Content(role="user", parts=[types.Part(text=corpo.texto)])
        return await _executar(sessao, content)


@app.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(session_id: str, corpo: RespostaConfirmacao):
    async with _lock(session_id):
        sessao = await _sessao_ou_404(session_id)
        pedidos, respondidos = _confirmacoes(sessao)
        if corpo.id not in pedidos or corpo.id in respondidos:
            raise HTTPException(409, "Não há confirmação pendente com esse id nesta sessão")
        content = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=corpo.id,
                        name=CONFIRMACAO,
                        response={"confirmed": corpo.confirmado},
                    )
                )
            ],
        )
        return await _executar(sessao, content, pedidos[corpo.id]["_invocation_id"])


@app.get("/sessoes/{session_id}/eventos")
async def eventos(session_id: str):
    sessao = await _sessao_ou_404(session_id)
    return [ev.model_dump(mode="json", exclude_none=True) for ev in sessao.events]


@app.get("/apartamentos/{numero}/reservas")
async def reservas(numero: str):
    return db.reservas_do_apartamento(numero)


@app.get("/apartamentos/{numero}/visitantes")
async def visitantes(numero: str):
    return db.visitantes_do_apartamento(numero)
