"""Janela de execução: mostra a saída de um comando e transforma as perguntas dele em botões."""

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

from . import estado
from .atalho import NOME_APP, caminho_icone, criar_atalho, criar_icone, raiz_do_projeto, scripts_do_venv
from .execucao import Execucao, LeitorAnsi, Pergunta, opcoes_numeradas, texto_sem_ansi

from .componentes import (  # noqa: F401 - cores, fontes e peças das telas
    ATENCAO,
    ATENCAO_CLARO,
    BORDA,
    Botao,
    CARTAO,
    COMO_EXPORTAR_LINKEDIN,
    DESTAQUE,
    DESTAQUE_CLARO,
    DESTAQUE_ESCURO,
    FONTE,
    FUNDO,
    F_NEGRITO,
    F_NORMAL,
    F_NUMERO,
    F_PEQUENA,
    F_SAIDA,
    F_SUBTITULO,
    F_TITULO,
    Formulario,
    LATERAL,
    LATERAL_ATIVO,
    LATERAL_TEXTO,
    MOTIVOS_SEM_INTERESSE,
    PERIGO,
    SUAVE,
    TEXTO,
    URL_EXPORTACAO_LINKEDIN,
    area_rolavel,
    cartao,
    escolher,
    perguntar,
    rotulo,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # só para a anotação de tipo
    from .janela import App

ESPERA_PARAR_MS = 15_000  # depois do pedido de parar, quanto esperar antes de encerrar a tarefa à força


# ---------------------------------------------------------------- janela de execução

class JanelaExecucao(tk.Toplevel):
    """Mostra a saída de um comando e transforma as perguntas dele em botões e campos."""

    def __init__(self, app: "App", titulo: str, args: list[str] | list[list[str]],
                 ao_fim: Callable[[int], None] | None = None) -> None:
        super().__init__(app.raiz)
        self.app, self.ao_fim, self.titulo = app, ao_fim, titulo
        # Um comando, ou vários em sequência na mesma janela (ex.: uma busca por área).
        self._comandos = [list(c) for c in args] if args and isinstance(args[0], list) else [list(args)]
        self._pior = 0
        self.title(f"{titulo} — {NOME_APP}")
        self.configure(bg=FUNDO)
        self.geometry("1000x660")
        self.minsize(760, 480)
        self.transient(app.raiz)
        self._fila: queue.Queue = queue.Queue()
        self._ansi = LeitorAnsi()
        self._pergunta: Pergunta | None = None
        self._rodando = True
        self._parando = False
        self._giro = 0
        self._trava_entrada = threading.Lock()  # a janela e a linha de leitura escrevem na entrada do processo

        topo = tk.Frame(self, bg=FUNDO, padx=20, pady=14)
        topo.pack(fill="x")
        rotulo(topo, titulo, F_SUBTITULO).pack(side="left")
        self._status = rotulo(topo, "Trabalhando…", F_NEGRITO, SUAVE)
        self._status.pack(side="right")

        corpo = tk.Frame(self, bg=CARTAO, highlightthickness=1, highlightbackground=BORDA)
        corpo.pack(fill="both", expand=True, padx=20)
        self._texto = tk.Text(corpo, font=F_SAIDA, wrap="none", bg=CARTAO, fg=TEXTO, relief="flat", padx=12, pady=10,
                              state="disabled", cursor="arrow")
        rolagem_v = ttk.Scrollbar(corpo, orient="vertical", command=self._texto.yview)
        rolagem_h = ttk.Scrollbar(corpo, orient="horizontal", command=self._texto.xview)
        self._texto.configure(yscrollcommand=rolagem_v.set, xscrollcommand=rolagem_h.set)
        rolagem_v.pack(side="right", fill="y")
        rolagem_h.pack(side="bottom", fill="x")
        self._texto.pack(fill="both", expand=True)
        self._texto.tag_configure("negrito", font=(*F_SAIDA, "bold"))

        self._area_pergunta = tk.Frame(self, bg=ATENCAO_CLARO, padx=20, pady=12, highlightthickness=1,
                                       highlightbackground="#f5d9a8")
        rodape = tk.Frame(self, bg=FUNDO, padx=20, pady=12)
        rodape.pack(fill="x", side="bottom")
        self._rodape = rodape
        Botao(rodape, "Abrir pasta de arquivos", app.abrir_pasta_dados, "link").pack(side="left")
        self._fechar = Botao(rodape, "Aguarde…", self._ao_fechar, "secundario")
        self._fechar.pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        self._iniciar_proximo()
        self.after(40, self._processar)
        self.after(200, self._animar)

    @property
    def rodando(self) -> bool:
        return self._rodando

    def _iniciar_proximo(self) -> None:
        """Cada comando roda num processo próprio: várias janelas do app trabalham ao mesmo tempo."""
        import subprocess

        args = self._comandos.pop(0)
        venv = scripts_do_venv() / ("python.exe" if sys.platform == "win32" else "python")
        python = str(venv) if venv.is_file() else sys.executable
        ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self._processo = subprocess.Popen(
            [python, "-m", "agente_carreira.app.filho", *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=raiz_do_projeto(), env=ambiente, text=True, encoding="utf-8",
            errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._ler_processo, args=(self._processo,), daemon=True).start()

    def _ler_processo(self, processo) -> None:
        """Lê a saída do processo; linhas de controle viram perguntas, cuja resposta volta pela entrada dele."""
        import json

        from .filho import MARCA

        for linha in iter(processo.stdout.readline, ""):
            if MARCA not in linha:
                self._fila.put(("texto", linha))
                continue
            antes, _, controle = linha.partition(MARCA)
            if antes:
                self._fila.put(("texto", antes))
            if not controle.startswith("PERGUNTA "):
                continue
            dados = json.loads(controle[len("PERGUNTA "):])
            pergunta = Pergunta(texto=dados["texto"], tipo=dados["tipo"], padrao=dados["padrao"],
                                opcoes=[tuple(o) for o in dados["opcoes"]])
            self._fila.put(("pergunta", pergunta))
            pergunta.pronta.wait()
            resposta = {"cancelar": True} if pergunta.cancelada else {"valor": pergunta.resposta}
            self._enviar(processo, json.dumps(resposta, ensure_ascii=False))
        codigo = processo.wait()
        self._fila.put(("fim", 130 if getattr(self, "_parado", False) else codigo))

    def _enviar(self, processo, linha: str) -> None:
        with self._trava_entrada:
            try:
                processo.stdin.write(linha + "\n")
                processo.stdin.flush()
            except (OSError, ValueError):
                pass  # o processo já terminou

    def parar(self) -> None:
        """Pede à tarefa que pare com calma (fecha o navegador e não deixa arquivo pela metade).

        Se ela não parar em 15 segundos (ex.: no meio de uma pausa longa), é encerrada à força.
        """
        from .filho import PEDIDO_PARAR

        processo = getattr(self, "_processo", None)
        if not self._rodando or self._parando:
            return
        self._parando = self._parado = True
        self._comandos.clear()
        self._status.configure(text="Parando com segurança…", fg=ATENCAO)
        self._fechar.configure(text="Parando…")
        pergunta, self._pergunta = self._pergunta, None
        self._area_pergunta.pack_forget()
        if processo is not None and processo.poll() is None:
            self._enviar(processo, PEDIDO_PARAR)
        if pergunta is not None:
            pergunta.cancelar()
        self.after(ESPERA_PARAR_MS, self._forcar_parada)

    def _forcar_parada(self) -> None:
        processo = getattr(self, "_processo", None)
        if processo is not None and processo.poll() is None:
            processo.terminate()

    # -- saída
    def _escrever(self, texto: str) -> None:
        self._recente = (getattr(self, "_recente", "") + texto_sem_ansi(texto))[-4000:]
        self._texto.configure(state="normal")
        for trecho, estilos in self._ansi.ler(texto):
            for estilo in estilos:
                if estilo.startswith("cor"):
                    self._texto.tag_configure(estilo, foreground=estilo[3:])
            self._texto.insert("end", trecho, estilos)
        self._texto.configure(state="disabled")
        self._texto.see("end")

    def _processar(self) -> None:
        try:
            while True:
                tipo, valor = self._fila.get_nowait()
                if tipo == "texto":
                    self._escrever(valor)
                elif tipo == "pergunta":
                    self._mostrar_pergunta(valor)
                elif tipo == "fim":
                    self._terminar(valor)
        except queue.Empty:
            pass
        if self.winfo_exists() and (self._rodando or not self._fila.empty()):
            self.after(40, self._processar)

    def _animar(self) -> None:
        if not self._rodando or not self.winfo_exists():
            return
        if self._pergunta is None and not self._parando:
            self._giro = (self._giro + 1) % 4
            self._status.configure(text="Trabalhando" + "." * self._giro, fg=SUAVE)
        self.after(350, self._animar)

    # -- perguntas
    def _mostrar_pergunta(self, pergunta: Pergunta) -> None:
        self._pergunta = pergunta
        self._status.configure(text="Precisa da sua resposta", fg=ATENCAO)
        self._fechar.configure(text="Cancelar")
        area = self._area_pergunta
        for filho in area.winfo_children():
            filho.destroy()
        area.pack(fill="x", padx=20, pady=(10, 0), before=self._rodape)
        rotulo(area, pergunta.texto, F_NEGRITO, TEXTO, bg=ATENCAO_CLARO, wraplength=900).pack(anchor="w")
        botoes = tk.Frame(area, bg=ATENCAO_CLARO)
        botoes.pack(fill="x", pady=(8, 0))
        if pergunta.tipo == "sim_nao":
            sim = Botao(botoes, "Sim", lambda: self._responder(True), "primario" if pergunta.padrao == "sim" else "secundario")
            nao = Botao(botoes, "Não", lambda: self._responder(False), "primario" if pergunta.padrao != "sim" else "secundario")
            sim.pack(side="left")
            nao.pack(side="left", padx=8)
            self.bind("<Return>", lambda _e: self._responder(pergunta.padrao == "sim"))
        elif pergunta.tipo == "opcoes":
            for i, (valor, nome) in enumerate(pergunta.opcoes):
                Botao(botoes, nome, lambda v=valor: self._responder(v), "primario" if i == 0 else "secundario").pack(
                    side="left", padx=(0, 8))
        elif (numeradas := self._lista_numerada(pergunta)):
            # "Motivo (número)" logo depois de uma lista: cada item vira um botão.
            for i, (valor, nome) in enumerate(numeradas):
                tipo = "primario" if valor == pergunta.padrao else "secundario"
                Botao(botoes, nome, lambda v=valor: self._responder(v), tipo, padx=12, pady=5).grid(
                    row=i // 4, column=i % 4, sticky="ew", padx=(0, 8), pady=(0, 6))
            if pergunta.padrao == "":
                Botao(botoes, "Nenhum", lambda: self._responder(""), "link").grid(
                    row=len(numeradas) // 4 + 1, column=0, sticky="w")
        else:
            var = tk.StringVar(value=pergunta.padrao or "")
            campo = ttk.Entry(botoes, textvariable=var, font=F_NORMAL, width=70)
            campo.pack(side="left", ipady=4)
            campo.focus_set()
            campo.select_range(0, "end")
            Botao(botoes, "Continuar", lambda: self._responder(var.get()), "primario").pack(side="left", padx=8)
            Botao(botoes, "Deixar em branco", lambda: self._responder("")).pack(side="left")
            self.bind("<Return>", lambda _e: self._responder(var.get()))
        self.lift()
        self.focus_force()

    def _lista_numerada(self, pergunta: Pergunta) -> list[tuple[str, str]]:
        texto = pergunta.texto.lower()
        if "número" not in texto or "vírgula" in texto:  # escolha múltipla continua no campo de texto
            return []
        return opcoes_numeradas(getattr(self, "_recente", "").splitlines()[-30:])

    def _responder(self, valor) -> None:
        pergunta, self._pergunta = self._pergunta, None
        self.unbind("<Return>")
        self._area_pergunta.pack_forget()
        self._fechar.configure(text="Aguarde…")
        self._status.configure(text="Trabalhando…", fg=SUAVE)
        if pergunta is not None:
            exibicao = "Sim" if valor is True else "Não" if valor is False else (valor if valor != "" else "(em branco)")
            self._escrever(f"\x1b[36m→ {exibicao}\x1b[0m\n")
            pergunta.responder(valor)

    # -- fim
    def _terminar(self, codigo: int) -> None:
        self._pior = self._pior or codigo
        if self._comandos and codigo != 130:  # cancelar para a sequência inteira
            self._escrever("\n")
            self._iniciar_proximo()
            return
        codigo = self._pior
        self._rodando = False
        self._area_pergunta.pack_forget()
        textos = {0: ("Pronto ✓", DESTAQUE), 130: ("Cancelado", SUAVE)}
        texto, cor = textos.get(codigo, ("Terminou com aviso — leia acima", ATENCAO if codigo == 1 else PERIGO))
        self._status.configure(text=texto, fg=cor)
        self._fechar.configure(text="Fechar")
        if self.ao_fim:
            self.ao_fim(codigo)

    def _ao_fechar(self) -> None:
        if not self._rodando:
            self.destroy()
            return
        if self._parando:
            return
        texto = ("Cancelar esta tarefa? O que já foi feito fica salvo." if self._pergunta is not None else
                 "Ainda trabalhando. Parar esta tarefa agora? O que já foi feito fica salvo.")
        if messagebox.askyesno(NOME_APP, texto, parent=self):
            self.parar()
