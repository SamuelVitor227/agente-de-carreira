"""Tela Relatórios: painel e exportação."""

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


class TelaRelatorios:
    # ---------------------------------------------------------------- relatórios

    def _pagina_relatorios(self, pai) -> None:
        corpo = area_rolavel(pai)
        self._cabecalho(corpo, "Relatórios", "Como está indo a sua busca: vagas, candidaturas e o que funciona melhor.")
        self._graficos(corpo)
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

    def _graficos(self, corpo) -> None:
        """RF-EV-20: os números e os gráficos principais aqui mesmo, sem abrir o navegador."""
        from ...candidaturas import carregar_candidaturas
        from ...radar.modelos import carregar_base, carregar_config
        from ...relatorios import montar_painel
        from ..componentes import grafico_barras

        base, candidaturas, config = carregar_base(), carregar_candidaturas(), carregar_config()
        total = montar_painel(base, candidaturas).total
        numeros = self._grade(corpo, 4)
        for i, (valor, legenda) in enumerate([
            (str(total.candidaturas), "Candidaturas enviadas"),
            (f"{total.retornos}" + (f" ({total.taxa_retorno}%)" if total.candidaturas else ""), "Retornos das empresas"),
            (str(total.entrevistas), "Entrevistas"),
            (str(total.propostas), "Propostas"),
        ]):
            c = cartao(numeros, padx=16, pady=12)
            c.grid(row=0, column=i, sticky="nsew", padx=8, pady=8)
            rotulo(c, valor, F_NUMERO, DESTAQUE if valor[:1] not in ("0", "") else SUAVE, bg=CARTAO).pack(anchor="w")
            rotulo(c, legenda, F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w")

        graficos = self._grade(corpo, 2)
        blocos = [
            ("Vagas novas por semana", "Passe o mouse numa coluna para ver o número.",
             estado.vagas_por_semana(base), True),
            (f"De onde vêm as vagas boas (nota {config.limiar_salvar}+)", "Uma vaga pode vir de mais de uma fonte.",
             estado.vagas_boas_por_fonte(base, config.limiar_salvar), False),
            ("Funil das candidaturas", "Quantas chegaram a cada etapa.", estado.funil_das_candidaturas(candidaturas), False),
        ]
        for i, (titulo, explicacao, dados, vertical) in enumerate(blocos):
            c = cartao(graficos, padx=16, pady=14)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=8, pady=8)
            rotulo(c, titulo, F_NEGRITO, bg=CARTAO).pack(anchor="w")
            rotulo(c, explicacao, F_PEQUENA, SUAVE, bg=CARTAO).pack(anchor="w", pady=(0, 8))
            if any(v for _, v in dados):
                grafico_barras(c, dados, vertical=vertical, largura=440).pack(anchor="w")
            else:
                rotulo(c, "Ainda sem dados: aparece aqui quando houver.", F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w", pady=12)

    def _abrir_painel(self) -> None:
        try:
            from ...relatorios import salvar_painel_html

            webbrowser.open(salvar_painel_html().resolve().as_uri())
        except Exception as erro:  # noqa: BLE001
            messagebox.showerror(NOME_APP, f"Não deu para gerar o painel: {erro}", parent=self.raiz)

    def _exportar(self) -> None:
        from ...storage import diretorio_dados

        self.executar("Baixar planilhas", ["exportar"], depois=lambda: self.abrir_pasta(diretorio_dados() / "exportacoes"))
