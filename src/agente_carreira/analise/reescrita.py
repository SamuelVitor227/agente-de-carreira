"""Reescrita do resumo, experiências e projetos (RF-CV-03) em modo copiloto.

Os motores de IA são as assinaturas do usuário (Claude Pro / Gemini Pro), sem
API: o agente monta o pacote de reescrita, mostra exatamente quais dados serão
enviados e para qual motor (RF-IA-02, RN-14), e só gera o prompt após
autorização. O usuário cola o prompt no motor e revisa o resultado; nada é
aplicado ao perfil sem confirmação (RN-01, RN-02).
"""

from __future__ import annotations

from datetime import datetime

from ..models import PerfilMestre
from .termos import TermoFrequente

MOTORES = ("claude", "gemini")


def dados_enviados(perfil: PerfilMestre) -> list[str]:
    """Relação exata do que sai do perfil-mestre no prompt (transparência RF-IA-02)."""
    dados: list[str] = []
    if perfil.objetivo:
        dados.append("objetivo profissional")
    if perfil.resumo:
        dados.append("resumo")
    if perfil.experiencias:
        dados.append(
            f"{len(perfil.experiencias)} experiência(s): cargo, empresa, período, responsabilidades e tecnologias"
        )
    if perfil.projetos:
        dados.append(f"{len(perfil.projetos)} projeto(s): nome, descrição e tecnologias")
    if perfil.banco_conquistas:
        dados.append(f"{len(perfil.banco_conquistas)} conquista(s) do banco")
    dados.append("NÃO são enviados: nome, e-mail, telefone, links e endereço")
    return dados


def montar_prompt(perfil: PerfilMestre, termos: list[TermoFrequente], motor: str) -> str:
    """Monta o prompt de reescrita para o usuário colar no motor escolhido."""
    linhas: list[str] = [
        "# Tarefa: reescrever seções de currículo",
        "",
        "Reescreva o resumo, as experiências e os projetos abaixo no padrão:",
        "**verbo de ação + o que foi feito + resultado (com número quando houver) + tecnologia**.",
        "",
        "Regras obrigatórias:",
        "- NÃO invente nenhum fato, tecnologia, número ou resultado que não esteja no material.",
        "- Use o termo exato das vagas (lista abaixo) SOMENTE quando ele corresponder a algo verdadeiro no material.",
        "- Marque com [A CONFIRMAR] qualquer frase em que você tenha extrapolado ou precise de confirmação.",
        "- Responda em português, em Markdown, mantendo a mesma estrutura de seções.",
        "",
        "## Termos mais frequentes nas vagas-alvo",
        "",
    ]
    for termo in termos:
        linhas.append(f"- {termo.termo} ({termo.vagas_em_que_aparece} de {termo.total_de_vagas} vagas)")

    linhas += ["", "## Material do perfil (fonte da verdade — não acrescentar nada)", ""]
    if perfil.objetivo:
        linhas += ["### Objetivo", perfil.objetivo, ""]
    if perfil.resumo:
        linhas += ["### Resumo atual", perfil.resumo, ""]

    conquistas_por_id = {c.id: c for c in perfil.banco_conquistas}
    for i, exp in enumerate(perfil.experiencias, 1):
        fim = exp.periodo.fim.isoformat() if exp.periodo.fim else "atual"
        linhas.append(f"### Experiência {i}: {exp.cargo} — {exp.empresa} ({exp.periodo.inicio} a {fim})")
        for resp in exp.responsabilidades:
            linhas.append(f"- {resp}")
        for cid in exp.conquista_ids:
            if conq := conquistas_por_id.get(cid):
                partes = [conq.verbo_acao, conq.descricao]
                if conq.resultado:
                    partes.append(f"resultado: {conq.resultado}")
                if conq.numero:
                    partes.append(f"({conq.numero})")
                linhas.append(f"- Conquista: {' '.join(partes)}")
        if exp.tecnologias:
            linhas.append(f"- Tecnologias: {', '.join(exp.tecnologias)}")
        if exp.competencias_transferiveis:
            linhas.append(f"- Competências transferíveis: {', '.join(exp.competencias_transferiveis)}")
        linhas.append("")

    for proj in perfil.projetos:
        linhas.append(f"### Projeto: {proj.nome} ({proj.tipo})")
        if proj.descricao:
            linhas.append(proj.descricao)
        if proj.tecnologias:
            linhas.append(f"- Tecnologias: {', '.join(proj.tecnologias)}")
        linhas.append("")

    linhas += [
        "---",
        f"(Pacote gerado pelo Agente de Carreira em {datetime.now():%d/%m/%Y %H:%M} "
        f"para o motor {motor}; revisão humana obrigatória antes de qualquer uso.)",
    ]
    return "\n".join(linhas)
