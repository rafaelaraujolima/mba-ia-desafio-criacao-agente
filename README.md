# Assistente virtual do Residencial Aurora

API (FastAPI) sobre Google ADK 2.2.0 em que o modelo conduz a conversa e o **código** decide o que é permitido. O enunciado original está em [task.md](task.md).

## Arquitetura

Agente principal com três especialistas, ligados por `sub_agents` (transferência) em [aurora/agents.py](aurora/agents.py):

| Agente | Responsabilidade | Tools |
|---|---|---|
| `assistente_aurora` (principal) | Só distribui o trabalho. Não tem tools nem o regulamento nas instruções. | — |
| `especialista_reservas` | Reservar, cancelar, listar e checar disponibilidade | `reservar_area`, `cancelar_minha_reserva`, `listar_minhas_reservas`, `verificar_disponibilidade` |
| `especialista_visitantes` | Autorizar e listar visitantes | `autorizar_visitante`, `listar_meus_visitantes` |
| `especialista_regulamento` | Responder dúvidas do regulamento | `consultar_regulamento` |

**Por que `sub_agents` e não `AgentTool`:** o pedido de confirmação é emitido pelo especialista que chamou a tool. Com `ResumabilityConfig(is_resumable=True)`, o Runner entrega a resposta ao agente autor da chamada (`Runner._find_agent_to_run`), o que funciona também com sessão persistida em SQLite. **Por que três especialistas:** cada um tem um conjunto pequeno de tools e um contexto próprio, e o regulamento fica isolado em um agente que só o consulta sob demanda.

Armazenamento: `estado/condominio.db` (reservas e visitantes) e `estado/sessoes.db` (sessões do ADK), ambos SQLite e fora do Git. `dados/` é só leitura e serve de estado inicial.

## Garantias

1. **Confirmação (G1)**
   - [aurora/agents.py](aurora/agents.py): `FunctionTool(..., require_confirmation=...)`. A reserva usa [`reserva_pede_confirmacao`](aurora/tools.py), que consulta a taxa da área (taxa 0 não pede). `autorizar_visitante` usa `require_confirmation=True`. O cancelamento não pede.
   - [aurora/api.py](aurora/api.py): `responder_confirmacao` só aceita ids de `adk_request_confirmation` ainda sem resposta nos eventos persistidos (senão 409) e envia um `FunctionResponse` com o `invocation_id` original. Texto do morador nunca confirma nada.
2. **Isolamento por apartamento (G2)**
   - [aurora/tools.py](aurora/tools.py): todas as tools leem `tool_context.state["apartamento"]` (definido em `POST /sessoes`); nenhuma tem parâmetro de apartamento.
   - `verificar_disponibilidade` devolve só `disponivel: true/false`; cancelar procura apenas reservas do próprio apartamento.
3. **Persistência (G3)**
   - [aurora/api.py](aurora/api.py): `DatabaseSessionService` sobre SQLite; dados em [aurora/db.py](aurora/db.py).
   - Códigos de reserva vêm da tabela `sequencia_codigo` (AUTOINCREMENT) e cancelar só muda o status, então nunca se repetem.
4. **Regulamento consultado (G4)**
   - [aurora/regulamento.py](aurora/regulamento.py): `consultar` escolhe um capítulo e devolve no máximo 4 artigos dele. O texto completo nunca entra em instruções nem eventos.
5. **Concorrência (G5)**
   - [aurora/db.py](aurora/db.py): índice único parcial `ux_reserva_ativa (area, data) WHERE status='ativa'`. `criar_reserva` faz o INSERT e trata `IntegrityError` como recusa normal (`data_ocupada`), sem checagem prévia.

## Como rodar

Pré-requisitos: [uv](https://docs.astral.sh/uv/) e Python >= 3.12.

```bash
cp .env.example .env        # preencha GOOGLE_API_KEY (chave do Google AI Studio)
uv sync
uv run python -m aurora restaurar   # restaura reservas e visitantes ao estado de dados/
uv run python -m aurora             # sobe a API em http://localhost:8000
```

Variáveis do `.env`: `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI` (deixe `FALSE`), `AURORA_MODELO_PRINCIPAL` e `AURORA_MODELO_ESPECIALISTA` (padrão `gemini-2.5-flash`), `AURORA_ESTADO_DIR` (padrão `./estado`).

O comando `restaurar` não apaga as sessões. Para zerar tudo, apague a pasta `estado/`.
