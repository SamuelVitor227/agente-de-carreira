"""Processo filho de uma janela de execução do app: roda 'agente ARGS' e conversa com a janela por linhas.

Cada janela do app tem o seu processo, então várias tarefas rodam ao mesmo tempo (busca, candidatura,
e-mail...). A saída vai para a janela como texto; cada pergunta vira uma linha de controle (começa com
MARCA) e a resposta volta pela entrada padrão como JSON.

A janela também pode mandar {"parar": true}: a tarefa é interrompida com calma (o navegador fecha as abas
dela e nenhum arquivo fica pela metade), em vez de ser encerrada à força.

Se o app for fechado e a tarefa continuar ("deixar terminando"), a saída passa para
data/app/tarefas-em-segundo-plano.log e as perguntas que aparecerem depois são canceladas.

Uso: python -m agente_carreira.app.filho ARGS...
"""

from __future__ import annotations

import _thread
import json
import queue
import sys
import threading
from datetime import datetime

MARCA = "\x1e"  # separador de registro: nunca aparece no texto normal
PEDIDO_PARAR = json.dumps({"parar": True})
LOG_SEGUNDO_PLANO = "tarefas-em-segundo-plano.log"


def mensagem_pergunta(pergunta) -> str:
    return MARCA + "PERGUNTA " + json.dumps({"texto": pergunta.texto, "tipo": pergunta.tipo, "opcoes": pergunta.opcoes,
                                             "padrao": pergunta.padrao}, ensure_ascii=False) + "\n"


class Canal:
    """O que chega da janela: respostas às perguntas e o pedido de parar.

    Uma linha lê a entrada o tempo todo. "Parar" com uma pergunta aberta cancela a pergunta; sem pergunta,
    interrompe a tarefa onde ela estiver (KeyboardInterrupt), o que fecha o navegador e as travas pelo caminho.
    """

    def __init__(self, entrada, interromper=_thread.interrupt_main) -> None:
        self.respostas: queue.Queue = queue.Queue()
        self.parar = threading.Event()
        self.fechada = threading.Event()
        self._interromper = interromper
        self._trava = threading.Lock()
        self._esperando = False
        threading.Thread(target=self._ler, args=(entrada,), name="canal-da-janela", daemon=True).start()

    def _ler(self, entrada) -> None:
        try:
            for linha in iter(entrada.readline, ""):
                try:
                    dados = json.loads(linha)
                except ValueError:
                    continue
                if not dados.get("parar"):
                    self.respostas.put(dados)
                    continue
                with self._trava:
                    if self.parar.is_set():
                        continue
                    self.parar.set()
                    if self._esperando:
                        self.respostas.put({"cancelar": True})
                    else:
                        self._interromper()
        except (OSError, ValueError):
            pass
        self.fechada.set()

    def esperar_resposta(self) -> dict | None:
        """A resposta da janela; None se a tarefa foi parada ou a janela não existe mais."""
        with self._trava:
            if self.parar.is_set():
                return None
            self._esperando = True
        try:
            while True:
                try:
                    return self.respostas.get(timeout=0.2)
                except queue.Empty:
                    if self.fechada.is_set():
                        return None
        finally:
            with self._trava:
                self._esperando = False


class Saida:
    """A saída da tarefa: para a janela; se a janela sumir (app fechado), para um arquivo de log."""

    def __init__(self, destino, args: list[str]) -> None:
        self._destino = destino
        self._args = args
        self.na_janela = True
        self.ultimo = "\n"

    def _para_o_log(self) -> None:
        from ..storage import diretorio_dados

        caminho = diretorio_dados() / "app" / LOG_SEGUNDO_PLANO
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._destino = open(caminho, "a", encoding="utf-8", errors="replace")  # noqa: SIM115 - até o fim do processo
        self._destino.write(f"\n===== {datetime.now():%d/%m/%Y %H:%M} · agente {' '.join(self._args)} "
                            "(o app foi fechado; a tarefa continuou) =====\n")
        self.na_janela = False

    def escrever(self, texto: str, controle: bool = False) -> bool:
        """Devolve False se a linha de controle (pergunta) não chegou à janela."""
        from .execucao import texto_sem_ansi

        if self.na_janela:
            try:
                self._destino.write(texto)
                self._destino.flush()
                if texto and not controle:
                    self.ultimo = texto[-1]
                return True
            except (OSError, ValueError):
                self._para_o_log()
        if controle:
            return False
        self._destino.write(texto_sem_ansi(texto))
        self._destino.flush()
        return True


def main(argv: list[str] | None = None) -> int:
    from . import preparar_ambiente
    from .execucao import Execucao

    preparar_ambiente()
    args = list(sys.argv[1:] if argv is None else argv)
    destino = sys.__stdout__
    try:
        destino.reconfigure(encoding="utf-8", errors="replace", line_buffering=False)
    except (AttributeError, ValueError):
        pass
    saida = Saida(destino, args)
    canal = Canal(sys.stdin)

    def perguntar(pergunta) -> None:
        if saida.ultimo != "\n":
            saida.escrever("\n")  # a linha de controle começa sempre numa linha nova
        if not saida.escrever(mensagem_pergunta(pergunta), controle=True):
            pergunta.cancelar()  # ninguém para responder
            return
        dados = canal.esperar_resposta()
        if dados is None or dados.get("cancelar"):
            pergunta.cancelar()
        else:
            pergunta.responder(dados.get("valor"))

    execucao = Execucao(args, ao_escrever=saida.escrever, ao_perguntar=perguntar, ao_terminar=lambda codigo: None)
    try:
        return execucao.rodar()
    except KeyboardInterrupt:  # o pedido de parar chegou na hora em que a tarefa já terminava
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
