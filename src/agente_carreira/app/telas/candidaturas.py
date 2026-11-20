"""Tela Minhas candidaturas: funil, lembretes e o que aconteceu em cada processo."""

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


class TelaCandidaturas:
    # ---------------------------------------------------------------- candidaturas

    def _treinar_entrevista(self, candidatura) -> None:
        """RF-EV-21: uma pergunta provável por vez, com a dica do seu perfil; as melhores respostas ficam guardadas."""
        from ...preparacao import carregar_treino, guardar_resposta_treino, perguntas_provaveis, vaga_da_candidatura
        from ...respostas import carregar_respostas
        from ...storage import carregar_perfil

        vaga = vaga_da_candidatura(candidatura)
        if vaga is None:
            messagebox.showinfo(NOME_APP, "Não achei a vaga desta candidatura para montar as perguntas.", parent=self.raiz)
            return
        perguntas = perguntas_provaveis(carregar_perfil(), vaga)
        treino, banco = carregar_treino(), carregar_respostas()
        janela = tk.Toplevel(self.raiz)
        janela.title(f"Treinar entrevista — {NOME_APP}")
        janela.configure(bg=FUNDO, padx=24, pady=18)
        janela.geometry("760x560")
        janela.transient(self.raiz)
        rotulo(janela, f"Treino para: {vaga.titulo}" + (f" — {vaga.empresa}" if vaga.empresa else ""), F_NEGRITO,
               SUAVE, wraplength=700).pack(anchor="w")
        contador = rotulo(janela, "", F_PEQUENA, SUAVE)
        contador.pack(anchor="w", pady=(10, 0))
        pergunta_rotulo = rotulo(janela, "", F_SUBTITULO, wraplength=700)
        pergunta_rotulo.pack(anchor="w", pady=(2, 4))
        dica = rotulo(janela, "", F_NORMAL, DESTAQUE, wraplength=700)
        dica.pack(anchor="w")
        rotulo(janela, "Responda em voz alta primeiro (1 a 2 minutos). Depois escreva a versão que você gostou:",
               F_PEQUENA, SUAVE).pack(anchor="w", pady=(10, 2))
        caixa = tk.Text(janela, height=9, font=F_NORMAL, wrap="word", relief="solid", bd=1)
        caixa.pack(fill="both", expand=True)
        situacao = rotulo(janela, "", F_PEQUENA, DESTAQUE)
        situacao.pack(anchor="w", pady=(4, 0))
        botoes = tk.Frame(janela, bg=FUNDO)
        botoes.pack(fill="x", pady=(10, 0))
        atual = {"i": 0}

        def mostrar() -> None:
            p = perguntas[atual["i"]]
            contador.configure(text=f"Pergunta {atual['i'] + 1} de {len(perguntas)}")
            pergunta_rotulo.configure(text=p.texto)
            dica.configure(text=p.dica)
            caixa.delete("1.0", "end")
            caixa.insert("1.0", treino.resposta(p.texto) or (banco.resposta(p.chave) if p.chave else None) or "")
            situacao.configure(text="")

        def ir(passo: int) -> None:
            atual["i"] = max(0, min(len(perguntas) - 1, atual["i"] + passo))
            mostrar()

        def guardar() -> None:
            p, texto = perguntas[atual["i"]], caixa.get("1.0", "end").strip()
            if not texto:
                situacao.configure(text="Escreva a resposta antes de guardar.")
                return
            guardar_resposta_treino(p, texto)
            treino.itens.update(carregar_treino().itens)
            situacao.configure(text="Guardada ✓" + (" Também vai para as Respostas prontas dos formulários." if p.chave else ""))

        Botao(botoes, "← Anterior", lambda: ir(-1)).pack(side="left")
        Botao(botoes, "Próxima →", lambda: ir(1)).pack(side="left", padx=8)
        Botao(botoes, "Guardar esta resposta", guardar, "primario").pack(side="left")
        Botao(botoes, "Fechar", janela.destroy, "link").pack(side="right")
        mostrar()

    def _lembrete_feito(self, lembrete_id: str) -> None:
        from ...funil import marcar_lembrete_feito

        if marcar_lembrete_feito(lembrete_id):
            self.avisar("Lembrete marcado como feito ✓")
        self.atualizar()

    def _pagina_candidaturas(self, pai) -> None:
        from ...candidaturas import Etapa, carregar_candidaturas
        from ...funil import carregar_lembretes, vencidos

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
                Botao(linha, "Feito", lambda i=lembrete.id: self._lembrete_feito(i), "link").pack(side="right")

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
        Botao(barra, "Treinar entrevista", lambda: (c := escolhida()) and self._treinar_entrevista(c)).pack(side="left")
        Botao(barra, "Escrever follow-up", followup).pack(side="left", padx=6)
        tabela.bind("<Double-Button-1>", lambda _e: aconteceu())
