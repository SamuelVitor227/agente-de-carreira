"""Tela Meu perfil e currículo."""

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

from .. import estado
from ..atalho import NOME_APP, caminho_icone, criar_atalho, criar_icone, raiz_do_projeto, scripts_do_venv
from ..execucao import Execucao, LeitorAnsi, Pergunta, opcoes_numeradas, texto_sem_ansi

from ..componentes import (  # noqa: F401 - cores, fontes e peças das telas
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
from ..janela_execucao import JanelaExecucao  # noqa: F401


class TelaPerfil:
    # ---------------------------------------------------------------- perfil

    def _pagina_perfil(self, pai) -> None:
        from ...storage import carregar_perfil, perfil_existe

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
            from ...storage import diretorio_dados

            self.executar("Gerar currículo", ["cv", "exportar", "--foco", r["foco"], "--idioma", r["idioma"],
                                              "--nivel", r["nivel"], "--formato", "ambos"],
                          depois=lambda: self.abrir_pasta(diretorio_dados() / "saidas"))

    def _respostas(self) -> None:
        """RF-EV-06: todas as perguntas comuns dos formulários numa tela, já com o que sai do seu perfil."""
        from ...radar.modelos import carregar_config
        from ...respostas import (ESSENCIAIS, EXEMPLOS, LONGAS, PERGUNTAS, carregar_respostas, definir_resposta,
                                  salvar_respostas, sugestoes_do_perfil)
        from ...storage import PerfilAusente, carregar_perfil

        banco = carregar_respostas()
        try:
            sugestoes = sugestoes_do_perfil(carregar_perfil(), carregar_config())
        except PerfilAusente:
            sugestoes = {}
        janela = tk.Toplevel(self.raiz)
        janela.title(f"Respostas prontas — {NOME_APP}")
        janela.configure(bg=FUNDO)
        janela.geometry("760x680")
        janela.transient(self.raiz)
        topo = tk.Frame(janela, bg=FUNDO, padx=22, pady=16)
        topo.pack(fill="x")
        rotulo(topo, "Respostas prontas", F_SUBTITULO).pack(anchor="w")
        rotulo(topo, "As perguntas que os formulários de vaga sempre fazem. Responda uma vez: o agente preenche "
               "sozinho nas candidaturas (só com o que você guardar aqui). As marcadas com ★ quase todo formulário "
               "pede. O que veio do seu perfil está escrito em verde: confira antes de salvar.",
               F_NORMAL, SUAVE, wraplength=700).pack(anchor="w", pady=(4, 0))
        rodape = tk.Frame(janela, bg=FUNDO, padx=22, pady=12)
        rodape.pack(side="bottom", fill="x")
        corpo_externo = tk.Frame(janela, bg=FUNDO)
        corpo_externo.pack(fill="both", expand=True, padx=(22, 0))
        corpo = area_rolavel(corpo_externo)
        leitores = {}
        for chave, (pergunta, uso) in PERGUNTAS.items():
            bloco = tk.Frame(corpo, bg=FUNDO)
            bloco.pack(fill="x", pady=6, padx=(0, 18))
            rotulo(bloco, ("★ " if chave in ESSENCIAIS else "") + pergunta, F_NEGRITO).pack(anchor="w")
            guardada = banco.resposta(chave)
            valor = guardada or sugestoes.get(chave, "")
            cor = DESTAQUE if (not guardada and chave in sugestoes) else TEXTO
            if chave in LONGAS:
                caixa = tk.Text(bloco, height=3, font=F_NORMAL, wrap="word", relief="solid", bd=1, fg=cor)
                caixa.insert("1.0", valor)
                caixa.pack(fill="x", pady=(3, 0))
                leitores[chave] = lambda c=caixa: c.get("1.0", "end").strip()
            else:
                var = tk.StringVar(value=valor)
                entrada = tk.Entry(bloco, textvariable=var, font=F_NORMAL, relief="solid", bd=1, fg=cor)
                entrada.pack(fill="x", pady=(3, 0), ipady=3)
                leitores[chave] = var.get
            ajuda = EXEMPLOS.get(chave, uso)
            rotulo(bloco, ajuda, F_PEQUENA, SUAVE, wraplength=680).pack(anchor="w")

        def salvar() -> None:
            novo = carregar_respostas()
            for chave, ler in leitores.items():
                texto = ler()
                if texto:
                    if texto != (novo.resposta(chave) or ""):
                        definir_resposta(novo, chave, texto)  # guardar = sua aprovação (RN-09)
                else:
                    novo.itens.pop(chave, None)
            salvar_respostas(novo)
            faltam = [PERGUNTAS[c][0] for c in ESSENCIAIS if not novo.resposta(c)]
            janela.destroy()
            self.avisar("Respostas guardadas ✓" + (f" Ainda faltam {len(faltam)} das principais." if faltam else ""))
            self.atualizar()

        Botao(rodape, "Salvar respostas", salvar, "primario").pack(side="right")
        Botao(rodape, "Cancelar", janela.destroy).pack(side="right", padx=8)
