"""Interface do app: navegação lateral, telas em linguagem simples e execução sem console."""

from __future__ import annotations

import os
import queue
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from . import estado
from .atalho import NOME_APP, caminho_icone, criar_atalho, criar_icone, raiz_do_projeto, scripts_do_venv
from .execucao import Execucao, LeitorAnsi, Pergunta, opcoes_numeradas, texto_sem_ansi

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


# ---------------------------------------------------------------- janela de execução

class JanelaExecucao(tk.Toplevel):
    """Mostra a saída de um comando e transforma as perguntas dele em botões e campos."""

    def __init__(self, app: "App", titulo: str, args: list[str] | list[list[str]],
                 ao_fim: Callable[[int], None] | None = None) -> None:
        super().__init__(app.raiz)
        self.app, self.ao_fim = app, ao_fim
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
        self._giro = 0

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

    def _iniciar_proximo(self) -> None:
        Execucao(self._comandos.pop(0), ao_escrever=lambda t: self._fila.put(("texto", t)),
                 ao_perguntar=lambda p: self._fila.put(("pergunta", p)),
                 ao_terminar=lambda c: self._fila.put(("fim", c))).iniciar()

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
        if self._pergunta is None:
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
        if self._pergunta is not None:
            if messagebox.askyesno(NOME_APP, "Cancelar esta tarefa? O que já foi feito fica salvo.", parent=self):
                pergunta, self._pergunta = self._pergunta, None
                self._area_pergunta.pack_forget()
                pergunta.cancelar()
            return
        messagebox.showinfo(NOME_APP, "Ainda trabalhando. A janela pode ser fechada quando terminar.", parent=self)


# ---------------------------------------------------------------- app

MENU = [
    ("inicio", "⌂   Início"),
    ("vagas", "★   Vagas"),
    ("candidaturas", "✉   Minhas candidaturas"),
    ("perfil", "☺   Meu perfil e currículo"),
    ("linkedin", "in  LinkedIn"),
    ("aprovacoes", "✓   Aprovações"),
    ("relatorios", "▤   Relatórios"),
    ("config", "⚙   Configurações"),
]


class App:
    def __init__(self) -> None:
        if sys.platform == "win32":
            try:  # texto nítido em telas com escala (125%, 150%...)
                import ctypes

                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:  # noqa: BLE001
                pass
        self.raiz = tk.Tk()
        self.raiz.title(NOME_APP)
        self.raiz.geometry("1180x760")
        self.raiz.minsize(1000, 640)
        self.raiz.configure(bg=FUNDO)
        try:
            icone = caminho_icone()
            if not icone.is_file():
                criar_icone(icone)
            self.raiz.iconbitmap(default=str(icone))
        except Exception:  # noqa: BLE001
            pass
        estilo = ttk.Style(self.raiz)
        estilo.theme_use("clam")
        estilo.configure("Treeview", font=F_NORMAL, rowheight=32, background=CARTAO, fieldbackground=CARTAO,
                         bordercolor=BORDA, borderwidth=0)
        estilo.configure("Treeview.Heading", font=F_NEGRITO, background="#eef2f6", foreground=TEXTO, relief="flat",
                         padding=(8, 6))
        estilo.map("Treeview", background=[("selected", DESTAQUE_CLARO)], foreground=[("selected", TEXTO)])
        estilo.configure("TEntry", padding=4)

        lateral = tk.Frame(self.raiz, bg=LATERAL, width=232)
        lateral.pack(side="left", fill="y")
        lateral.pack_propagate(False)
        rotulo(lateral, "Agente de\nCarreira", (FONTE, 16, "bold"), "#ffffff").pack(anchor="w", padx=22, pady=(24, 22))
        self._itens_menu: dict[str, Botao] = {}
        for chave, texto in MENU:
            item = Botao(lateral, texto, lambda c=chave: self.mostrar(c), "lateral", font=(FONTE, 11), anchor="w",
                         padx=22, pady=10)
            item.pack(fill="x")
            self._itens_menu[chave] = item
        rotulo(lateral, "Nada é enviado nem publicado\nsem o seu sim.", F_PEQUENA, "#94a3b8").pack(
            side="bottom", anchor="w", padx=22, pady=18)

        self.conteudo = tk.Frame(self.raiz, bg=FUNDO)
        self.conteudo.pack(side="left", fill="both", expand=True)
        self.pagina_atual = "inicio"
        self.mostrar("inicio")

    # -- navegação
    def mostrar(self, pagina: str) -> None:
        self.pagina_atual = pagina
        for chave, item in self._itens_menu.items():
            item.fixar(LATERAL_ATIVO if chave == pagina else LATERAL)
            item.configure(fg="#ffffff" if chave == pagina else LATERAL_TEXTO)
        for filho in self.conteudo.winfo_children():
            filho.destroy()
        moldura = tk.Frame(self.conteudo, bg=FUNDO)
        moldura.pack(fill="both", expand=True)
        try:
            getattr(self, f"_pagina_{pagina}")(moldura)
        except Exception as erro:  # noqa: BLE001 - uma tela com problema não derruba o app
            rotulo(moldura, f"Não foi possível abrir esta tela:\n{type(erro).__name__}: {erro}", F_NORMAL, PERIGO,
                   padx=32, pady=32).pack(anchor="w")

    def atualizar(self, _codigo: int | None = None) -> None:
        if self.raiz.winfo_exists():
            self.mostrar(self.pagina_atual)

    def executar(self, titulo: str, args: list[str] | list[list[str]],
                 depois: Callable[[], None] | None = None) -> None:
        """Roda o comando numa janela; `depois` roda só se ele terminar bem (ex.: abrir a pasta gerada)."""
        def ao_fim(codigo: int) -> None:
            self.atualizar()
            if codigo == 0 and depois:
                depois()
        JanelaExecucao(self, titulo, args, ao_fim=ao_fim)

    def abrir_pasta(self, pasta) -> None:
        pasta.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(pasta)
        else:
            webbrowser.open(pasta.as_uri())

    def _cabecalho(self, pai, titulo: str, subtitulo: str = "") -> tk.Frame:
        topo = tk.Frame(pai, bg=FUNDO)
        topo.pack(fill="x", padx=32, pady=(26, 14))
        acoes = tk.Frame(topo, bg=FUNDO)
        acoes.pack(side="right", anchor="n")  # os botões primeiro: o texto quebra linha, os botões não somem
        texto = tk.Frame(topo, bg=FUNDO)
        texto.pack(side="left", fill="x", expand=True)
        rotulo(texto, titulo, F_TITULO).pack(anchor="w")
        if subtitulo:
            sub = rotulo(texto, subtitulo, F_NORMAL, SUAVE, wraplength=560)
            sub.pack(anchor="w", pady=(2, 0), fill="x")
            # Quebra a linha pela largura que sobra ao lado dos botões (nada fica cortado).
            texto.bind("<Configure>", lambda e: sub.configure(wraplength=max(220, e.width - 8)))
        return acoes

    def _cartao_acao(self, pai, titulo: str, descricao: str, botao: str, comando, linha: int, coluna: int,
                     tipo: str = "secundario") -> None:
        c = cartao(pai, padx=18, pady=16)
        c.grid(row=linha, column=coluna, sticky="nsew", padx=8, pady=8)
        rotulo(c, titulo, F_NEGRITO, bg=CARTAO).pack(anchor="w")
        rotulo(c, descricao, F_NORMAL, SUAVE, bg=CARTAO, wraplength=360).pack(anchor="w", pady=(4, 12), fill="x")
        Botao(c, botao, comando, tipo).pack(anchor="w", side="bottom")

    def _grade(self, pai, colunas: int = 2) -> tk.Frame:
        grade = tk.Frame(pai, bg=FUNDO)
        grade.pack(fill="x", padx=24)
        for i in range(colunas):
            grade.columnconfigure(i, weight=1, uniform="col")
        return grade

    # -- ações comuns
    def acao(self, chave: str) -> None:
        {
            "importar_cv": self.importar_cv, "conectar_linkedin": self.conectar_linkedin, "criar_busca": self.criar_busca,
            "buscar_vagas": lambda: self.executar("Buscar vagas", ["vagas", "rodada"]),
            "saude": lambda: self.executar("Fontes de vagas", ["saude"]),
            "vagas": lambda: self.mostrar("vagas"), "candidaturas": lambda: self.mostrar("candidaturas"),
            "aprovacoes": lambda: self.mostrar("aprovacoes"),
            "email_alertas": self.configurar_email, "agendar_busca": self._agendar_busca,
        }[chave]()

    def importar_cv(self) -> None:
        arquivo = filedialog.askopenfilename(parent=self.raiz, title="Escolha seu currículo",
                                             filetypes=[("Currículo", "*.pdf *.docx *.txt"), ("Todos os arquivos", "*.*")])
        if arquivo:
            self.executar("Trazer seu currículo", ["importar", arquivo])

    def conectar_linkedin(self) -> None:
        tem_zip = messagebox.askyesnocancel(NOME_APP, COMO_EXPORTAR_LINKEDIN, parent=self.raiz)
        if tem_zip is None:
            return
        if not tem_zip:
            webbrowser.open(URL_EXPORTACAO_LINKEDIN)
            return
        arquivo = filedialog.askopenfilename(parent=self.raiz, title="Escolha o arquivo .zip do LinkedIn",
                                             filetypes=[("Arquivo do LinkedIn", "*.zip")])
        if arquivo:
            self.executar("Conectar LinkedIn", ["li", "conectar", arquivo])

    def criar_busca(self) -> None:
        from ..radar.modelos import carregar_config

        existentes = {b.nome for b in carregar_config().buscas}
        livres = [f for f in estado.FOCOS if f not in existentes]
        if not livres:
            messagebox.showinfo(NOME_APP, "Todas as áreas já têm uma busca. Para mudar uma, remova-a em "
                                "Configurações e crie de novo.", parent=self.raiz)
            return
        opcoes_area = [(f, nome + ("  (já tem busca)" if f in existentes else "")) for f, nome in estado.FOCOS.items()]
        campos = [
            ("focos", "Áreas (pode marcar mais de uma)", "varios_lista", opcoes_area, [livres[0]],
             "Cada área vira uma busca separada, com os cargos e nomes de vaga daquela área."),
            ("niveis", "Nível", "varios", [("estagio", "Estágio"), ("trainee", "Trainee"), ("junior", "Júnior"),
                                           ("pleno", "Pleno")], ["estagio", "trainee", "junior"], None),
            ("contratos", "Tipo de contrato", "varios", [("estagio", "Estágio"), ("clt", "CLT"), ("pj", "PJ")],
             ["estagio", "clt", "pj"], None),
            ("cidades", "Cidades para trabalho presencial ou híbrido", "texto", None, "",
             "Separe por vírgula. Em branco = Belo Horizonte e região metropolitana."),
            ("remoto", "Aceito trabalhar remoto", "marcar", None, True, None),
            ("salario", "Salário ou bolsa mínima (opcional)", "texto", None, "", "Só números, ex.: 1500"),
        ]
        respostas = None
        while True:
            respostas = perguntar(self.raiz, "Que vagas você procura?", "O agente usa isso para procurar e dar nota "
                                  "às vagas.", campos if respostas is None else [
                                      (c, t, tp, op, respostas.get(c, p), aj) for c, t, tp, op, p, aj in campos],
                                  botao="Salvar busca")
            if not respostas:
                return
            try:
                comandos, puladas = estado.comandos_busca(respostas, existentes)
                break
            except ValueError as erro:
                messagebox.showwarning(NOME_APP, str(erro), parent=self.raiz)  # volta ao formulário com o que já marcou
        if puladas:
            messagebox.showinfo(NOME_APP, "Estas áreas já tinham busca e ficaram como estavam:\n• " + "\n• ".join(puladas)
                                + "\n\nPara mudar uma delas, remova-a em Configurações e crie de novo.", parent=self.raiz)
        if comandos:
            self.executar("Salvar busca de vagas" if len(comandos) == 1 else f"Salvar {len(comandos)} buscas de vagas",
                          comandos)

    def configurar_email(self) -> None:
        from ..configuracao import carregar_configuracao, salvar_configuracao
        from ..operacao import credenciais

        provedores = [(chave, nome) for chave, (nome, _, _) in credenciais.PROVEDORES.items()]
        explicacao = ("O agente lê os alertas de vaga que chegam no seu e-mail (LinkedIn, Gupy, Indeed…), só para ler: "
                      "nunca apaga, marca ou responde. Use a mesma conta que aparece no seu Outlook (Gmail, Hotmail…): "
                      "o agente lê direto do servidor e você continua usando o Outlook normalmente. Use uma SENHA DE "
                      "APP, não a senha normal do e-mail.\n\n"
                      "Gmail: " + credenciais.COMO_CRIAR_SENHA_DE_APP["gmail"] + "\n\n"
                      "Para receber alertas do LinkedIn: pesquise a vaga no LinkedIn, ligue \"Criar alerta\" e escolha "
                      "receber por e-mail, todo dia.")
        r = perguntar(self.raiz, "Receber vagas do seu e-mail", explicacao, [
            ("provedor", "Seu e-mail é do", "escolha", provedores, "gmail", None),
            ("email", "Endereço de e-mail", "texto", None, credenciais.email_configurado() or "", None),
            ("senha", "Senha de app", "senha", None, "", "16 letras geradas pelo provedor. Fica só no seu Windows."),
            ("pasta", "Pasta onde chegam os alertas", "texto", None, "INBOX",
             "INBOX = caixa de entrada. Se você criou um marcador só para vagas, escreva o nome dele."),
            ("avisos", "Mandar também os avisos do agente para este e-mail", "marcar", None, True, None),
        ], botao="Salvar e testar")
        if not r:
            return
        cfg = credenciais.ConfigEmail(provedor=r["provedor"], email=r["email"], senha=r["senha"], pasta=r["pasta"],
                                      avisos=r["avisos"])
        try:
            valores = credenciais.variaveis(cfg)
            self.raiz.config(cursor="watch")
            self.raiz.update()
            quantos = credenciais.testar_imap(valores["AGENTE_IMAP_HOST"], valores["AGENTE_IMAP_USUARIO"],
                                              valores["AGENTE_IMAP_SENHA"], valores["AGENTE_IMAP_PASTA"])
            credenciais.gravar_variaveis_do_usuario(valores)
        except Exception as erro:  # noqa: BLE001 - login recusado, pasta errada, sem internet...
            messagebox.showerror(NOME_APP, f"Não consegui entrar no e-mail: {erro}\n\nConfira o endereço, a senha de "
                                 "app e a pasta. Nada foi salvo.", parent=self.raiz)
            return
        finally:
            self.raiz.config(cursor="")
        if cfg.avisos:
            central = carregar_configuracao()
            central.notificacao.canal = "email"
            central.notificacao.email_para = cfg.email.strip()
            salvar_configuracao(central)
        messagebox.showinfo(NOME_APP, f"Pronto! Entrei no e-mail e achei {quantos} mensagem(ns) da última semana na pasta "
                            f"{cfg.pasta or 'INBOX'}.\n\nA partir de agora, cada busca lê os alertas de vaga.",
                            parent=self.raiz)
        self.atualizar()

    def abrir_pasta_dados(self) -> None:
        from ..storage import diretorio_dados

        pasta = diretorio_dados()
        pasta.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(pasta)
        else:
            webbrowser.open(pasta.as_uri())

    # ================================================================ telas

    def _pagina_inicio(self, pai) -> None:
        inicio = estado.montar_inicio()
        corpo = area_rolavel(pai)
        saudacao = f"Olá, {inicio.nome}!" if inicio.nome else "Bem-vindo(a)!"
        self._cabecalho(corpo, saudacao, "Aqui está o que importa hoje na sua busca de emprego.")

        p = inicio.proximo
        destaque = tk.Frame(corpo, bg=DESTAQUE_CLARO, highlightthickness=1, highlightbackground="#bfe0cf", padx=22, pady=18)
        destaque.pack(fill="x", padx=32, pady=(0, 16))
        rotulo(destaque, "PRÓXIMO PASSO", F_PEQUENA, DESTAQUE, bg=DESTAQUE_CLARO).pack(anchor="w")
        rotulo(destaque, p.titulo, F_SUBTITULO, TEXTO, bg=DESTAQUE_CLARO).pack(anchor="w", pady=(2, 2))
        rotulo(destaque, p.explicacao, F_NORMAL, SUAVE, bg=DESTAQUE_CLARO, wraplength=760).pack(anchor="w")
        if p.acao:
            Botao(destaque, p.botao or "Começar", lambda: self.acao(p.acao), "primario").pack(anchor="w", pady=(12, 0))

        n = inicio.numeros
        grade = self._grade(corpo, 4)
        for i, (titulo, valor, destino) in enumerate([
            ("Vagas boas para você", n["vagas_boas"], "vagas"),
            ("Candidaturas em andamento", n["em_andamento"], "candidaturas"),
            ("Lembretes para hoje", n["lembretes"], "candidaturas"),
            ("Esperando sua aprovação", n["aprovacoes"], "aprovacoes"),
        ]):
            c = cartao(grade, padx=16, pady=14, cursor="hand2")
            c.grid(row=0, column=i, sticky="nsew", padx=8, pady=8)
            numero = rotulo(c, str(valor), F_NUMERO, DESTAQUE if valor else SUAVE, bg=CARTAO)
            numero.pack(anchor="w")
            legenda = rotulo(c, titulo, F_NORMAL, SUAVE, bg=CARTAO)
            legenda.pack(anchor="w")
            for w in (c, numero, legenda):
                w.bind("<Button-1>", lambda _e, d=destino: self.mostrar(d))

        if not all(passo.feito for passo in inicio.passos):
            bloco = cartao(corpo, padx=22, pady=18)
            bloco.pack(fill="x", padx=32, pady=(10, 8))
            feitos = sum(passo.feito for passo in inicio.passos)
            rotulo(bloco, f"Primeiros passos · {feitos} de {len(inicio.passos)}", F_SUBTITULO, bg=CARTAO).pack(anchor="w")
            rotulo(bloco, "Faça uma vez e o agente passa a trabalhar para você todo dia.", F_NORMAL, SUAVE,
                   bg=CARTAO).pack(anchor="w", pady=(0, 10))
            for numero, passo in enumerate(inicio.passos, 1):
                linha = tk.Frame(bloco, bg=CARTAO)
                linha.pack(fill="x", pady=6)
                marca = "✓" if passo.feito else str(numero)
                tk.Label(linha, text=marca, width=3, font=F_NEGRITO, fg="#ffffff" if passo.feito else DESTAQUE,
                         bg=DESTAQUE if passo.feito else DESTAQUE_CLARO).pack(side="left", padx=(0, 12), ipady=4)
                texto = tk.Frame(linha, bg=CARTAO)
                texto.pack(side="left", fill="x", expand=True)
                rotulo(texto, passo.titulo, F_NEGRITO, SUAVE if passo.feito else TEXTO, bg=CARTAO).pack(anchor="w")
                rotulo(texto, passo.explicacao, F_PEQUENA, SUAVE, bg=CARTAO).pack(anchor="w")
                Botao(linha, "Refazer" if passo.feito else "Fazer agora", lambda a=passo.acao: self.acao(a),
                      "link" if passo.feito else "primario").pack(side="right")

        rodape = tk.Frame(corpo, bg=FUNDO)
        rodape.pack(fill="x", padx=32, pady=(10, 26))
        quando = inicio.ultima_busca.astimezone().strftime("%d/%m às %H:%M") if inicio.ultima_busca else "nunca"
        rotulo(rodape, f"Última busca de vagas: {quando}", F_NORMAL, SUAVE).pack(side="left")
        Botao(rodape, "Buscar vagas agora", lambda: self.acao("buscar_vagas")).pack(side="right")

    # ---------------------------------------------------------------- vagas

    def _pagina_vagas(self, pai) -> None:
        from ..candidaturas import carregar_candidaturas
        from ..radar.modelos import carregar_base

        acoes = self._cabecalho(pai, "Vagas", "As vagas que o agente encontrou, da maior nota para a menor. "
                                              "A nota mostra o quanto a vaga combina com você.")
        Botao(acoes, "Adicionar vaga por link", self._adicionar_vaga).pack(side="right", padx=(8, 0))
        Botao(acoes, "Candidatar às melhores", self._candidatar_melhores, "primario").pack(side="right", padx=(8, 0))
        Botao(acoes, "Buscar vagas agora", lambda: self.acao("buscar_vagas")).pack(side="right")

        filtro = getattr(self, "_filtro_vagas", "recomendadas")
        abas = tk.Frame(pai, bg=FUNDO)
        abas.pack(fill="x", padx=32, pady=(0, 8))
        for valor, nome in (("recomendadas", "Recomendadas"), ("salvas", "Salvas"), ("todas", "Todas")):
            def trocar(v=valor):
                self._filtro_vagas = v
                self.mostrar("vagas")
            Botao(abas, nome, trocar, "primario" if valor == filtro else "secundario", padx=12, pady=5).pack(side="left", padx=(0, 6))

        linhas = estado.linhas_vagas(carregar_base(), carregar_candidaturas(), filtro)
        if not linhas:
            vazio = cartao(pai, padx=24, pady=24)
            vazio.pack(fill="x", padx=32, pady=10)
            rotulo(vazio, "Nenhuma vaga aqui ainda.", F_SUBTITULO, bg=CARTAO).pack(anchor="w")
            rotulo(vazio, "Clique em \"Buscar vagas agora\" ou veja a aba \"Todas\".", F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w")
            return

        quadro = cartao(pai)
        quadro.pack(fill="both", expand=True, padx=32)
        colunas = (("nota", "Nota", 60), ("titulo", "Vaga", 330), ("empresa", "Empresa", 170), ("local", "Local", 170),
                   ("situacao", "Situação", 140))
        tabela = ttk.Treeview(quadro, columns=[c for c, _, _ in colunas], show="headings", selectmode="browse")
        for chave, nome, largura in colunas:
            tabela.heading(chave, text=nome, anchor="w")
            tabela.column(chave, width=largura, anchor="center" if chave == "nota" else "w", stretch=chave == "titulo")
        tabela.tag_configure("alta", foreground=DESTAQUE)
        tabela.tag_configure("baixa", foreground=SUAVE)
        tabela.tag_configure("golpe", foreground=PERIGO)
        for l in linhas:
            tag = "golpe" if l.alerta else "alta" if l.nota >= 70 else "baixa" if l.nota < 50 else ""
            tabela.insert("", "end", iid=l.id, values=(l.nota, l.titulo, l.empresa, l.local, l.situacao), tags=(tag,))
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=tabela.yview)
        tabela.configure(yscrollcommand=rolagem.set)
        rolagem.pack(side="right", fill="y")
        tabela.pack(fill="both", expand=True)

        barra = tk.Frame(pai, bg=FUNDO)
        barra.pack(fill="x", padx=32, pady=14)
        rotulo(barra, "Escolha uma vaga na lista e:", F_NORMAL, SUAVE).pack(side="left", padx=(0, 10))

        def selecionada() -> str | None:
            sel = tabela.selection()
            if not sel:
                messagebox.showinfo(NOME_APP, "Clique numa vaga da lista primeiro.", parent=self.raiz)
                return None
            return sel[0]

        def ver():
            if (vid := selecionada()):
                self.executar("Detalhes da vaga", ["vagas", "ver", vid])

        def candidatar():
            if (vid := selecionada()):
                if messagebox.askyesno(NOME_APP, "O agente vai montar seu kit de candidatura: currículo sob medida, "
                                       "mensagem e respostas do formulário.\n\nEle preenche e PARA antes de enviar: "
                                       "quem clica em enviar é você. Continuar?", parent=self.raiz):
                    self.executar("Candidatar-me", ["candidatar", vid])

        def salvar():
            if (vid := selecionada()):
                self.executar("Salvar vaga", ["vagas", "salvar", vid])

        def sem_interesse():
            if (vid := selecionada()) is None:
                return
            r = perguntar(self.raiz, "Por que essa vaga não serve?", "O agente aprende com isso e melhora as próximas notas.",
                          [("motivo", "Motivo", "escolha", MOTIVOS_SEM_INTERESSE, "area", None)], botao="Enviar")
            if r:
                self.executar("Vaga sem interesse", ["vagas", "feedback", vid, "--nao-interessa", "--motivo", r["motivo"]])

        Botao(barra, "Quero me candidatar", candidatar, "primario").pack(side="left")
        Botao(barra, "Ver detalhes", ver).pack(side="left", padx=6)
        Botao(barra, "Salvar para depois", salvar).pack(side="left")
        Botao(barra, "Não tenho interesse", sem_interesse, "perigo").pack(side="left", padx=6)
        tabela.bind("<Double-Button-1>", lambda _e: ver())

    def _adicionar_vaga(self) -> None:
        r = perguntar(self.raiz, "Adicionar vaga por link", "Cole o link de uma vaga que você achou. O agente lê e dá nota.",
                      [("url", "Link da vaga", "texto", None, "", "Ex.: https://empresa.gupy.io/jobs/123")], botao="Adicionar")
        if r and r["url"].strip():
            self.executar("Adicionar vaga", ["vagas", "link", r["url"].strip()])

    # ---------------------------------------------------------------- candidaturas

    def _pagina_candidaturas(self, pai) -> None:
        from ..candidaturas import Etapa, carregar_candidaturas
        from ..funil import carregar_lembretes, vencidos

        acoes = self._cabecalho(pai, "Minhas candidaturas", "Acompanhe cada processo. Quando algo acontecer, "
                                                            "conte ao agente em \"O que aconteceu?\".")
        Botao(acoes, "Ler e-mails de retorno", lambda: self.executar("Ler e-mails de retorno", ["funil", "emails"])).pack(
            side="right", padx=(8, 0))
        Botao(acoes, "Calendário (.ics)", lambda: self.executar("Exportar calendário", ["funil", "agenda"])).pack(side="right")

        pendentes = vencidos(carregar_lembretes())
        if pendentes:
            aviso = tk.Frame(pai, bg=ATENCAO_CLARO, highlightthickness=1, highlightbackground="#f5d9a8", padx=18, pady=12)
            aviso.pack(fill="x", padx=32, pady=(0, 10))
            rotulo(aviso, "Lembretes", F_NEGRITO, ATENCAO, bg=ATENCAO_CLARO).pack(anchor="w")
            for lembrete in pendentes[:5]:
                linha = tk.Frame(aviso, bg=ATENCAO_CLARO)
                linha.pack(fill="x", pady=2)
                rotulo(linha, f"• {lembrete.descricao} ({lembrete.quando.astimezone():%d/%m %H:%M})", F_NORMAL,
                       bg=ATENCAO_CLARO).pack(side="left")
                Botao(linha, "Feito", lambda i=lembrete.id: self.executar("Lembrete feito", ["funil", "feito", i]),
                      "link").pack(side="right")

        mostrar_todas = getattr(self, "_mostrar_encerradas", False)
        colecao = carregar_candidaturas()
        linhas = estado.linhas_candidaturas(colecao, mostrar_todas)
        opcoes = tk.Frame(pai, bg=FUNDO)
        opcoes.pack(fill="x", padx=32, pady=(0, 8))

        def alternar():
            self._mostrar_encerradas = not mostrar_todas
            self.mostrar("candidaturas")
        Botao(opcoes, "Esconder encerradas" if mostrar_todas else "Mostrar também as encerradas", alternar, "link").pack(side="left")

        if not linhas:
            vazio = cartao(pai, padx=24, pady=24)
            vazio.pack(fill="x", padx=32, pady=10)
            rotulo(vazio, "Nenhuma candidatura ainda.", F_SUBTITULO, bg=CARTAO).pack(anchor="w")
            rotulo(vazio, "Vá em Vagas, escolha uma e clique em \"Quero me candidatar\".", F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w")
            Botao(vazio, "Ver vagas", lambda: self.mostrar("vagas"), "primario").pack(anchor="w", pady=(12, 0))
            return

        quadro = cartao(pai)
        quadro.pack(fill="both", expand=True, padx=32)
        colunas = (("vaga", "Vaga", 230), ("empresa", "Empresa", 130), ("etapa", "Etapa", 140), ("desde", "Desde", 90),
                   ("proximo", "Próximo / motivo", 250))
        tabela = ttk.Treeview(quadro, columns=[c for c, _, _ in colunas], show="headings", selectmode="browse")
        for chave, nome, largura in colunas:
            tabela.heading(chave, text=nome, anchor="w")
            tabela.column(chave, width=largura, minwidth=70, anchor="w", stretch=chave in ("vaga", "proximo"))
        tabela.tag_configure("encerrada", foreground=SUAVE)
        for l in linhas:
            tabela.insert("", "end", iid=l.id, values=(l.vaga, l.empresa, l.etapa, l.desde, l.proximo),
                          tags=("encerrada",) if l.encerrada else ())
        tabela.pack(fill="both", expand=True)

        def escolhida():
            sel = tabela.selection()
            if not sel:
                messagebox.showinfo(NOME_APP, "Clique numa candidatura da lista primeiro.", parent=self.raiz)
                return None
            return colecao.buscar(sel[0])

        def aconteceu():
            c = escolhida()
            if c is None:
                return
            if c.status in (Etapa.ENCONTRADA, Etapa.SELECIONADA):
                if messagebox.askyesno(NOME_APP, "Você já enviou esta candidatura na plataforma?", parent=self.raiz):
                    self.executar("Candidatura enviada", ["funil", "enviada", c.id])
                return
            opcoes_etapa = estado.proximas_etapas(c)
            if not opcoes_etapa:
                messagebox.showinfo(NOME_APP, "Este processo já foi encerrado.", parent=self.raiz)
                return
            r = perguntar(self.raiz, "O que aconteceu?", f"{c.vaga_titulo} — {c.empresa or ''}",
                          [("etapa", "Escolha a opção", "escolha", [(e.value, f) for e, f in opcoes_etapa], None, None)])
            if not r:
                return
            etapa = Etapa(r["etapa"])
            args = ["funil", "mover", c.id, etapa.value]
            if estado.motivos(etapa):
                m = perguntar(self.raiz, "Qual foi o motivo?", "Isso ajuda o agente a melhorar suas próximas candidaturas.",
                              [("motivo", "Motivo", "escolha", [(x, x[:1].upper() + x[1:]) for x in estado.motivos(etapa)], None, None)])
                if not m:
                    return
                args += ["--motivo", m["motivo"]]
            if estado.pede_data(etapa):
                while True:
                    d = perguntar(self.raiz, "Quando vai ser?", "O agente cria um lembrete e prepara você para a etapa.",
                                  [("quando", "Data e hora", "texto", None, "", "Ex.: 25/11/2026 14:30. Em branco = ainda não sei.")])
                    if d is None:
                        return
                    try:
                        quando = estado.data_para_cli(d["quando"])
                        break
                    except ValueError:
                        messagebox.showwarning(NOME_APP, "Data inválida. Use dia/mês/ano e hora, ex.: 25/11/2026 14:30.",
                                               parent=self.raiz)
                args += ["--quando", quando or ""]  # vazio = ainda sem data (a CLI não pergunta de novo)
            self.executar("Atualizar candidatura", args)

        def preparar():
            if (c := escolhida()):
                self.executar("Preparar para a entrevista", ["funil", "preparar", c.id])

        def followup():
            if (c := escolhida()):
                self.executar("Mensagem de follow-up", ["funil", "followup", c.id])

        barra = tk.Frame(pai, bg=FUNDO)
        barra.pack(fill="x", padx=32, pady=14)
        Botao(barra, "O que aconteceu?", aconteceu, "primario").pack(side="left")
        Botao(barra, "Preparar para entrevista", preparar).pack(side="left", padx=6)
        Botao(barra, "Escrever follow-up", followup).pack(side="left")
        tabela.bind("<Double-Button-1>", lambda _e: aconteceu())

    # ---------------------------------------------------------------- perfil

    def _pagina_perfil(self, pai) -> None:
        from ..storage import carregar_perfil, perfil_existe

        corpo = area_rolavel(pai)
        self._cabecalho(corpo, "Meu perfil e currículo", "Tudo sai do seu perfil. O agente nunca inventa nada: "
                                                         "o que ele não tiver certeza, pergunta a você.")
        if not perfil_existe():
            vazio = cartao(corpo, padx=24, pady=22)
            vazio.pack(fill="x", padx=32, pady=(0, 10))
            rotulo(vazio, "Você ainda não tem perfil", F_SUBTITULO, bg=CARTAO).pack(anchor="w")
            rotulo(vazio, "O jeito mais rápido é trazer seu currículo. Também dá para usar o arquivo do LinkedIn.",
                   F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w", pady=(2, 12))
            botoes = tk.Frame(vazio, bg=CARTAO)
            botoes.pack(anchor="w")
            Botao(botoes, "Trazer meu currículo", self.importar_cv, "primario").pack(side="left")
            Botao(botoes, "Usar arquivo do LinkedIn", self.conectar_linkedin).pack(side="left", padx=8)
            Botao(botoes, "Criar respondendo perguntas", lambda: self.executar("Criar perfil", ["perfil", "criar"])).pack(side="left")
            return

        p = carregar_perfil()
        resumo = cartao(corpo, padx=22, pady=18)
        resumo.pack(fill="x", padx=32, pady=(0, 8))
        rotulo(resumo, p.contato.nome, F_SUBTITULO, bg=CARTAO).pack(anchor="w")
        local = ", ".join(x for x in (p.contato.cidade, p.contato.uf) if x)
        rotulo(resumo, " · ".join(x for x in (p.contato.email, local) if x), F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w")
        if p.objetivo:
            rotulo(resumo, p.objetivo, F_NORMAL, bg=CARTAO, wraplength=820).pack(anchor="w", pady=(8, 0))
        numeros = tk.Frame(resumo, bg=CARTAO)
        numeros.pack(anchor="w", pady=(12, 0))
        for valor, nome in ((len(p.experiencias), "experiências"), (len(p.projetos), "projetos"),
                            (len(p.formacao), "formações"), (len(p.certificacoes), "certificados"),
                            (len(p.competencias_tecnicas), "competências")):
            bloco = tk.Frame(numeros, bg=CARTAO)
            bloco.pack(side="left", padx=(0, 26))
            rotulo(bloco, str(valor), (FONTE, 16, "bold"), DESTAQUE, bg=CARTAO).pack(anchor="w")
            rotulo(bloco, nome, F_PEQUENA, SUAVE, bg=CARTAO).pack(anchor="w")
        if p.competencias_tecnicas:
            rotulo(resumo, "Competências: " + ", ".join(p.competencias_tecnicas[:14]) +
                   ("…" if len(p.competencias_tecnicas) > 14 else ""), F_PEQUENA, SUAVE, bg=CARTAO,
                   wraplength=820).pack(anchor="w", pady=(10, 0))
        pendentes = len(p.rascunhos.experiencias) + len(p.rascunhos.formacoes)
        if pendentes:
            aviso = tk.Frame(corpo, bg=ATENCAO_CLARO, padx=18, pady=10, highlightthickness=1, highlightbackground="#f5d9a8")
            aviso.pack(fill="x", padx=32, pady=(4, 4))
            rotulo(aviso, f"{pendentes} item(ns) do currículo esperando você completar (datas, detalhes).", F_NORMAL,
                   ATENCAO, bg=ATENCAO_CLARO).pack(side="left")
            Botao(aviso, "Completar agora", lambda: self.executar("Completar itens", ["rascunhos"]), "link").pack(side="right")

        grade = self._grade(corpo, 2)
        itens = [
            ("Abrir a Gupy (preenche seus dados)", "Abre a Gupy no navegador do agente. Em todo formulário, ele preenche "
             "nome, e-mail, telefone, cidade, estado e links (só campos vazios, nunca envia nada).",
             "Abrir a Gupy", lambda: self.executar("Gupy com preenchimento automático", ["plataformas", "abrir", "gupy"]),
             "primario"),
            ("Gerar meu currículo (PDF e Word)", "Um currículo limpo, que os robôs de seleção (ATS) conseguem ler.",
             "Gerar currículo", self._gerar_cv, "primario"),
            ("Nota do currículo", "De 0 a 100: o quanto seu currículo combina com as vagas que você quer, e o que melhorar.",
             "Ver nota", lambda: self.executar("Nota do currículo", ["cv", "nota"]), "secundario"),
            ("O que falta no meu currículo", "O que as vagas pedem e você ainda não mostra, separado em 3 grupos.",
             "Ver o que falta", lambda: self.executar("O que falta no currículo", ["cv", "lacunas"]), "secundario"),
            ("Conferir se o perfil está completo", "Aponta campos vazios, datas estranhas e o que vale preencher.",
             "Conferir", lambda: self.executar("Conferir perfil", ["perfil", "validar"]), "secundario"),
            ("Frases para confirmar", "Frases que o agente marcou com [A CONFIRMAR] porque precisa da sua palavra.",
             "Revisar frases", lambda: self.executar("Confirmar frases", ["confirmar"]), "secundario"),
            ("Respostas prontas para formulários", "Pretensão salarial, disponibilidade, inglês… Responda uma vez e "
             "o agente reaproveita nas candidaturas.", "Editar respostas", self._respostas, "secundario"),
            ("Atualizar com um currículo novo", "Traga um currículo mais recente: o agente mostra o que mudou antes de aplicar.",
             "Escolher arquivo", self.importar_cv, "secundario"),
            ("Ver perfil completo", "Tudo o que está guardado no seu perfil.",
             "Ver perfil", lambda: self.executar("Perfil completo", ["perfil", "mostrar"]), "secundario"),
        ]
        for i, (titulo, descricao, botao, comando, tipo) in enumerate(itens):
            self._cartao_acao(grade, titulo, descricao, botao, comando, i // 2, i % 2, tipo)
        tk.Frame(corpo, bg=FUNDO, height=20).pack()

    def _gerar_cv(self) -> None:
        r = perguntar(self.raiz, "Gerar currículo", "Escolha a área: o agente organiza o currículo para ela.", [
            ("foco", "Área", "escolha", list(estado.FOCOS.items()), "backend-dotnet", None),
            ("idioma", "Idioma", "escolha", [("pt", "Português"), ("en", "Inglês")], "pt", None),
            ("nivel", "Nível da vaga", "escolha", [("estagio", "Estágio"), ("junior", "Júnior"), ("pleno", "Pleno")],
             "estagio", None),
        ], botao="Gerar")
        if r:
            from ..storage import diretorio_dados

            self.executar("Gerar currículo", ["cv", "exportar", "--foco", r["foco"], "--idioma", r["idioma"],
                                              "--nivel", r["nivel"], "--formato", "ambos"],
                          depois=lambda: self.abrir_pasta(diretorio_dados() / "saidas"))

    def _respostas(self) -> None:
        from ..respostas import PERGUNTAS, carregar_respostas

        banco = carregar_respostas()
        opcoes = [(chave, f"{rotulo_}{'  ✓' if banco.resposta(chave) else ''}") for chave, (rotulo_, _) in PERGUNTAS.items()]
        r = perguntar(self.raiz, "Respostas prontas", "Escolha a pergunta (✓ = já respondida) e escreva sua resposta.",
                      [("chave", "Pergunta", "escolha", opcoes, None, None),
                       ("resposta", "Sua resposta", "textolongo", None, "", "Em branco = apagar a resposta guardada.")],
                      botao="Salvar")
        if not r:
            return
        if r["resposta"].strip():
            self.executar("Salvar resposta", ["respostas", "definir", r["chave"], r["resposta"].strip()])
        elif banco.resposta(r["chave"]):
            self.executar("Apagar resposta", ["respostas", "remover", r["chave"]])

    # ---------------------------------------------------------------- LinkedIn

    def _pagina_linkedin(self, pai) -> None:
        from ..linkedin.estado import carregar_estado

        corpo = area_rolavel(pai)
        self._cabecalho(corpo, "LinkedIn", "Para o seu perfil, o agente prepara cada mudança e você aprova e cola no "
                                           "LinkedIn. Para vagas, você escolhe abaixo se ele trabalha sozinho.")
        conectado = bool(carregar_estado().campos)
        faixa = tk.Frame(corpo, bg=DESTAQUE_CLARO if conectado else ATENCAO_CLARO, padx=18, pady=12)
        faixa.pack(fill="x", padx=32, pady=(0, 8))
        rotulo(faixa, "✓ Dados do LinkedIn carregados." if conectado else "Seu LinkedIn ainda não foi conectado.",
               F_NEGRITO, DESTAQUE if conectado else ATENCAO, bg=faixa.cget("bg")).pack(side="left")
        Botao(faixa, "Atualizar dados" if conectado else "Conectar agora", self.conectar_linkedin,
              "link" if conectado else "primario").pack(side="right")
        self._cartao_automacao_linkedin(corpo)

        grade = self._grade(corpo, 2)
        itens = [
            ("Verificar meu perfil", "Checklist do que um bom perfil precisa, com o que falta no seu.",
             "Verificar", lambda: self.executar("Verificar perfil do LinkedIn", ["li", "auditar"]), "primario"),
            ("Sugestões de melhoria", "Título, Sobre, experiências e competências reescritos, com antes e depois. "
             "Você aprova cada um.", "Ver sugestões", lambda: self.executar("Sugestões para o LinkedIn", ["li", "propor"]),
             "secundario"),
            ("Título do perfil", "3 opções de título (a frase embaixo do seu nome).",
             "Ver opções", lambda: self.executar("Título do LinkedIn", ["li", "titulo"]), "secundario"),
            ("Texto do \"Sobre\"", "Um texto de apresentação feito a partir do seu perfil.",
             "Ver texto", lambda: self.executar("Sobre do LinkedIn", ["li", "sobre"]), "secundario"),
            ("Aviso de que procura emprego", "Como ligar o \"Open to Work\" com os cargos certos.",
             "Ver passo a passo", lambda: self.executar("Open to Work", ["li", "open-to-work"]), "secundario"),
            ("Ideias de posts", "Sugestões de posts a partir dos seus projetos. Nada é publicado sem você.",
             "Ver ideias", lambda: self.executar("Ideias de posts", ["li", "pauta"]), "secundario"),
            ("Ajustes de privacidade", "Configurações recomendadas antes de mexer no perfil.",
             "Ver ajustes", lambda: self.executar("Ajustes do LinkedIn", ["li", "ajustes"]), "secundario"),
            ("Histórico de mudanças", "Tudo o que você já aprovou, com opção de desfazer.",
             "Ver histórico", lambda: self.executar("Histórico do LinkedIn", ["li", "log"]), "secundario"),
        ]
        for i, (titulo, descricao, botao, comando, tipo) in enumerate(itens):
            self._cartao_acao(grade, titulo, descricao, botao, comando, i // 2, i % 2, tipo)
        tk.Frame(corpo, bg=FUNDO, height=20).pack()

    def _cartao_automacao_linkedin(self, corpo) -> None:
        from ..cli_linkedin_auto import RISCO
        from ..configuracao import carregar_configuracao

        cfg = carregar_configuracao().linkedin_automatico
        bloco = cartao(corpo, padx=22, pady=16)
        bloco.pack(fill="x", padx=32, pady=(0, 8))
        topo = tk.Frame(bloco, bg=CARTAO)
        topo.pack(fill="x")
        estado_txt = "LIGADA" if cfg.ativo else "desligada"
        rotulo(topo, f"Automação no LinkedIn: {estado_txt}", F_SUBTITULO, PERIGO if cfg.ativo else TEXTO,
               bg=CARTAO).pack(side="left")
        if cfg.ativo:
            descricao = ("O agente usa o navegador dele, com a sua conta, para procurar vagas em cada busca e preencher a "
                         "Candidatura Simplificada. Ele para antes de \"Enviar candidatura\": o clique final é seu.")
        else:
            descricao = ("Desligada, o LinkedIn entra pelos alertas de e-mail e você aplica com a ajuda do agente. "
                         "Ligada, o agente procura vagas e preenche a Candidatura Simplificada sozinho. Atenção: o "
                         "LinkedIn proíbe automação e pode restringir a conta.")
        rotulo(bloco, descricao, F_NORMAL, SUAVE, bg=CARTAO, wraplength=820).pack(anchor="w", pady=(4, 10))
        botoes = tk.Frame(bloco, bg=CARTAO)
        botoes.pack(anchor="w")

        def ligar():
            if messagebox.askyesno(NOME_APP, RISCO + "\n\nVocê aceita esse risco e quer ligar a automação?",
                                   icon="warning", parent=self.raiz):
                self.executar("Ligar automação no LinkedIn", ["li", "automatico", "ligar", "--aceito-o-risco"])

        if cfg.ativo:
            Botao(botoes, "Entrar no LinkedIn", lambda: self.executar("Entrar no LinkedIn", ["li", "automatico", "entrar"]),
                  "primario").pack(side="left")
            Botao(botoes, "Testar busca agora", lambda: self.executar("Testar busca no LinkedIn",
                                                                      ["li", "automatico", "testar"])).pack(side="left", padx=8)
            Botao(botoes, "Desligar automação", lambda: self.executar("Desligar automação no LinkedIn",
                                                                       ["li", "automatico", "desligar"]), "perigo").pack(side="left")
        else:
            Botao(botoes, "Ligar automação…", ligar, "perigo").pack(side="left")

    def _candidatar_melhores(self) -> None:
        from ..candidaturas import carregar_candidaturas
        from ..configuracao import carregar_configuracao
        from ..radar.modelos import carregar_base, carregar_config

        central, config = carregar_configuracao(), carregar_config()
        candidaturas = carregar_candidaturas()
        restantes = estado.vagas_restantes_hoje(candidaturas, central.limites.candidaturas_por_dia)
        escolhidas = estado.melhores_para_candidatar(carregar_base(), candidaturas, config.limiar_candidatar, restantes)
        if restantes <= 0:
            messagebox.showinfo(NOME_APP, f"Você já chegou ao limite de {central.limites.candidaturas_por_dia} "
                                "candidaturas de hoje. Amanhã tem mais.", parent=self.raiz)
            return
        if not escolhidas:
            messagebox.showinfo(NOME_APP, f"Nenhuma vaga com nota {config.limiar_candidatar} ou mais esperando "
                                "candidatura. Busque vagas novas ou escolha uma na lista.", parent=self.raiz)
            return
        lista = "\n".join(f"• {l.nota} · {l.titulo} — {l.empresa}" for l in escolhidas)
        if not messagebox.askyesno(NOME_APP, f"O agente vai preparar e preencher {len(escolhidas)} candidatura(s), uma "
                                   f"de cada vez:\n\n{lista}\n\nEm cada uma ele para antes do envio: você confere e "
                                   "clica em Enviar. Continuar?", parent=self.raiz):
            return
        self.executar(f"Candidatar às {len(escolhidas)} melhores", [["candidatar", l.id] for l in escolhidas])

    # ---------------------------------------------------------------- aprovações

    def _pagina_aprovacoes(self, pai) -> None:
        from ..operacao.fila import listar_fila

        corpo = area_rolavel(pai)
        self._cabecalho(corpo, "Aprovações", "Tudo o que o agente quer fazer e precisa do seu sim: textos para o "
                                             "LinkedIn, posts e uso de inteligência artificial.")
        itens = listar_fila()
        if not itens:
            vazio = cartao(corpo, padx=24, pady=24)
            vazio.pack(fill="x", padx=32)
            rotulo(vazio, "✓ Nada esperando por você.", F_SUBTITULO, DESTAQUE, bg=CARTAO).pack(anchor="w")
            rotulo(vazio, "Quando o agente preparar algo, aparece aqui.", F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w")
            return
        for item in itens:
            c = cartao(corpo, padx=20, pady=16)
            c.pack(fill="x", padx=32, pady=(0, 12))
            rotulo(c, item.tipo.upper(), F_PEQUENA, DESTAQUE, bg=CARTAO).pack(anchor="w")
            rotulo(c, item.titulo, F_NEGRITO, bg=CARTAO, wraplength=820).pack(anchor="w")
            if item.antes:
                rotulo(c, "Como está hoje:", F_PEQUENA, SUAVE, bg=CARTAO).pack(anchor="w", pady=(8, 0))
                rotulo(c, item.antes, F_NORMAL, SUAVE, bg=CARTAO, wraplength=820).pack(anchor="w")
            rotulo(c, "Proposta:" if item.antes else "O que vai acontecer:", F_PEQUENA, SUAVE, bg=CARTAO).pack(anchor="w", pady=(8, 0))
            rotulo(c, item.depois, F_NORMAL, bg=CARTAO, wraplength=820).pack(anchor="w")
            for detalhe in item.detalhes:
                rotulo(c, f"• {detalhe}", F_PEQUENA, SUAVE, bg=CARTAO, wraplength=820).pack(anchor="w")
            for problema in item.problemas:
                rotulo(c, f"⚠ {problema}", F_PEQUENA, ATENCAO, bg=CARTAO, wraplength=820).pack(anchor="w")
            botoes = tk.Frame(c, bg=CARTAO)
            botoes.pack(anchor="w", pady=(12, 0))
            Botao(botoes, "Aprovar", lambda i=item.id: self._decidir("aprovar", i), "primario").pack(side="left")
            if not item.id.startswith("ia:"):
                Botao(botoes, "Editar o texto", lambda i=item: self._editar_item(i)).pack(side="left", padx=8)
            Botao(botoes, "Recusar", lambda i=item.id: self._decidir("rejeitar", i), "perigo").pack(side="left", padx=8)

    def _decidir(self, decisao: str, id_: str) -> None:
        from ..operacao import fila

        try:
            resultado = fila.aprovar(id_) if decisao == "aprovar" else fila.rejeitar(id_)
        except ValueError as erro:
            messagebox.showwarning(NOME_APP, f"Não deu para aprovar: {erro}\n\nUse \"Editar o texto\" para corrigir.",
                                   parent=self.raiz)
            return
        partes = [resultado.mensagem]
        if resultado.proximo_passo:
            partes.append(f"\nPróximo passo: {resultado.proximo_passo}")
        if resultado.texto_para_copiar:
            self.raiz.clipboard_clear()
            self.raiz.clipboard_append(resultado.texto_para_copiar)
            partes.append("\nO texto já foi copiado: é só colar (Ctrl+V) no LinkedIn.")
        if resultado.arquivo:
            partes.append(f"\nArquivo: {resultado.arquivo}")
        messagebox.showinfo(NOME_APP, "\n".join(partes), parent=self.raiz)
        self.atualizar()

    def _editar_item(self, item) -> None:
        from ..operacao import fila

        r = perguntar(self.raiz, "Editar o texto", item.titulo,
                      [("texto", "Texto", "textolongo", None, item.depois, None)], botao="Salvar")
        if r and r["texto"].strip():
            try:
                resultado = fila.editar(item.id, texto=r["texto"])
            except ValueError as erro:
                messagebox.showwarning(NOME_APP, str(erro), parent=self.raiz)
                return
            messagebox.showinfo(NOME_APP, resultado.mensagem, parent=self.raiz)
            self.atualizar()

    # ---------------------------------------------------------------- relatórios

    def _pagina_relatorios(self, pai) -> None:
        corpo = area_rolavel(pai)
        self._cabecalho(corpo, "Relatórios", "Como está indo a sua busca: vagas, candidaturas e o que funciona melhor.")
        grade = self._grade(corpo, 2)
        itens = [
            ("Painel geral", "Números da sua busca, com gráficos por fonte, área e versão do currículo. Abre no navegador.",
             "Abrir painel", self._abrir_painel, "primario"),
            ("Relatório da semana", "O que funcionou, o que as vagas pedem e você ainda não tem, e os próximos passos.",
             "Ver relatório", lambda: self.executar("Relatório da semana", ["relatorio", "semanal"]), "secundario"),
            ("Baixar planilhas (Excel)", "Suas vagas, candidaturas e histórico em planilhas que abrem no Excel.",
             "Baixar", self._exportar, "secundario"),
            ("Qual currículo funciona melhor", "Compara as versões do seu currículo pelas respostas que receberam.",
             "Comparar", lambda: self.executar("Desempenho do currículo", ["cv", "desempenho"]), "secundario"),
            ("Tudo o que o agente fez", "Registro de cada ação feita em sites, com data e a sua aprovação.",
             "Ver registro", lambda: self.executar("Registro de ações", ["auditoria"]), "secundario"),
            ("Verificação de qualidade", "Confere se o agente está seguindo as regras combinadas (critérios de aceitação).",
             "Verificar", lambda: self.executar("Verificação de qualidade", ["aceite"]), "secundario"),
        ]
        for i, (titulo, descricao, botao, comando, tipo) in enumerate(itens):
            self._cartao_acao(grade, titulo, descricao, botao, comando, i // 2, i % 2, tipo)

    def _abrir_painel(self) -> None:
        try:
            from ..relatorios import salvar_painel_html

            webbrowser.open(salvar_painel_html().resolve().as_uri())
        except Exception as erro:  # noqa: BLE001
            messagebox.showerror(NOME_APP, f"Não deu para gerar o painel: {erro}", parent=self.raiz)

    def _exportar(self) -> None:
        from ..storage import diretorio_dados

        self.executar("Baixar planilhas", ["exportar"], depois=lambda: self.abrir_pasta(diretorio_dados() / "exportacoes"))

    # ---------------------------------------------------------------- configurações

    def _pagina_config(self, pai) -> None:
        from ..configuracao import carregar_configuracao
        from ..operacao.credenciais import email_configurado
        from ..radar.modelos import carregar_config

        corpo = area_rolavel(pai)
        self._cabecalho(corpo, "Configurações", "Ajuste como o agente procura vagas e quando ele trabalha sozinho.")

        buscas = carregar_config().buscas
        bloco = cartao(corpo, padx=22, pady=18)
        bloco.pack(fill="x", padx=32, pady=(0, 10))
        topo = tk.Frame(bloco, bg=CARTAO)
        topo.pack(fill="x")
        rotulo(topo, "Que vagas eu procuro", F_SUBTITULO, bg=CARTAO).pack(side="left")
        Botao(topo, "Nova busca", self.criar_busca, "primario").pack(side="right")
        if not buscas:
            rotulo(bloco, "Nenhuma busca ainda. Crie uma para o agente saber o que procurar.", F_NORMAL, SUAVE,
                   bg=CARTAO).pack(anchor="w", pady=(8, 0))
        nomes_nivel = {"estagio": "Estágio", "trainee": "Trainee", "junior": "Júnior", "pleno": "Pleno", "senior": "Sênior"}
        for b in buscas:
            linha = tk.Frame(bloco, bg=CARTAO)
            linha.pack(fill="x", pady=(10, 0))

            def remover(n=b.nome):
                if messagebox.askyesno(NOME_APP, f"Remover a busca '{n}'?", parent=self.raiz):
                    self.executar("Remover busca", ["busca", "remover", n])
            Botao(linha, "Remover", remover, "link").pack(side="right", anchor="n")
            info = tk.Frame(linha, bg=CARTAO)
            info.pack(side="left", fill="x", expand=True)
            locais = ", ".join(b.localidades[:3]) + ("…" if len(b.localidades) > 3 else "")
            niveis = ", ".join(nomes_nivel.get(n, n) for n in b.niveis)
            rotulo(info, b.nome, F_NEGRITO, bg=CARTAO).pack(anchor="w")
            rotulo(info, f"{niveis} · {locais}" + (" · aceita remoto" if b.remoto_brasil else ""), F_PEQUENA, SUAVE,
                   bg=CARTAO, wraplength=700).pack(anchor="w")
            rotulo(info, "Cargos: " + ", ".join(b.cargos[:4]) + ("…" if len(b.cargos) > 4 else ""), F_PEQUENA, SUAVE,
                   bg=CARTAO, wraplength=700).pack(anchor="w")

        central = carregar_configuracao()
        grade = self._grade(corpo, 2)
        sugestao = central.somente_sugestao
        itens = [
            ("Busca automática todo dia", "O agente procura vagas sozinho todo dia de manhã e manda o resumo até as 8h.",
             "Agendar", self._agendar_busca, "secundario"),
            ("Relatório toda semana", "Um resumo da semana no domingo à noite.",
             "Agendar", lambda: self.executar("Agendar relatório semanal", ["relatorio", "agendar"]), "secundario"),
            ("Modo só sugestões: " + ("LIGADO" if sugestao else "desligado"),
             "Ligado, o agente não abre nenhum site: só sugere. Bom para testar com calma.",
             "Desligar" if sugestao else "Ligar",
             lambda: self.executar("Modo só sugestões", ["config", "sugestao", "--desligar" if sugestao else "--ligar"]),
             "secundario"),
            ("Vagas e avisos pelo e-mail", "O agente lê os alertas de vaga do seu e-mail e manda os avisos para ele. "
             f"Hoje: {email_configurado() or 'não configurado'}.", "Configurar e-mail", self.configurar_email, "secundario"),
            ("Atalho na Área de Trabalho", "Recria o ícone do agente na sua Área de Trabalho.",
             "Criar atalho", self._criar_atalho, "secundario"),
            ("Pasta dos seus dados", "Onde ficam seu perfil, currículos gerados e relatórios. Nada disso vai para a internet.",
             "Abrir pasta", self.abrir_pasta_dados, "secundario"),
            ("Fontes de vagas", "Mostra se algum site de vagas mudou ou deu erro.",
             "Verificar", lambda: self.executar("Fontes de vagas", ["saude"]), "secundario"),
            ("Modo avançado", "Abre o terminal com os comandos do agente (para quem é de TI).",
             "Abrir terminal", self._terminal, "secundario"),
        ]
        for i, (titulo, descricao, botao, comando, tipo) in enumerate(itens):
            self._cartao_acao(grade, titulo, descricao, botao, comando, i // 2, i % 2, tipo)
        tk.Frame(corpo, bg=FUNDO, height=20).pack()

    def _agendar_busca(self) -> None:
        r = perguntar(self.raiz, "Busca automática", "O computador precisa estar ligado nesse horário.",
                      [("hora", "Horário", "texto", None, "07:00", "Formato HH:MM. Às 7h o resumo fica pronto antes das 8h.")],
                      botao="Agendar")
        if r:
            self.executar("Agendar busca diária", ["vagas", "agendar", "--hora", r["hora"].strip() or "07:00"])

    def _criar_atalho(self) -> None:
        try:
            caminho = criar_atalho()
        except RuntimeError as erro:
            messagebox.showerror(NOME_APP, str(erro), parent=self.raiz)
            return
        messagebox.showinfo(NOME_APP, f"Atalho criado em:\n{caminho}", parent=self.raiz)

    def _terminal(self) -> None:
        import subprocess

        scripts = str(scripts_do_venv())  # o app pode rodar no Python base; o 'agente' está no venv
        ambiente = dict(os.environ, PATH=f"{scripts}{os.pathsep}{os.environ.get('PATH', '')}")
        subprocess.Popen(["cmd.exe", "/k", f"title {NOME_APP} & echo Digite: agente --help"], cwd=raiz_do_projeto(),
                         env=ambiente, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))

    def rodar(self) -> None:
        self.raiz.mainloop()


def abrir_janela() -> None:
    App().rodar()
