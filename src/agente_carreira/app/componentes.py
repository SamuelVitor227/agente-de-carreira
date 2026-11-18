"""Cores, fontes e peças das telas do app: botão, cartão, rótulo, área com rolagem e formulários."""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .atalho import NOME_APP, caminho_icone, criar_atalho, criar_icone, raiz_do_projeto, scripts_do_venv

# ---------------------------------------------------------------- aparência

FUNDO = "#f4f6f8"
CARTAO = "#ffffff"
BORDA = "#e2e8f0"
TEXTO = "#0f172a"
SUAVE = "#64748b"
LATERAL = "#1e293b"
LATERAL_TEXTO = "#cbd5e1"
LATERAL_ATIVO = "#334155"
DESTAQUE = "#2f7d5b"
DESTAQUE_ESCURO = "#24644a"
DESTAQUE_CLARO = "#e8f3ee"
ATENCAO = "#b45309"
ATENCAO_CLARO = "#fff7e6"
PERIGO = "#b91c1c"

FONTE = "Segoe UI"
F_NORMAL = (FONTE, 10)
F_PEQUENA = (FONTE, 9)
F_NEGRITO = (FONTE, 10, "bold")
F_TITULO = (FONTE, 20, "bold")
F_SUBTITULO = (FONTE, 13, "bold")
F_NUMERO = (FONTE, 24, "bold")
F_SAIDA = ("Consolas", 10)

URL_EXPORTACAO_LINKEDIN = "https://www.linkedin.com/mypreferences/d/download-my-data"
COMO_EXPORTAR_LINKEDIN = (
    "O agente não entra na sua conta do LinkedIn: assim ela não corre risco de bloqueio.\n"
    "Seus dados vêm de um arquivo que o próprio LinkedIn gera:\n\n"
    "1. No LinkedIn, clique em Eu → Configurações e privacidade → Privacidade de dados → "
    "Obter uma cópia dos seus dados.\n"
    "2. Escolha o pacote completo e clique em Solicitar arquivo.\n"
    "3. O LinkedIn manda um link por e-mail (de alguns minutos até 24 horas). Baixe o arquivo .zip.\n\n"
    "Você já tem o arquivo .zip?\n\n"
    "Sim = escolher o arquivo   ·   Não = abrir a página do LinkedIn para pedir"
)
MOTIVOS_SEM_INTERESSE = [
    ("area", "Não é a área ou as tecnologias que quero"), ("requisitos", "Pede coisas que eu não tenho"),
    ("nivel", "O nível não é o meu"), ("modelo", "Modelo de trabalho (presencial/remoto)"),
    ("local", "Local longe demais"), ("salario", "Salário baixo"), ("empresa", "Não gosto da empresa"),
    ("outro", "Outro motivo"),
]


class Botao(tk.Label):
    """Botão plano, com cor de destaque e efeito ao passar o mouse."""

    ESTILOS = {
        "primario": (DESTAQUE, "#ffffff", DESTAQUE_ESCURO),
        "secundario": ("#ffffff", TEXTO, "#eef2f6"),
        "perigo": ("#ffffff", PERIGO, "#fdecec"),
        "link": (None, DESTAQUE, None),
        "lateral": (LATERAL, LATERAL_TEXTO, LATERAL_ATIVO),
    }

    def __init__(self, pai, texto: str, comando: Callable[[], None], tipo: str = "secundario", **kw) -> None:
        fundo, cor, hover = self.ESTILOS[tipo]
        fundo = fundo or pai.cget("bg")
        borda = 1 if tipo in ("secundario", "perigo") else 0
        super().__init__(pai, text=texto, bg=fundo, fg=cor, font=kw.pop("font", F_NEGRITO if tipo != "link" else F_NORMAL),
                         padx=kw.pop("padx", 14), pady=kw.pop("pady", 7), cursor="hand2",
                         highlightthickness=borda, highlightbackground=BORDA, **kw)
        self._fundo, self._hover, self._comando, self._ativo = fundo, hover or fundo, comando, True
        self.bind("<Enter>", lambda _e: self._ativo and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._fundo))
        self.bind("<Button-1>", lambda _e: self._ativo and self._comando())
        if tipo == "link":
            self.configure(font=(FONTE, 10, "underline"))

    def ativar(self, ativo: bool) -> None:
        self._ativo = ativo
        self.configure(fg=self.cget("fg") if ativo else "#a0aec0", cursor="hand2" if ativo else "arrow")

    def fixar(self, fundo: str) -> None:
        self._fundo = fundo
        self.configure(bg=fundo)


def cartao(pai, **kw) -> tk.Frame:
    return tk.Frame(pai, bg=CARTAO, highlightthickness=1, highlightbackground=BORDA, **kw)


def rotulo(pai, texto: str, fonte=F_NORMAL, cor=TEXTO, **kw) -> tk.Label:
    return tk.Label(pai, text=texto, font=fonte, fg=cor, bg=kw.pop("bg", pai.cget("bg")), justify="left", anchor="w", **kw)


def area_rolavel(pai) -> tk.Frame:
    """Frame com rolagem vertical (roda do mouse incluída)."""
    tela = tk.Canvas(pai, bg=FUNDO, highlightthickness=0)
    barra = ttk.Scrollbar(pai, orient="vertical", command=tela.yview)
    interno = tk.Frame(tela, bg=FUNDO)
    janela = tela.create_window((0, 0), window=interno, anchor="nw")
    interno.bind("<Configure>", lambda _e: tela.configure(scrollregion=tela.bbox("all")))
    tela.bind("<Configure>", lambda e: tela.itemconfigure(janela, width=e.width))
    tela.configure(yscrollcommand=barra.set)
    tela.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")

    def rolar(evento):
        if tela.winfo_exists() and interno.winfo_height() > tela.winfo_height():
            tela.yview_scroll(int(-evento.delta / 120), "units")

    tela.bind("<Enter>", lambda _e: tela.bind_all("<MouseWheel>", rolar))
    tela.bind("<Leave>", lambda _e: tela.unbind_all("<MouseWheel>"))
    return interno


# ---------------------------------------------------------------- formulários simples

class Formulario(tk.Toplevel):
    """Campos: (chave, rótulo, tipo, opções, padrão, ajuda). Tipos: texto, escolha, varios, marcar, textolongo."""

    def __init__(self, pai, titulo: str, explicacao: str, campos: list[tuple], botao: str = "Continuar") -> None:
        super().__init__(pai)
        self.title(titulo)
        self.configure(bg=FUNDO, padx=22, pady=18)
        self.transient(pai)
        self.resizable(False, False)
        self.resultado: dict | None = None
        self._leitores: dict[str, Callable[[], object]] = {}
        rotulo(self, titulo, F_SUBTITULO).pack(anchor="w")
        if explicacao:
            rotulo(self, explicacao, F_NORMAL, SUAVE, wraplength=520).pack(anchor="w", pady=(4, 12))
        for chave, texto, tipo, opcoes, padrao, ajuda in campos:
            bloco = tk.Frame(self, bg=FUNDO)
            bloco.pack(fill="x", pady=6)
            if tipo != "marcar":
                rotulo(bloco, texto, F_NEGRITO).pack(anchor="w")
            if tipo in ("texto", "senha"):
                var = tk.StringVar(value=padrao or "")
                ttk.Entry(bloco, textvariable=var, width=60, font=F_NORMAL, show="•" if tipo == "senha" else "").pack(
                    anchor="w", pady=(3, 0), ipady=3)
                self._leitores[chave] = var.get
            elif tipo == "textolongo":
                caixa = tk.Text(bloco, width=62, height=6, font=F_NORMAL, wrap="word", relief="solid", bd=1)
                caixa.insert("1.0", padrao or "")
                caixa.pack(anchor="w", pady=(3, 0))
                self._leitores[chave] = lambda c=caixa: c.get("1.0", "end").strip()
            elif tipo == "escolha":
                var = tk.StringVar(value=padrao if padrao is not None else (opcoes[0][0] if opcoes else ""))
                for valor, nome in opcoes:
                    tk.Radiobutton(bloco, text=nome, value=valor, variable=var, bg=FUNDO, font=F_NORMAL, anchor="w",
                                   activebackground=FUNDO).pack(anchor="w")
                self._leitores[chave] = var.get
            elif tipo in ("varios", "varios_lista"):  # caixas de marcar: na mesma linha ou uma embaixo da outra
                marcados = set(padrao or [])
                variaveis = []
                linha = tk.Frame(bloco, bg=FUNDO)
                linha.pack(anchor="w")
                for valor, nome in opcoes:
                    var = tk.BooleanVar(value=valor in marcados)
                    caixa = tk.Checkbutton(linha, text=nome, variable=var, bg=FUNDO, font=F_NORMAL, anchor="w",
                                           activebackground=FUNDO)
                    if tipo == "varios":
                        caixa.pack(side="left", padx=(0, 10))
                    else:
                        caixa.pack(anchor="w")
                    variaveis.append((valor, var))
                self._leitores[chave] = lambda v=variaveis: [valor for valor, var in v if var.get()]
            elif tipo == "marcar":
                var = tk.BooleanVar(value=bool(padrao))
                tk.Checkbutton(bloco, text=texto, variable=var, bg=FUNDO, font=F_NORMAL,
                               activebackground=FUNDO).pack(anchor="w")
                self._leitores[chave] = var.get
            if ajuda:
                rotulo(bloco, ajuda, F_PEQUENA, SUAVE, wraplength=520).pack(anchor="w", pady=(2, 0))
        botoes = tk.Frame(self, bg=FUNDO)
        botoes.pack(fill="x", pady=(16, 0))
        Botao(botoes, botao, self._ok, "primario").pack(side="right")
        Botao(botoes, "Cancelar", self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_window(self)

    def _ok(self) -> None:
        self.resultado = {chave: ler() for chave, ler in self._leitores.items()}
        self.destroy()


def perguntar(pai, titulo, explicacao, campos, botao="Continuar") -> dict | None:
    return Formulario(pai, titulo, explicacao, campos, botao).resultado


def escolher(pai, titulo: str, explicacao: str, opcoes: list[tuple[str, str, str]]) -> str | None:
    """Janela com uma explicação e um botão por opção (valor, texto, tipo). Devolve o valor (None = fechou)."""
    janela = tk.Toplevel(pai)
    janela.title(NOME_APP)
    janela.configure(bg=FUNDO, padx=24, pady=20)
    janela.transient(pai)
    janela.resizable(False, False)
    escolha: list[str | None] = [None]
    rotulo(janela, titulo, F_SUBTITULO).pack(anchor="w")
    rotulo(janela, explicacao, F_NORMAL, SUAVE, wraplength=480).pack(anchor="w", pady=(6, 16))
    botoes = tk.Frame(janela, bg=FUNDO)
    botoes.pack(fill="x")

    def definir(valor: str) -> None:
        escolha[0] = valor
        janela.destroy()

    for valor, texto, tipo in opcoes:
        Botao(botoes, texto, lambda v=valor: definir(v), tipo).pack(side="left", padx=(0, 8))
    janela.bind("<Escape>", lambda _e: janela.destroy())
    janela.grab_set()
    janela.wait_window(janela)
    return escolha[0]
