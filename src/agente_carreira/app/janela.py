"""Interface do app: navegação lateral, telas em linguagem simples e execução sem console.

Cada tela mora em app/telas/; aqui ficam o App (navegação, faixa de andamento, avisos, fechar com
tarefas rodando) e as ações usadas por várias telas."""

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
from .janela_execucao import ESPERA_PARAR_MS, JanelaExecucao  # noqa: F401
from .telas.inicio import TelaInicio
from .telas.vagas import TelaVagas
from .telas.candidaturas import TelaCandidaturas
from .telas.perfil import TelaPerfil
from .telas.linkedin import TelaLinkedIn
from .telas.aprovacoes import TelaAprovacoes
from .telas.relatorios import TelaRelatorios
from .telas.config import TelaConfig


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


class App(TelaInicio, TelaVagas, TelaCandidaturas, TelaPerfil, TelaLinkedIn, TelaAprovacoes, TelaRelatorios, TelaConfig):
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

        direita = tk.Frame(self.raiz, bg=FUNDO)
        direita.pack(side="left", fill="both", expand=True)
        self._faixa = tk.Frame(direita, bg=DESTAQUE_CLARO, padx=24, pady=8)  # andamento: aparece só quando há algo
        self._faixa_texto = rotulo(self._faixa, "", F_NEGRITO, DESTAQUE, bg=DESTAQUE_CLARO)
        self._faixa_texto.pack(side="left")
        Botao(self._faixa, "Ver andamento", self.ver_andamento, "link").pack(side="right")
        self._faixa_fechar = Botao(self._faixa, "Ocultar", self._ocultar_faixa, "link")
        self._faixa_estado: dict | None = None
        self._faixa_oculta_ate: str | None = None
        self._faixa_giro = 0
        self._aviso = tk.Label(direita, bg=DESTAQUE, fg="#ffffff", font=F_NEGRITO, padx=24, pady=8, anchor="w")
        self._aviso_timer: str | None = None
        self.conteudo = tk.Frame(direita, bg=FUNDO)
        self.conteudo.pack(fill="both", expand=True)
        self._tela_vagas = {"aba": "recomendadas", "texto": "", "modelo": "", "nivel": "", "ordem": ("nota", True)}
        self._janelas: list[JanelaExecucao] = []
        self.raiz.protocol("WM_DELETE_WINDOW", self._ao_fechar_app)
        self.pagina_atual = "inicio"
        self.mostrar("inicio")
        self.raiz.after(400, self._atualizar_faixa)

    def avisar(self, texto: str, segundos: float = 4.0) -> None:
        """Confirmação curta no topo (ex.: "Vaga salva ✓"), que some sozinha."""
        if self._aviso_timer is not None:
            self.raiz.after_cancel(self._aviso_timer)
        self._aviso.configure(text=texto)
        self._aviso.pack(fill="x", before=self.conteudo)
        self._aviso_timer = self.raiz.after(int(segundos * 1000), self._esconder_aviso)

    def _esconder_aviso(self) -> None:
        self._aviso_timer = None
        if self._aviso.winfo_exists():
            self._aviso.pack_forget()

    # -- fechar o app com tarefas rodando
    def tarefas_rodando(self) -> list[JanelaExecucao]:
        self._janelas = [j for j in self._janelas if j.winfo_exists()]
        return [j for j in self._janelas if j.rodando]

    def _ao_fechar_app(self) -> None:
        rodando = self.tarefas_rodando()
        if not rodando:
            self.raiz.destroy()
            return
        nomes = ", ".join(j.titulo for j in rodando)
        escolha = escolher(self.raiz, "Ainda há tarefas rodando",
                           f"{len(rodando)} tarefa(s) em andamento: {nomes}.\n\n"
                           "Parar e sair: o agente para tudo com segurança (o navegador fecha e nada fica pela "
                           "metade).\nDeixar terminando: o app fecha e as tarefas continuam sozinhas; o que elas "
                           "mostrariam vai para data/app/tarefas-em-segundo-plano.log, e perguntas que aparecerem "
                           "são canceladas.",
                           [("parar", "Parar e sair", "primario"), ("deixar", "Deixar terminando e sair", "secundario"),
                            ("voltar", "Voltar", "link")])
        if escolha == "parar":
            for janela in rodando:
                janela.parar()
            self.raiz.title(f"{NOME_APP} — parando as tarefas…")
            self._sair_quando_pararem(time.monotonic() + ESPERA_PARAR_MS / 1000 + 5)
        elif escolha == "deixar":
            self.raiz.destroy()

    def _sair_quando_pararem(self, limite: float) -> None:
        if not self.tarefas_rodando() or time.monotonic() > limite:
            self.raiz.destroy()
            return
        self.raiz.after(200, lambda: self._sair_quando_pararem(limite))

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
        self._janelas.append(JanelaExecucao(self, titulo, args, ao_fim=ao_fim))

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
            "buscar_vagas": self.buscar_vagas,
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

    # ---------------------------------------------------------------- andamento (tarefas longas)

    def buscar_vagas(self) -> None:
        from ..operacao import andamento

        if (estado := andamento.em_andamento("Busca de vagas")) is not None:
            messagebox.showinfo(NOME_APP, "Já tem uma busca de vagas rodando:\n\n" + andamento.descrever(estado)
                                + "\n\nAcompanhe pela faixa no topo ou em \"Ver andamento\".", parent=self.raiz)
            self.ver_andamento()
            return
        self.executar("Buscar vagas", ["vagas", "rodada"])

    def _ocultar_faixa(self) -> None:
        if self._faixa_estado:
            self._faixa_oculta_ate = self._faixa_estado.get("fim")
        self._faixa.pack_forget()

    def _atualizar_faixa(self) -> None:
        from datetime import datetime, timedelta, timezone

        from ..operacao import andamento

        try:
            estado = andamento.ler()
        except Exception:  # noqa: BLE001 - a faixa nunca derruba o app
            estado = None
        anterior, self._faixa_estado = self._faixa_estado, estado
        mostrar = False
        if estado and estado.get("rodando"):
            self._faixa_giro = (self._faixa_giro + 1) % 2
            texto, cor, fundo = ("● " if self._faixa_giro else "○ ") + andamento.descrever(estado), DESTAQUE, DESTAQUE_CLARO
            mostrar = True
            self._faixa_fechar.pack_forget()
        elif estado and estado.get("fim") and estado.get("fim") != self._faixa_oculta_ate:
            fim = datetime.fromisoformat(estado["fim"])
            if datetime.now(timezone.utc) - fim < timedelta(minutes=30):
                ok = estado.get("situacao") == "concluida"
                texto = ("✓ " if ok else "⚠ ") + andamento.descrever(estado)
                cor, fundo = (DESTAQUE, DESTAQUE_CLARO) if ok else (ATENCAO, ATENCAO_CLARO)
                mostrar = True
                self._faixa_fechar.pack(side="right", padx=(0, 12))
        if mostrar:
            for widget in (self._faixa, self._faixa_texto):
                widget.configure(bg=fundo)
            self._faixa_texto.configure(text=texto, fg=cor)
            if not self._faixa.winfo_ismapped():
                self._faixa.pack(fill="x", before=self.conteudo)
        elif self._faixa.winfo_ismapped():
            self._faixa.pack_forget()
        if anterior and anterior.get("rodando") and not (estado and estado.get("rodando")):
            self.atualizar()  # terminou: a tela mostra as vagas novas
        if self.raiz.winfo_exists():
            self.raiz.after(3000, self._atualizar_faixa)

    def ver_andamento(self) -> None:
        from ..operacao import andamento

        janela = tk.Toplevel(self.raiz)
        janela.title(f"Andamento — {NOME_APP}")
        janela.configure(bg=FUNDO, padx=20, pady=16)
        janela.geometry("820x520")
        janela.transient(self.raiz)
        cabecalho = rotulo(janela, "", F_SUBTITULO)
        cabecalho.pack(anchor="w")
        rotulo(janela, "O que o agente fez nas tarefas longas (busca de vagas, e-mail, sites), da mais antiga para a mais "
               "recente. Atualiza sozinho.", F_NORMAL, SUAVE, wraplength=760).pack(anchor="w", pady=(2, 10))
        caixa = tk.Text(janela, font=F_SAIDA, bg=CARTAO, relief="flat", padx=12, pady=10, wrap="word",
                        highlightthickness=1, highlightbackground=BORDA)
        caixa.pack(fill="both", expand=True)

        def atualizar():
            if not janela.winfo_exists():
                return
            estado = andamento.ler()
            cabecalho.configure(text=andamento.descrever(estado) if estado else "Nenhuma tarefa longa registrada ainda.")
            caixa.configure(state="normal")
            caixa.delete("1.0", "end")
            caixa.insert("end", "\n".join(andamento.ultimas_linhas(80)) or "(vazio)")
            caixa.configure(state="disabled")
            caixa.see("end")
            janela.after(3000, atualizar)

        atualizar()

    def rodar(self) -> None:
        self.raiz.mainloop()


def abrir_janela() -> None:
    App().rodar()
