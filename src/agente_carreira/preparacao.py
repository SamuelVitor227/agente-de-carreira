"""Preparação para entrevista (RF-AC-04).

Resumo da empresa (pelo que a vaga diz e pelas suas anotações), requisitos da
vaga × evidências do CV, perguntas prováveis e perguntas para você fazer.
Tudo no motor local; a evidência só vem do perfil-mestre (RN-02).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .candidatar.kit import VagaDoKit
from .models import PerfilMestre
from .radar.aderencia import tecnologias_em
from .radar.extracao import secoes_requisitos
from .respostas import BancoRespostas

PERGUNTAS_PARA_FAZER = [
    "Como é um dia típico de quem ocupa esta vaga, e com quem vou trabalhar mais de perto?",
    "Qual é a stack principal hoje e o que vocês estão planejando mudar ou adotar?",
    "Como funcionam o onboarding e o acompanhamento nos primeiros meses?",
    "Como vocês avaliam o desempenho de quem está começando (estágio/júnior)?",
    "Quais são os próximos passos do processo e o prazo de retorno?",
]


def _norm(texto: str | None) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def evidencias(perfil: PerfilMestre, requisito: str) -> list[str]:
    """Itens do perfil que sustentam o requisito: mesmas tecnologias ou palavras-chave."""
    tecs = {_norm(t) for t in tecnologias_em(requisito)}
    palavras = {p for p in re.findall(r"[a-z]{5,}", _norm(requisito))}
    achadas: list[str] = []

    def casa(texto: str, tecnologias: list[str] | None = None) -> bool:
        if tecs and tecs & {_norm(t) for t in (tecnologias or []) + tecnologias_em(texto)}:
            return True
        return not tecs and bool(palavras & set(re.findall(r"[a-z]{5,}", _norm(texto))))

    for exp in perfil.experiencias:
        if casa(" ".join(exp.responsabilidades + [exp.cargo]), exp.tecnologias):
            achadas.append(f"experiência: {exp.cargo} — {exp.empresa}")
    for proj in perfil.projetos:
        if casa(f"{proj.nome} {proj.descricao or ''}", proj.tecnologias):
            achadas.append(f"projeto: {proj.nome}")
    for conq in perfil.banco_conquistas:
        if casa(f"{conq.descricao} {conq.resultado or ''}", conq.tecnologias):
            achadas.append(f"conquista: {conq.verbo_acao} {conq.descricao}")
    for cert in perfil.certificacoes:
        if casa(f"{cert.nome} {cert.emissor or ''}"):
            achadas.append(f"certificação: {cert.nome}")
    for form in perfil.formacao:
        if casa(form.curso):
            achadas.append(f"formação: {form.curso}")
    if not achadas and tecs and (declaradas := [t for t in perfil.competencias_tecnicas if _norm(t) in tecs]):
        # Só declarada, sem projeto ou experiência: vale, mas sinaliza que falta exemplo concreto.
        achadas.append(f"competência declarada: {', '.join(declaradas)} (prepare um exemplo concreto)")
    return achadas


def _resumo_empresa(vaga: VagaDoKit, anotacoes: str | None) -> list[str]:
    linhas = []
    sobre = re.search(r"(sobre (a|n[oó]s|a empresa)|quem somos)\s*:?\s*\n(.+?)(\n\s*\n|$)", vaga.descricao, re.IGNORECASE | re.DOTALL)
    if sobre:
        linhas.append(" ".join(sobre.group(3).split()))
    elif vaga.descricao:
        linhas.append(" ".join(vaga.descricao.split())[:400] + ("…" if len(vaga.descricao) > 400 else ""))
    if anotacoes:
        linhas.append(f"Suas anotações: {anotacoes}")
    linhas.append("Complete com o site da empresa e as avaliações de entrevistas no Glassdoor (leitura manual).")
    return linhas


@dataclass
class PerguntaTreino:
    """Uma pergunta provável da entrevista, com a dica tirada do seu perfil (RF-EV-21)."""
    texto: str
    dica: str
    chave: str | None = None  # pergunta do banco de respostas (Anexo C), se for uma delas


def _requisitos(vaga: VagaDoKit) -> tuple[list[str], list[str]]:
    obrigatorios, desejaveis = vaga.requisitos_obrigatorios, vaga.requisitos_desejaveis
    if not obrigatorios and not desejaveis:
        obrigatorios, desejaveis = secoes_requisitos(vaga.descricao)
    if not obrigatorios and not desejaveis:
        obrigatorios = tecnologias_em(f"{vaga.titulo}\n{vaga.descricao}")
    return list(obrigatorios), list(desejaveis)


def perguntas_provaveis(perfil: PerfilMestre, vaga: VagaDoKit) -> list[PerguntaTreino]:
    """As perguntas que provavelmente vão aparecer, cada uma com o que o seu perfil tem para responder."""
    obrigatorios, desejaveis = _requisitos(vaga)
    perguntas: list[PerguntaTreino] = []
    for tec in list(dict.fromkeys(t for r in obrigatorios for t in tecnologias_em(r)))[:5]:
        achadas = evidencias(perfil, tec)
        perguntas.append(PerguntaTreino(
            f"Conte sobre um projeto em que você usou {tec}. O que fez, que problema resolveu e o que aprendeu?",
            ("No seu perfil: " + "; ".join(achadas[:2])) if achadas else
            f"Não há {tec} no seu perfil: diga com honestidade o que sabe e como aprenderia (sem inventar)."))
    resumo = (perfil.resumo or perfil.objetivo or "").strip()
    perguntas += [
        PerguntaTreino("Fale sobre você em 60 segundos.",
                       "Comece pelo curso e pelo que você quer; feche com um projeto seu. " + (f"Seu resumo: {resumo[:200]}" if resumo else ""),
                       "apresentacao_60s"),
        PerguntaTreino("Conte uma situação difícil num trabalho em equipe e como resolveu.",
                       "Use o formato situação, tarefa, ação e resultado (STAR), com um caso real."),
        PerguntaTreino("Qual foi o maior desafio técnico que você enfrentou e como resolveu?",
                       "Escolha um problema de um projeto seu, o que você tentou e o resultado (com número, se tiver).",
                       "maior_desafio"),
        PerguntaTreino(f"Por que você quer trabalhar{f' na {vaga.empresa}' if vaga.empresa else ' aqui'}?",
                       "Junte algo concreto da empresa ou da vaga com o que você quer aprender.", "por_que_empresa"),
    ]
    sem_evidencia = [r for r in obrigatorios if not evidencias(perfil, r)]
    perguntas += [PerguntaTreino(f"Você não citou {r}. Como faria para aprender rápido?",
                                 "Mostre um caso em que aprendeu algo novo sozinho e em quanto tempo.")
                  for r in sem_evidencia[:3]]
    return perguntas


def material(perfil: PerfilMestre, vaga: VagaDoKit, banco: BancoRespostas | None = None, anotacoes: str | None = None) -> str:
    obrigatorios = vaga.requisitos_obrigatorios
    desejaveis = vaga.requisitos_desejaveis
    if not obrigatorios and not desejaveis:
        obrigatorios, desejaveis = secoes_requisitos(vaga.descricao)
    if not obrigatorios and not desejaveis:
        obrigatorios = tecnologias_em(f"{vaga.titulo}\n{vaga.descricao}")

    linhas = [f"# Preparação — {vaga.titulo}{f' — {vaga.empresa}' if vaga.empresa else ''}", "", "## A empresa", ""]
    linhas += [f"- {l}" for l in _resumo_empresa(vaga, anotacoes)]
    linhas += ["", "## Requisitos da vaga × suas evidências", ""]
    sem_evidencia: list[str] = []
    for tipo, lista in (("obrigatório", obrigatorios), ("desejável", desejaveis)):
        for req in lista:
            achadas = evidencias(perfil, req)
            if achadas:
                linhas.append(f"- **{req}** ({tipo}): " + "; ".join(achadas[:3]))
            else:
                linhas.append(f"- **{req}** ({tipo}): sem evidência no perfil — prepare como vai falar disso, sem inventar")
                sem_evidencia.append(req)
    linhas += ["", "## Perguntas prováveis", ""]
    tecnicas = list(dict.fromkeys(t for r in obrigatorios for t in tecnologias_em(r)))[:5]
    linhas += [f"- Conte sobre um projeto em que você usou {t}. O que fez, que problema resolveu e o que aprendeu?" for t in tecnicas]
    linhas += [
        "- Fale sobre você em 60 segundos.",
        "- Conte uma situação difícil num trabalho em equipe e como resolveu (responda no formato situação, tarefa, ação e resultado).",
        "- Qual foi o maior desafio técnico que você enfrentou e como resolveu?",
        f"- Por que você quer trabalhar{f' na {vaga.empresa}' if vaga.empresa else ' aqui'}?",
    ]
    linhas += [f"- Você não citou {r}. Como faria para aprender rápido?" for r in sem_evidencia[:3]]
    if banco:
        prontas = [(rotulo, banco.resposta(chave)) for chave, rotulo in (
            ("apresentacao_60s", "Apresentação de 60 segundos"), ("maior_desafio", "Maior desafio técnico"),
            ("por_que_empresa", "Por que esta empresa (modelo)"))]
        prontas = [(r, t) for r, t in prontas if t]
        if prontas:
            linhas += ["", "## Suas respostas aprovadas (Anexo C)", ""]
            linhas += [f"- **{r}:** {t}" for r, t in prontas]
    linhas += ["", "## Perguntas para você fazer", ""]
    linhas += [f"- {p}" for p in PERGUNTAS_PARA_FAZER]
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------- simulado de entrevista (RF-EV-21)

ARQUIVO_TREINO = "entrevista-respostas.json"


class RespostaTreino(BaseModel):
    pergunta: str
    resposta: str
    guardada_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TreinoEntrevista(BaseModel):
    """As respostas que você treinou e guardou, por pergunta (valem para as próximas entrevistas)."""
    itens: dict[str, RespostaTreino] = Field(default_factory=dict)

    def resposta(self, pergunta: str) -> str | None:
        item = self.itens.get(_chave_treino(pergunta))
        return item.resposta if item else None


def _chave_treino(pergunta: str) -> str:
    # "Por que você quer trabalhar na Omega?" e "... na Beta?" são a mesma pergunta.
    return re.sub(r"\s+(na|no|em)\s+[^?]+\?$", "?", _norm(pergunta)).strip()


def _caminho_treino() -> Path:
    from .storage import diretorio_dados

    return diretorio_dados() / ARQUIVO_TREINO


def carregar_treino() -> TreinoEntrevista:
    from .arquivos import ler_modelo

    return ler_modelo(_caminho_treino(), TreinoEntrevista)


def guardar_resposta_treino(pergunta: PerguntaTreino, resposta: str) -> None:
    """Guarda a sua resposta; as do Anexo C (apresentação, maior desafio, por que esta empresa) vão também para o
    banco de respostas prontas, que preenche os formulários (guardar aqui é a sua aprovação)."""
    from .arquivos import gravar_modelo
    from .respostas import carregar_respostas, definir_resposta, salvar_respostas

    resposta = resposta.strip()
    if not resposta:
        return
    treino = carregar_treino()
    treino.itens[_chave_treino(pergunta.texto)] = RespostaTreino(pergunta=pergunta.texto, resposta=resposta)
    gravar_modelo(_caminho_treino(), treino)
    if pergunta.chave:
        banco = carregar_respostas()
        definir_resposta(banco, pergunta.chave, resposta)
        salvar_respostas(banco)


def vaga_da_candidatura(candidatura) -> VagaDoKit | None:
    """A vaga de uma candidatura: do kit guardado, ou da base de vagas."""
    from .candidatar.kit import Kit, vaga_do_kit
    from .radar.modelos import carregar_base

    if candidatura.kit_dir and (Path(candidatura.kit_dir) / "kit.json").is_file():
        return Kit.model_validate_json((Path(candidatura.kit_dir) / "kit.json").read_text(encoding="utf-8")).vaga
    if candidatura.vaga_id:
        try:
            return vaga_do_kit(carregar_base().buscar(candidatura.vaga_id))
        except ValueError:
            return None
    return None
