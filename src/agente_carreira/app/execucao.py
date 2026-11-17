"""Roda os comandos da CLI dentro do app, sem console.

A saída vai para a janela (com as cores do terminal) e cada pergunta da CLI
(typer.prompt, typer.confirm, input) vira uma pergunta na própria janela:
botões de Sim/Não, botões de opção ou um campo de texto. Os fluxos são os
mesmos da CLI, com as mesmas confirmações (RN-01).
"""

from __future__ import annotations

import builtins
import io
import re
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# Uma execução por vez: stdout e as funções de pergunta são trocadas no processo inteiro.
_TRAVA = threading.Lock()

# ---------------------------------------------------------------- perguntas

TipoPergunta = Literal["sim_nao", "opcoes", "texto"]
_OPCAO = re.compile(r"\[(\w)\]([^,\[]*?)(?=\s*,|\s+ou\s+|\s*$)")


def opcoes_da_pergunta(texto: str) -> list[tuple[str, str]]:
    """'[a]provar o kit, [e]ditar a mensagem ou [c]ancelar' → [('a', 'Aprovar o kit'), ...]."""
    opcoes = [(letra, (letra + resto).strip()) for letra, resto in _OPCAO.findall(texto)]
    return [(valor, rotulo[:1].upper() + rotulo[1:]) for valor, rotulo in opcoes] if len(opcoes) >= 2 else []


_ITEM_NUMERADO = re.compile(r"^\s*(\d{1,2})\.\s+(\S.*?)\s*$")


def opcoes_numeradas(linhas: list[str]) -> list[tuple[str, str]]:
    """A lista numerada que acabou de aparecer ('  1. perfil técnico', ...) → [('1', 'Perfil técnico'), ...]."""
    opcoes: list[tuple[str, str]] = []
    for linha in reversed([l for l in linhas if l.strip()]):
        m = _ITEM_NUMERADO.match(linha)
        if not m:
            break
        opcoes.append((m.group(1), m.group(2)[:1].upper() + m.group(2)[1:]))
    opcoes.reverse()
    numeros = [int(v) for v, _ in opcoes]
    return opcoes if len(opcoes) >= 2 and numeros == list(range(numeros[0], numeros[0] + len(numeros))) else []


def texto_sem_ansi(texto: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", texto)


class Cancelado(Exception):
    """A pessoa fechou a janela no meio de uma pergunta."""


@dataclass
class Pergunta:
    texto: str
    tipo: TipoPergunta
    opcoes: list[tuple[str, str]] = field(default_factory=list)
    padrao: str | None = None
    resposta: Any = None
    cancelada: bool = False
    pronta: threading.Event = field(default_factory=threading.Event)

    def responder(self, valor: Any) -> None:
        self.resposta = valor
        self.pronta.set()

    def cancelar(self) -> None:
        self.cancelada = True
        self.pronta.set()


def limpar_texto_pergunta(texto: str) -> str:
    return texto.lstrip("﻿").strip().rstrip(":").strip()


# ---------------------------------------------------------------- cores ANSI → trechos com estilo

CORES_ANSI = {
    30: "#1d1d1b", 31: "#c62828", 32: "#2e7d32", 33: "#a15c00", 34: "#1f5fa8", 35: "#8e44ad", 36: "#00838f", 37: "#5f6368",
    90: "#6b6b66", 91: "#d32f2f", 92: "#388e3c", 93: "#b26a00", 94: "#1e66c8", 95: "#9c27b0", 96: "#0097a7", 97: "#3c4043",
}
_ESC = re.compile(r"\x1b\[([0-9;]*)m")


def _cor_256(n: int) -> str | None:
    if n < 8:
        return CORES_ANSI[30 + n]
    if n < 16:
        return CORES_ANSI[90 + n - 8]
    if n < 232:
        n -= 16
        r, g, b = (n // 36) % 6, (n // 6) % 6, n % 6
        return "#%02x%02x%02x" % tuple(0 if c == 0 else 55 + 40 * c for c in (r, g, b))
    cinza = 8 + 10 * (n - 232)
    return "#%02x%02x%02x" % (cinza, cinza, cinza)


class LeitorAnsi:
    """Divide o texto em (trecho, estilos), guardando o estilo entre um pedaço e outro."""

    def __init__(self) -> None:
        self.negrito = False
        self.cor: str | None = None
        self._resto = ""

    def _aplicar(self, codigos: str) -> None:
        partes = [int(p) for p in codigos.split(";") if p.isdigit()] or [0]
        i = 0
        while i < len(partes):
            c = partes[i]
            if c == 0:
                self.negrito, self.cor = False, None
            elif c == 1:
                self.negrito = True
            elif c == 22:
                self.negrito = False
            elif c == 39:
                self.cor = None
            elif c in CORES_ANSI:
                self.cor = CORES_ANSI[c]
            elif c == 38 and i + 2 < len(partes) and partes[i + 1] == 5:
                self.cor = _cor_256(partes[i + 2])
                i += 2
            elif c == 38 and i + 4 < len(partes) and partes[i + 1] == 2:
                self.cor = "#%02x%02x%02x" % tuple(min(255, v) for v in partes[i + 2:i + 5])
                i += 4
            elif c in (48,) and i + 1 < len(partes):  # cor de fundo: ignorada (pula os parâmetros)
                i += 2 if partes[i + 1] == 5 else 4 if partes[i + 1] == 2 else 0
            i += 1

    def _estilos(self) -> tuple[str, ...]:
        estilos = []
        if self.negrito:
            estilos.append("negrito")
        if self.cor:
            estilos.append("cor" + self.cor)
        return tuple(estilos)

    def ler(self, texto: str) -> list[tuple[str, tuple[str, ...]]]:
        texto = self._resto + texto
        self._resto = ""
        corte = texto.rfind("\x1b")
        if corte != -1 and "m" not in texto[corte:]:  # sequência partida no fim: espera o próximo pedaço
            texto, self._resto = texto[:corte], texto[corte:]
        trechos: list[tuple[str, tuple[str, ...]]] = []
        posicao = 0
        for m in _ESC.finditer(texto):
            if m.start() > posicao:
                trechos.append((texto[posicao:m.start()], self._estilos()))
            self._aplicar(m.group(1))
            posicao = m.end()
        if posicao < len(texto):
            trechos.append((texto[posicao:], self._estilos()))
        return [(t, e) for t, e in trechos if t]


# ---------------------------------------------------------------- execução

class _Saida(io.TextIOBase):
    def __init__(self, destino: Callable[[str], None]) -> None:
        self._destino = destino

    def writable(self) -> bool:
        return True

    def write(self, texto: str) -> int:
        if texto:
            self._destino(texto)
        return len(texto)

    def isatty(self) -> bool:  # o rich decide as cores por FORCE_COLOR, não por aqui
        return False


class Execucao:
    """Roda 'agente ARGS' numa thread. Os callbacks são chamados nessa thread: a janela deve repassá-los à thread da interface."""

    def __init__(self, args: list[str], *, ao_escrever: Callable[[str], None],
                 ao_perguntar: Callable[[Pergunta], None], ao_terminar: Callable[[int], None]) -> None:
        self.args = list(args)
        self.ao_escrever = ao_escrever
        self.ao_perguntar = ao_perguntar
        self.ao_terminar = ao_terminar
        self.pergunta_aberta: Pergunta | None = None
        self.codigo: int | None = None

    # -- perguntas (rodam na thread da execução e esperam a resposta da janela)
    def _perguntar(self, pergunta: Pergunta) -> Any:
        self.pergunta_aberta = pergunta
        self.ao_perguntar(pergunta)
        pergunta.pronta.wait()
        self.pergunta_aberta = None
        if pergunta.cancelada:
            raise Cancelado()
        return pergunta.resposta

    def prompt(self, text: str, default: Any = None, *args: Any, type: Any = None, value_proc: Any = None,
               show_default: bool = True, **kwargs: Any) -> Any:
        texto = limpar_texto_pergunta(text)
        opcoes = opcoes_da_pergunta(texto)
        padrao = None if default is None else str(default)
        while True:
            resposta = self._perguntar(Pergunta(texto=texto, tipo="opcoes" if opcoes else "texto", opcoes=opcoes,
                                                padrao=padrao))
            resposta = "" if resposta is None else str(resposta)
            if resposta == "" and default is not None:
                return default
            if value_proc is not None:
                return value_proc(resposta)
            if type in (int, float):
                try:
                    return type(resposta.replace(",", ".") if type is float else resposta)
                except ValueError:
                    self.ao_escrever("\x1b[31mDigite só números.\x1b[0m\n")
                    continue
            return resposta

    def confirm(self, text: str, default: bool | None = False, abort: bool = False, *args: Any, **kwargs: Any) -> bool:
        resposta = bool(self._perguntar(Pergunta(texto=limpar_texto_pergunta(text), tipo="sim_nao",
                                                 padrao="sim" if default else "nao")))
        if abort and not resposta:
            import typer

            raise typer.Abort()
        return resposta

    def entrada(self, prompt: str = "") -> str:
        texto = limpar_texto_pergunta(str(prompt)) or "Digite (deixe em branco para terminar)"
        return str(self._perguntar(Pergunta(texto=texto, tipo="texto", padrao="")) or "")

    # -- execução
    def iniciar(self) -> threading.Thread:
        linha = threading.Thread(target=self.rodar, name="agente-execucao", daemon=True)
        linha.start()
        return linha

    def rodar(self) -> int:
        import typer
        from typer.main import get_command

        from ..cli import app
        from ..storage import PerfilAusente

        with _TRAVA:
            saida = _Saida(self.ao_escrever)
            antigos = (sys.stdout, sys.stderr, typer.prompt, typer.confirm, builtins.input)
            sys.stdout = sys.stderr = saida
            typer.prompt, typer.confirm, builtins.input = self.prompt, self.confirm, self.entrada
            codigo = 0
            try:
                resultado = get_command(app).main(args=self.args, prog_name="agente", standalone_mode=False)
                codigo = resultado if isinstance(resultado, int) else 0
            except PerfilAusente as erro:
                saida.write(f"\x1b[33m{erro}\x1b[0m\n")
                codigo = 1
            except (Cancelado, KeyboardInterrupt):
                saida.write("\nCancelado. Nada foi feito depois deste ponto.\n")
                codigo = 130
            except SystemExit as fim:
                codigo = fim.code if isinstance(fim.code, int) else 0
            except Exception as erro:  # noqa: BLE001 - o erro aparece na janela em vez de derrubar o app
                if type(erro).__name__ == "Abort":
                    saida.write("\nCancelado.\n")
                    codigo = 130
                elif hasattr(erro, "format_message"):
                    saida.write(f"\x1b[31mErro: {erro.format_message()}\x1b[0m\n")
                    codigo = 2
                else:
                    saida.write(f"\x1b[31mErro inesperado: {type(erro).__name__}: {erro}\x1b[0m\n")
                    codigo = 1
            finally:
                sys.stdout, sys.stderr, typer.prompt, typer.confirm, builtins.input = antigos
        self.codigo = codigo
        self.ao_terminar(codigo)
        return codigo
