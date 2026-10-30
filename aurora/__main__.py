"""Comandos: `python -m aurora` sobe a API; `python -m aurora restaurar` restaura os dados."""

import sys

import uvicorn

from . import config, db


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "restaurar":
        db.restaurar()
        print("Reservas e visitantes restaurados ao estado de dados/.")
        return
    uvicorn.run("aurora.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
