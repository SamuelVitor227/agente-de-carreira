"""Tela LinkedIn: copiloto do perfil e automação de vagas (opcional)."""

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


class TelaLinkedIn:
    # ---------------------------------------------------------------- LinkedIn

    def _pagina_linkedin(self, pai) -> None:
        from ...linkedin.estado import carregar_estado

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
        from ...cli_linkedin_auto import RISCO
        from ...configuracao import carregar_configuracao

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
