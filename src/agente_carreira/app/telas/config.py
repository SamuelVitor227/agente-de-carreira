"""Tela Configurações: buscas, agendamentos, e-mail, cópias de segurança e atalhos."""

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


class TelaConfig:
    # ---------------------------------------------------------------- configurações

    def _pagina_config(self, pai) -> None:
        from ...configuracao import carregar_configuracao
        from ...operacao.credenciais import email_configurado
        from ...radar.modelos import carregar_config

        corpo = area_rolavel(pai)
        self._cabecalho(corpo, "Configurações", "Ajuste como o agente procura vagas e quando ele trabalha sozinho.")

        config_vagas = carregar_config()
        buscas = config_vagas.buscas
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
        empresas = sorted({e.nome for b in buscas for e in b.empresas_alvo})
        nomes_remoto = {"qualquer": "de qualquer lugar", "brasil": "só de empresas no Brasil", "nao": "nenhuma"}
        from ...operacao.local_dados import servico_de_nuvem
        from ...storage import diretorio_dados

        nuvem = servico_de_nuvem(diretorio_dados())
        itens = [
            ("Vagas remotas: " + nomes_remoto[config_vagas.remoto],
             "Presencial e híbrido valem só em BH e região. Aqui você escolhe que vagas remotas quer receber.",
             "Mudar", self._escolher_remoto, "secundario"),
            ("Empresas que eu quero" + (f" · {len(empresas)}" if empresas else ""),
             (", ".join(empresas[:4]) + ("…" if len(empresas) > 4 else "") + ". ") if empresas else
             "Cadastre empresas onde você quer trabalhar: o agente olha a página de carreira delas em toda busca.",
             "Adicionar empresa", self._adicionar_empresa, "secundario"),
            ("Busca automática todo dia", "O agente procura vagas sozinho todo dia de manhã, sem abrir janela. Se o PC "
             "estiver desligado no horário, a busca roda assim que ele ligar.",
             "Agendar", self._agendar_busca, "secundario"),
            ("Cópias de segurança", "Uma cópia dos seus dados por dia, guardada por 7 dias. Se algo der errado, "
             "volte para um dia anterior.", "Ver cópias", self._copias_seguranca, "secundario"),
            ("Relatório toda semana", "Um resumo da semana no domingo à noite.",
             "Agendar", lambda: self.executar("Agendar relatório semanal", ["relatorio", "agendar"]), "secundario"),
            ("Modo só sugestões: " + ("LIGADO" if sugestao else "desligado"),
             "Ligado, o agente não abre nenhum site: só sugere. Bom para testar com calma.",
             "Desligar" if sugestao else "Ligar",
             lambda: self.executar("Modo só sugestões", ["config", "sugestao", "--desligar" if sugestao else "--ligar"]),
             "secundario"),
            ("Vagas e avisos pelo e-mail", "O agente lê os alertas de vaga do seu e-mail e manda os avisos para ele. "
             "Hoje: " + (email_configurado() or ("Outlook pelo navegador do agente" if central.email_navegador.ativo
                                                 else "não configurado")) + ".",
             "Configurar e-mail", self.configurar_email, "secundario"),
            ("Atalho na Área de Trabalho", "Recria o ícone do agente na sua Área de Trabalho.",
             "Criar atalho", self._criar_atalho, "secundario"),
            ("Pasta dos seus dados", "Onde ficam seu perfil, currículos gerados e relatórios. Nada disso vai para o "
             "GitHub nem para sites." + (f" Atenção: a pasta sincroniza com o {nuvem}." if nuvem else ""),
             "Abrir pasta", self.abrir_pasta_dados, "secundario"),
            *([("Tirar os dados da nuvem", f"Seus dados (inclusive os logins do LinkedIn e do Outlook no navegador do "
                f"agente) estão no {nuvem}. Mova para uma pasta só deste computador.", "Mover para este computador",
                self._mover_dados, "primario")] if nuvem else []),
            ("Fontes de vagas", "Mostra se algum site de vagas mudou ou deu erro.",
             "Verificar", lambda: self.executar("Fontes de vagas", ["saude"]), "secundario"),
            ("Modo avançado", "Abre o terminal com os comandos do agente (para quem é de TI).",
             "Abrir terminal", self._terminal, "secundario"),
        ]
        for i, (titulo, descricao, botao, comando, tipo) in enumerate(itens):
            self._cartao_acao(grade, titulo, descricao, botao, comando, i // 2, i % 2, tipo)
        tk.Frame(corpo, bg=FUNDO, height=20).pack()

    def _copias_seguranca(self) -> None:
        from ... import copias
        from ...operacao import andamento

        copias.garantir_copia_do_dia()
        janela = tk.Toplevel(self.raiz)
        janela.title(f"Cópias de segurança — {NOME_APP}")
        janela.configure(bg=FUNDO, padx=24, pady=20)
        janela.transient(self.raiz)
        rotulo(janela, "Cópias de segurança", F_SUBTITULO).pack(anchor="w")
        rotulo(janela, "O agente guarda uma cópia dos seus dados (perfil, vagas, candidaturas, configurações) por dia, "
               "por 7 dias. Restaurar volta tudo para aquele dia; o estado de agora fica guardado antes, numa cópia "
               "\"antes da restauração\".", F_NORMAL, SUAVE, wraplength=560).pack(anchor="w", pady=(4, 12))
        lista = copias.listar_copias()
        if not lista:
            rotulo(janela, "Ainda não há cópias.", F_NORMAL).pack(anchor="w")

        def restaurar(c) -> None:
            if self.tarefas_rodando() or andamento.em_andamento():
                messagebox.showwarning(NOME_APP, "Há uma tarefa rodando. Espere ela terminar (ou pare-a) antes de "
                                       "restaurar.", parent=janela)
                return
            if not messagebox.askyesno(NOME_APP, f"Voltar os seus dados para a cópia de {c.rotulo}?\n\nO que você fez "
                                       "depois disso sai dos dados, mas fica guardado numa cópia \"antes da "
                                       "restauração\".", parent=janela):
                return
            try:
                restaurados = copias.restaurar(c.nome)
            except (OSError, ValueError) as erro:
                messagebox.showerror(NOME_APP, f"Não deu para restaurar: {erro}", parent=janela)
                return
            messagebox.showinfo(NOME_APP, f"Pronto: {len(restaurados)} arquivo(s) voltaram para {c.rotulo}.",
                                parent=janela)
            janela.destroy()
            self.atualizar()

        for c in lista:
            linha = cartao(janela, padx=14, pady=8)
            linha.pack(fill="x", pady=3)
            rotulo(linha, c.rotulo[:1].upper() + c.rotulo[1:], F_NEGRITO, bg=CARTAO).pack(side="left")
            rotulo(linha, f"  {c.arquivos} arquivo(s) · {c.tamanho / 1024:.0f} KB", F_PEQUENA, SUAVE,
                   bg=CARTAO).pack(side="left")
            Botao(linha, "Restaurar", lambda c=c: restaurar(c), "link").pack(side="right")
        Botao(janela, "Fechar", janela.destroy).pack(anchor="e", pady=(14, 0))

    def _escolher_remoto(self) -> None:
        escolha = escolher(self.raiz, "Vagas remotas", "Qual vaga remota o agente deve recomendar? A lista de vagas é "
                           "refeita na hora com a sua escolha.",
                           [("qualquer", "De qualquer lugar", "secundario"), ("brasil", "Só de empresas no Brasil", "primario"),
                            ("nao", "Nenhuma", "secundario")])
        if escolha:
            self.executar("Vagas remotas", [["vagas", "config", "--remoto", escolha], ["vagas", "reavaliar"]])

    def _adicionar_empresa(self) -> None:
        r = perguntar(self.raiz, "Empresa que eu quero", "O agente olha a página de carreira dela em toda busca e "
                      "avisa quando aparecer vaga que combina com você.",
                      [("nome", "Nome da empresa", "texto", None, "", "Ex.: Localiza"),
                       ("pagina", "Página de vagas (opcional)", "texto", None, "",
                        "Ex.: https://localiza.gupy.io/ — copie da página \"Trabalhe conosco\" da empresa.")],
                      botao="Adicionar")
        if r and r["nome"].strip():
            args = ["busca", "empresa", r["nome"].strip()]
            if r["pagina"].strip():
                args += ["--pagina", r["pagina"].strip()]
            self.executar("Adicionar empresa", args)

    def _mover_dados(self) -> None:
        """RF-EV-19: dados (e logins do navegador do agente) fora do OneDrive."""
        from ...operacao.local_dados import destino_padrao

        if self.tarefas_rodando():
            messagebox.showwarning(NOME_APP, "Há tarefas rodando. Espere terminarem (ou pare-as) antes de mover os dados.",
                                   parent=self.raiz)
            return
        if not messagebox.askyesno(NOME_APP, f"Mover os seus dados para {destino_padrao()}?\n\nO agente copia tudo, "
                                   "confere e só então apaga a pasta antiga (no OneDrive). Feche o navegador do agente "
                                   "antes. Depois você recria o atalho e a busca automática.", parent=self.raiz):
            return

        def depois() -> None:
            from ...operacao.credenciais import carregar_variaveis_do_usuario

            carregar_variaveis_do_usuario()  # este app passa a usar a pasta nova
            try:
                criar_atalho()  # o atalho apontava para a pasta antiga
            except RuntimeError:
                pass
            messagebox.showinfo(NOME_APP, "Pronto: seus dados agora ficam só neste computador. O atalho foi recriado.\n\n"
                                "Feche e abra o app. Depois, recrie a busca automática: Configurações → Busca automática "
                                "todo dia → Agendar.", parent=self.raiz)
        self.executar("Mover os dados", ["dados", "mover"], depois=depois)

    def _agendar_busca(self) -> None:
        r = perguntar(self.raiz, "Busca automática", "A busca roda sem abrir janela. Se o computador estiver desligado "
                      "ou dormindo nesse horário, ela roda assim que ele ligar.",
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
