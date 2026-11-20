"""Tela Início: próximo passo, números do dia, primeiros passos e busca automática."""

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


class TelaInicio:
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

        if inicio.fontes_paradas:  # RF-EV-17: um site mudou ou deu erro e a fonte parou
            aviso = tk.Frame(corpo, bg=ATENCAO_CLARO, highlightthickness=1, highlightbackground="#f5d9a8", padx=22, pady=14)
            aviso.pack(fill="x", padx=32, pady=(10, 0))
            rotulo(aviso, "⚠ Uma fonte de vagas parou" if len(inicio.fontes_paradas) == 1 else
                   f"⚠ {len(inicio.fontes_paradas)} fontes de vagas pararam", F_NEGRITO, ATENCAO, bg=ATENCAO_CLARO).pack(anchor="w")
            rotulo(aviso, "Normalmente é porque o site mudou de layout ou pediu login. Confira o site e reative; se "
                   "parar de novo, o agente precisa de ajuste.", F_PEQUENA, SUAVE, bg=ATENCAO_CLARO,
                   wraplength=760).pack(anchor="w", pady=(0, 6))
            for nome, amigavel, erro in inicio.fontes_paradas:
                linha = tk.Frame(aviso, bg=ATENCAO_CLARO)
                linha.pack(fill="x", pady=2)
                rotulo(linha, f"• {amigavel}: {erro}", F_NORMAL, TEXTO, bg=ATENCAO_CLARO, wraplength=600).pack(side="left")
                Botao(linha, "Reativar", lambda n=nome: self.executar("Reativar fonte", ["saude", "reativar", n]),
                      "link").pack(side="right")
            Botao(aviso, "Ver o problema", lambda: self.executar("Fontes de vagas", ["saude"]), "link").pack(anchor="w")

        if inicio.respostas_faltando:  # RF-EV-06
            bloco = tk.Frame(corpo, bg=DESTAQUE_CLARO, highlightthickness=1, highlightbackground="#bfe0cf", padx=22, pady=14)
            bloco.pack(fill="x", padx=32, pady=(10, 0))
            textos = tk.Frame(bloco, bg=DESTAQUE_CLARO)
            textos.pack(side="left", fill="x", expand=True)
            rotulo(textos, f"Responda {len(inicio.respostas_faltando)} perguntas que os formulários sempre fazem",
                   F_NEGRITO, TEXTO, bg=DESTAQUE_CLARO).pack(anchor="w")
            rotulo(textos, "Sem elas, o agente para no meio de cada candidatura: " + ", ".join(
                p.lower() for p in inicio.respostas_faltando[:4]) + ("…" if len(inicio.respostas_faltando) > 4 else "")
                + (" " if len(inicio.respostas_faltando) > 4 else ". ") + "Leva 2 minutos.", F_PEQUENA, SUAVE,
                bg=DESTAQUE_CLARO, wraplength=620).pack(anchor="w")
            Botao(bloco, "Responder agora", self._respostas, "primario").pack(side="right")

        if inicio.lembrete_linkedin:  # RF-EV-22
            lembrete = cartao(corpo, padx=22, pady=14)
            lembrete.pack(fill="x", padx=32, pady=(10, 0))
            rotulo(lembrete, inicio.lembrete_linkedin, F_NORMAL, TEXTO, bg=CARTAO, wraplength=640).pack(side="left")
            Botao(lembrete, "Atualizar pelo LinkedIn", lambda: self.acao("conectar_linkedin")).pack(side="right")

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
        textos = tk.Frame(rodape, bg=FUNDO)
        textos.pack(side="left", fill="x", expand=True)
        rotulo(textos, f"Última busca de vagas: {quando}", F_NORMAL, SUAVE).pack(anchor="w")
        automatica = inicio.busca_automatica
        if automatica is not None:
            linha = tk.Frame(textos, bg=FUNDO)
            linha.pack(anchor="w", fill="x", pady=(2, 0))
            rotulo(linha, ("⚠ " if automatica.problema else "") + automatica.texto, F_NORMAL,
                   ATENCAO if automatica.problema else SUAVE, wraplength=640).pack(side="left")
            if automatica.problema:
                Botao(linha, "Ver o registro", self._abrir_registro_busca, "link").pack(side="left", padx=8)
        Botao(rodape, "Buscar vagas agora", lambda: self.acao("buscar_vagas")).pack(side="right", anchor="n")

    def _abrir_registro_busca(self) -> None:
        from ...storage import diretorio_dados

        registro = diretorio_dados() / "rodada.log"
        if registro.is_file() and hasattr(os, "startfile"):
            os.startfile(registro)
        else:
            messagebox.showinfo(NOME_APP, "A busca automática ainda não deixou registro: ela não chegou a rodar.\n\n"
                                "Para recriá-la, vá em Configurações > \"Busca automática todo dia\" > Agendar.",
                                parent=self.raiz)
