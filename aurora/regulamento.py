"""Consulta ao regulamento: devolve só os artigos relevantes de um único capítulo.

O texto completo nunca vai para o modelo nem para os eventos da sessão.
"""

import re
import unicodedata
from functools import lru_cache

from . import config

MAX_ARTIGOS = 4
_STOP = {
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "uma", "que", "qual",
    "quais", "para", "por", "com", "ate", "ou", "aos", "sao", "ser", "pode", "posso", "tem",
    "como", "quando", "horas", "hora", "voce",
}


def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFD", txt.lower())
    return "".join(c for c in txt if unicodedata.category(c) != "Mn")


def _tokens(txt: str) -> set[str]:
    # Radical simples de 5 letras (domingo/domingos, funciona/funcionamento).
    return {t[:5] for t in re.findall(r"[a-z0-9]+", _norm(txt)) if len(t) > 2 and t not in _STOP}


@lru_cache(maxsize=1)
def _capitulos() -> list[tuple[str, list[str]]]:
    texto = (config.DADOS_DIR / "regulamento.md").read_text(encoding="utf-8")
    capitulos = []
    for bloco in re.split(r"(?m)^## ", texto)[1:]:
        titulo, _, corpo = bloco.partition("\n")
        artigos = [a.strip() for a in re.split(r"(?m)^(?=\*\*Art\. )", corpo) if a.strip()]
        capitulos.append((titulo.strip(), artigos))
    return capitulos


def consultar(consulta: str) -> dict:
    alvo = _tokens(consulta)
    if not alvo:
        return {"encontrado": False, "mensagem": "Consulta vazia."}

    def pontos(txt: str, peso: int = 1) -> int:
        return len(alvo & _tokens(txt)) * peso

    melhor = None  # (total, titulo, [(pontos_do_artigo, artigo)])
    for titulo, artigos in _capitulos():
        pontuados = sorted(((pontos(a), a) for a in artigos), key=lambda x: -x[0])
        total = pontos(titulo, 3) + sum(p for p, _ in pontuados[:MAX_ARTIGOS])
        if melhor is None or total > melhor[0]:
            melhor = (total, titulo, pontuados)
    if melhor is None or melhor[0] == 0:
        return {"encontrado": False, "mensagem": "Nada encontrado no regulamento sobre isso."}
    _, titulo, pontuados = melhor
    trechos = [a for p, a in pontuados[:MAX_ARTIGOS] if p > 0]
    return {"encontrado": True, "capitulo": titulo, "trechos": trechos}
