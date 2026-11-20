"""Tela Vagas: abas, procura, filtros, painel de detalhes e ações rápidas."""

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


class TelaVagas:
    # ---------------------------------------------------------------- vagas

    def _pagina_vagas(self, pai) -> None:
        from ...candidaturas import carregar_candidaturas
        from ...radar.modelos import carregar_base, carregar_config

        acoes = self._cabecalho(pai, "Vagas", "Clique numa vaga para ver os detalhes embaixo. A nota mostra o quanto ela "
                                              "combina com você; \"≈\" quer dizer estimada só pelo título.")
        Botao(acoes, "Adicionar vaga por link", self._adicionar_vaga).pack(side="right", padx=(8, 0))
        Botao(acoes, "Candidatar às melhores", self._candidatar_melhores, "primario").pack(side="right", padx=(8, 0))
        Botao(acoes, "Buscar vagas agora", lambda: self.acao("buscar_vagas")).pack(side="right")
        Botao(acoes, "Ainda estão abertas?", lambda: self.executar("Conferir vagas", ["vagas", "conferir"]),
              "link").pack(side="right", padx=(0, 8))

        base, candidaturas, config = carregar_base(), carregar_candidaturas(), carregar_config()
        tela = self._tela_vagas  # aba, filtros e ordem ficam enquanto o app está aberto
        por_aba = {aba: estado.linhas_vagas(base, candidaturas, aba, config.limiar_salvar) for aba, _ in estado.ABAS_VAGAS}

        abas = tk.Frame(pai, bg=FUNDO)
        abas.pack(fill="x", padx=32, pady=(0, 8))
        for valor, nome in estado.ABAS_VAGAS:
            def trocar(v=valor):
                tela["aba"] = v
                self.mostrar("vagas")
            Botao(abas, f"{nome} · {len(por_aba[valor])}", trocar, "primario" if valor == tela["aba"] else "secundario",
                  padx=12, pady=5).pack(side="left", padx=(0, 6))
        explicacoes = {
            "recomendadas": f"Nota {config.limiar_salvar} ou mais: valem a sua atenção.",
            "outras": f"Nota abaixo de {config.limiar_salvar}: combinam pouco com o seu perfil.",
            "salvas": "As que você guardou para depois.",
            "todas": "Todas as que o agente encontrou, inclusive as que não passaram nos filtros.",
        }
        rotulo(abas, explicacoes[tela["aba"]], F_PEQUENA, SUAVE).pack(side="left", padx=(8, 0))

        linhas = por_aba[tela["aba"]]
        if not linhas:
            vazio = cartao(pai, padx=24, pady=24)
            vazio.pack(fill="x", padx=32, pady=10)
            rotulo(vazio, "Nenhuma vaga aqui ainda.", F_SUBTITULO, bg=CARTAO).pack(anchor="w")
            dica = ("Veja a aba \"Outras\" ou clique em \"Buscar vagas agora\"." if tela["aba"] == "recomendadas" else
                    "Clique em \"Buscar vagas agora\" ou veja a aba \"Todas\".")
            rotulo(vazio, dica, F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w")
            return

        filtros = tk.Frame(pai, bg=FUNDO)
        filtros.pack(fill="x", padx=32, pady=(0, 8))
        rotulo(filtros, "Procurar:", F_NORMAL, SUAVE).pack(side="left")
        texto = tk.StringVar(value=tela["texto"])
        campo = ttk.Entry(filtros, textvariable=texto, width=28, font=F_NORMAL)
        campo.pack(side="left", padx=(6, 14), ipady=2)
        opcoes_modelo = [("", "Qualquer modelo"), *estado.MODELOS_VAGA.items()]
        opcoes_nivel = [("", "Qualquer nível"), *estado.NIVEIS_VAGA.items()]
        escolhas = []
        for opcoes, chave in ((opcoes_modelo, "modelo"), (opcoes_nivel, "nivel")):
            caixa = ttk.Combobox(filtros, state="readonly", width=16, font=F_NORMAL, values=[n for _, n in opcoes])
            caixa.current([v for v, _ in opcoes].index(tela[chave]) if tela[chave] in [v for v, _ in opcoes] else 0)
            caixa.pack(side="left", padx=(0, 8))
            escolhas.append((caixa, opcoes, chave))
        contagem = rotulo(filtros, "", F_PEQUENA, SUAVE)
        contagem.pack(side="right")

        painel = ttk.PanedWindow(pai, orient="vertical")
        painel.pack(fill="both", expand=True, padx=32, pady=(0, 16))
        quadro = cartao(painel)
        detalhe = cartao(painel, padx=18, pady=12)
        painel.add(quadro, weight=1)
        painel.add(detalhe, weight=1)

        colunas = (("nota", "Nota", 64), ("titulo", "Vaga", 300), ("empresa", "Empresa", 150), ("local", "Local", 150),
                   ("encontrada", "Encontrada", 92), ("situacao", "Situação", 120))
        nomes = {c: n for c, n, _ in colunas}
        tabela = ttk.Treeview(quadro, columns=list(nomes), show="headings", selectmode="extended")

        def ordenar(coluna: str) -> None:
            atual, decrescente = tela["ordem"]
            tela["ordem"] = (coluna, not decrescente if atual == coluna else coluna in ("nota", "encontrada"))
            preencher()

        for chave, nome, largura in colunas:
            tabela.heading(chave, text=nome, anchor="w", command=lambda c=chave: ordenar(c))
            tabela.column(chave, width=largura, minwidth=50, anchor="center" if chave == "nota" else "w",
                          stretch=chave == "titulo")
        tabela.tag_configure("alta", foreground=DESTAQUE)
        tabela.tag_configure("baixa", foreground=SUAVE)
        tabela.tag_configure("golpe", foreground=PERIGO)
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=tabela.yview)
        tabela.configure(yscrollcommand=rolagem.set)
        rolagem.pack(side="right", fill="y")
        tabela.pack(fill="both", expand=True)

        def preencher(*_args) -> None:
            tela["texto"] = texto.get()
            for caixa, opcoes, chave in escolhas:
                tela[chave] = opcoes[max(0, caixa.current())][0]
            mostradas = estado.ordenar_linhas(
                estado.filtrar_linhas(linhas, tela["texto"], tela["modelo"], tela["nivel"]), *tela["ordem"])
            antes = [i for i in tabela.selection()]
            tabela.delete(*tabela.get_children())
            for l in mostradas:
                tag = ("golpe" if l.alerta else "alta" if l.nota >= config.limiar_candidatar else
                       "baixa" if l.nota < config.limiar_salvar else "")
                tabela.insert("", "end", iid=l.id, tags=(tag,), values=(
                    l.nota_texto, l.titulo, l.empresa, l.local, estado.quando_encontrada(l.encontrada), l.situacao))
            coluna, decrescente = tela["ordem"]
            for chave, nome in nomes.items():
                tabela.heading(chave, text=nome + ((" ▼" if decrescente else " ▲") if chave == coluna else ""))
            contagem.configure(text=f"{len(mostradas)} de {len(linhas)} vaga(s)")
            manter = [i for i in antes if tabela.exists(i)]
            if manter:
                tabela.selection_set(manter)
            elif mostradas:
                tabela.selection_set(mostradas[0].id)
                tabela.focus(mostradas[0].id)
            else:
                self._detalhe_vaga(detalhe, base, [], config)

        tabela.bind("<<TreeviewSelect>>", lambda _e: self._detalhe_vaga(detalhe, base, list(tabela.selection()), config))
        texto.trace_add("write", preencher)
        for caixa, _opcoes, _chave in escolhas:
            caixa.bind("<<ComboboxSelected>>", preencher)
        preencher()

    def _detalhe_vaga(self, quadro, base, ids: list[str], config) -> None:
        """Painel embaixo da lista: a vaga escolhida (ou as escolhidas) e o que dá para fazer com ela."""
        for filho in quadro.winfo_children():
            filho.destroy()
        if not ids:
            rotulo(quadro, "Clique numa vaga para ver os detalhes aqui.", F_NORMAL, SUAVE, bg=CARTAO).pack(anchor="w")
            return
        if len(ids) > 1:
            rotulo(quadro, f"{len(ids)} vagas selecionadas", F_SUBTITULO, bg=CARTAO).pack(anchor="w")
            rotulo(quadro, "Na candidatura, elas abrem no site uma de cada vez: o agente preenche seus dados e anexa o "
                   "currículo; você confere e clica em ENVIAR. Dica: Ctrl ou Shift + clique escolhe várias.",
                   F_NORMAL, SUAVE, bg=CARTAO, wraplength=760).pack(anchor="w", pady=(2, 10))
            botoes = tk.Frame(quadro, bg=CARTAO)
            botoes.pack(anchor="w")
            Botao(botoes, f"Candidatar às {len(ids)} selecionadas", lambda: self._candidatar_varias(ids),
                  "primario").pack(side="left")
            Botao(botoes, f"Salvar as {len(ids)} para depois", lambda: self._salvar_vagas(ids)).pack(side="left", padx=8)
            return
        try:
            vaga = base.buscar(ids[0])
        except ValueError:
            return
        topo = tk.Frame(quadro, bg=CARTAO)
        topo.pack(fill="x")
        rotulo(topo, vaga.titulo, F_SUBTITULO, bg=CARTAO, wraplength=900).pack(anchor="w")
        rotulo(topo, estado.resumo_da_vaga(vaga), F_NORMAL, SUAVE, bg=CARTAO, wraplength=900).pack(anchor="w")

        # Os botões numa linha, presos embaixo: o texto da nota nunca os empurra para fora do painel.
        botoes = tk.Frame(quadro, bg=CARTAO)
        botoes.pack(side="bottom", fill="x", pady=(10, 0))
        Botao(botoes, "Quero me candidatar", lambda: self._candidatar(vaga.id), "primario").pack(side="left")
        Botao(botoes, "Abrir no site", lambda: self._abrir_link(vaga.link)).pack(side="left", padx=6)
        Botao(botoes, "Ver currículo desta vaga", lambda: self._ver_curriculo(vaga.id)).pack(side="left", padx=(0, 6))
        if vaga.status != "salva":
            Botao(botoes, "Salvar para depois", lambda: self._salvar_vagas([vaga.id])).pack(side="left")
        Botao(botoes, "Não tenho interesse", lambda: self._sem_interesse(vaga.id), "perigo").pack(side="left", padx=6)

        corpo = tk.Frame(quadro, bg=CARTAO)
        corpo.pack(fill="both", expand=True, pady=(8, 0))
        esquerda = tk.Frame(corpo, bg=CARTAO, width=430)
        esquerda.pack(side="left", fill="y", padx=(0, 16))
        esquerda.pack_propagate(False)
        estimada = bool(vaga.aderencia and vaga.aderencia.estimada)
        frase = estado.frase_da_nota(vaga.nota, estimada, config.limiar_candidatar, config.limiar_salvar)
        cor = DESTAQUE if vaga.nota >= config.limiar_candidatar and not estimada else TEXTO
        rotulo(esquerda, f"Nota {'≈' if estimada else ''}{vaga.nota} — {frase}", F_NEGRITO, cor, bg=CARTAO,
               wraplength=420).pack(anchor="w")
        for linha in estado.explicar_nota(vaga.aderencia):
            rotulo(esquerda, linha, F_PEQUENA, SUAVE, bg=CARTAO, wraplength=420).pack(anchor="w", pady=(2, 0))
        for sinal in vaga.sinais:
            rotulo(esquerda, f"⚠ {sinal.mensagem}", F_PEQUENA, PERIGO if sinal.gravidade == "forte" else ATENCAO,
                   bg=CARTAO, wraplength=420).pack(anchor="w", pady=(2, 0))

        direita = tk.Frame(corpo, bg=CARTAO)
        direita.pack(side="left", fill="both", expand=True)
        caixa = tk.Text(direita, font=F_PEQUENA, wrap="word", bg="#f8fafc", fg=TEXTO, relief="flat", padx=10, pady=8,
                        height=6, cursor="arrow")
        barra = ttk.Scrollbar(direita, orient="vertical", command=caixa.yview)
        caixa.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        caixa.pack(fill="both", expand=True)
        caixa.insert("1.0", (vaga.descricao or "").strip() or
                     "A descrição desta vaga ainda não foi lida. Clique em \"Abrir no site\" para ver o anúncio; "
                     "a próxima busca tenta ler a descrição sozinha.")
        caixa.configure(state="disabled")

    # -- ações rápidas sobre vagas (sem janela de texto)
    def _candidatar(self, vaga_id: str) -> None:
        if messagebox.askyesno(NOME_APP, "A vaga vai abrir no site (LinkedIn, Gupy...), no navegador do agente, com o "
                               "currículo sob medida já pronto.\n\nNo formulário, o agente preenche seus dados e anexa "
                               "o currículo. Você confere, responde o que faltar e clica em ENVIAR. Depois é só fechar "
                               "o navegador. Abrir a vaga?", parent=self.raiz):
            self.executar("Candidatar-me", ["candidatar", vaga_id, "--direto"])

    def _candidatar_varias(self, ids: list[str]) -> None:
        from ...candidaturas import carregar_candidaturas
        from ...configuracao import carregar_configuracao

        limite = carregar_configuracao().limites.candidaturas_por_dia
        restantes = estado.vagas_restantes_hoje(carregar_candidaturas(), limite)
        if restantes <= 0:
            messagebox.showinfo(NOME_APP, f"Você já chegou ao limite de {limite} candidaturas de hoje. Amanhã tem mais.",
                                parent=self.raiz)
            return
        escolhidas = ids[:min(restantes, estado.LOTE_MAXIMO)]
        corte = (f"\n\nSó {len(escolhidas)} delas cabem agora (limite de hoje e de cada lote)."
                 if len(escolhidas) < len(ids) else "")
        if messagebox.askyesno(NOME_APP, f"As {len(escolhidas)} vaga(s) vão abrir no site, uma de cada vez. Em cada uma, "
                               "o agente preenche seus dados e anexa o currículo; você confere, clica em ENVIAR e fecha "
                               f"o navegador para ir para a próxima.{corte}\n\nComeçar?", parent=self.raiz):
            self.executar(f"Candidatar às {len(escolhidas)} vagas", [["candidatar", i, "--direto"] for i in escolhidas])

    def _ver_curriculo(self, vaga_id: str) -> None:
        """RF-EV-09: o currículo sob medida desta vaga, para conferir antes de se candidatar."""
        from ...cli_vagas import caminho_cv_da_vaga

        def abrir() -> None:
            pdf = caminho_cv_da_vaga(vaga_id)
            if pdf.is_file() and hasattr(os, "startfile"):
                os.startfile(pdf)
        self.executar("Currículo desta vaga", ["vagas", "curriculo", vaga_id], depois=abrir)

    def _abrir_link(self, link: str | None) -> None:
        if link:
            webbrowser.open(link)
        else:
            messagebox.showinfo(NOME_APP, "Esta vaga não tem link. Ela veio de um e-mail sem o endereço do anúncio.",
                                parent=self.raiz)

    def _salvar_vagas(self, ids: list[str]) -> None:
        from ...radar.acoes import FocoNecessario, salvar_vaga

        foco = None
        salvas = 0
        for vaga_id in ids:
            try:
                salvar_vaga(vaga_id, foco)
            except FocoNecessario:
                r = perguntar(self.raiz, "De que área é esta vaga?", "O agente usa as vagas salvas para ajustar o seu "
                              "currículo para a área certa.",
                              [("foco", "Área", "escolha", list(estado.FOCOS.items()), None, None)], botao="Salvar")
                if not r:
                    break
                foco = r["foco"]
                salvar_vaga(vaga_id, foco)
            except ValueError as erro:
                messagebox.showwarning(NOME_APP, str(erro), parent=self.raiz)
                continue
            salvas += 1
        if salvas:
            self.avisar("Vaga salva ✓ Ela fica na aba \"Salvas\"." if salvas == 1 else f"{salvas} vagas salvas ✓")
            self.atualizar()

    def _sem_interesse(self, vaga_id: str) -> None:
        from ...radar.acoes import aceitar_sugestoes, registrar_feedback

        r = perguntar(self.raiz, "Por que essa vaga não serve?", "O agente aprende com isso e melhora as próximas notas.",
                      [("motivo", "Motivo", "escolha", MOTIVOS_SEM_INTERESSE, "area", None)], botao="Enviar")
        if not r:
            return
        try:
            sugestoes = registrar_feedback(vaga_id, False, r["motivo"], descartar=True)
        except ValueError as erro:
            messagebox.showwarning(NOME_APP, str(erro), parent=self.raiz)
            return
        aceitas = [s for s in sugestoes if messagebox.askyesno(
            NOME_APP, f"Quer que o agente ajuste a busca?\n\n{s.descricao[:1].upper() + s.descricao[1:]}.", parent=self.raiz)]
        aceitar_sugestoes(aceitas)
        self.avisar("Pronto: a vaga saiu da lista e o agente vai levar isso em conta nas próximas notas."
                    + (" Busca ajustada." if aceitas else ""))
        self.atualizar()

    def _adicionar_vaga(self) -> None:
        r = perguntar(self.raiz, "Adicionar vaga por link", "Cole o link de uma vaga que você achou. O agente lê e dá nota.",
                      [("url", "Link da vaga", "texto", None, "", "Ex.: https://empresa.gupy.io/jobs/123")], botao="Adicionar")
        if r and r["url"].strip():
            self.executar("Adicionar vaga", ["vagas", "link", r["url"].strip()])


    def _candidatar_melhores(self) -> None:
        from ...candidaturas import carregar_candidaturas
        from ...configuracao import carregar_configuracao
        from ...radar.modelos import carregar_base, carregar_config

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
        if not messagebox.askyesno(NOME_APP, f"As {len(escolhidas)} vaga(s) vão abrir no site, uma de cada vez:\n\n{lista}"
                                   "\n\nEm cada uma, o agente preenche seus dados e anexa o currículo; você confere, "
                                   "clica em ENVIAR e fecha o navegador para ir para a próxima. Começar?", parent=self.raiz):
            return
        self.executar(f"Candidatar às {len(escolhidas)} melhores", [["candidatar", l.id, "--direto"] for l in escolhidas])
