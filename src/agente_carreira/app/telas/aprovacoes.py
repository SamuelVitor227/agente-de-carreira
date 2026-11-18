"""Tela Aprovações: o que o agente quer fazer e precisa do seu sim."""

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


class TelaAprovacoes:
    # ---------------------------------------------------------------- aprovações

    def _pagina_aprovacoes(self, pai) -> None:
        from ...operacao.fila import listar_fila

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
        from ...operacao import fila

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
        from ...operacao import fila

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
