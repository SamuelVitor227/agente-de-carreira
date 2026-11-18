"""Processo filho de uma janela de execução do app: roda 'agente ARGS' e conversa com a janela por linhas.

Cada janela do app tem o seu processo, então várias tarefas rodam ao mesmo tempo (busca, candidatura,
e-mail...). A saída vai para a janela como texto; cada pergunta vira uma linha de controle (começa com
MARCA) e a resposta volta pela entrada padrão como JSON.

Uso: python -m agente_carreira.app.filho ARGS...
"""

from __future__ import annotations

import json
import sys

MARCA = "\x1e"  # separador de registro: nunca aparece no texto normal


def mensagem_pergunta(pergunta) -> str:
    return MARCA + "PERGUNTA " + json.dumps({"texto": pergunta.texto, "tipo": pergunta.tipo, "opcoes": pergunta.opcoes,
                                             "padrao": pergunta.padrao}, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    from . import preparar_ambiente
    from .execucao import Execucao

    preparar_ambiente()
    saida = sys.__stdout__
    try:
        saida.reconfigure(encoding="utf-8", errors="replace", line_buffering=False)
    except (AttributeError, ValueError):
        pass
    ultimo = ["\n"]

    def escrever(texto: str) -> None:
        saida.write(texto)
        saida.flush()
        if texto:
            ultimo[0] = texto[-1]

    def perguntar(pergunta) -> None:
        if ultimo[0] != "\n":
            escrever("\n")  # a linha de controle começa sempre numa linha nova
        saida.write(mensagem_pergunta(pergunta))
        saida.flush()
        resposta = sys.stdin.readline()
        if not resposta:
            pergunta.cancelar()
            return
        dados = json.loads(resposta)
        if dados.get("cancelar"):
            pergunta.cancelar()
        else:
            pergunta.responder(dados.get("valor"))

    execucao = Execucao(list(sys.argv[1:] if argv is None else argv), ao_escrever=escrever, ao_perguntar=perguntar,
                        ao_terminar=lambda codigo: None)
    return execucao.rodar()


if __name__ == "__main__":
    raise SystemExit(main())
