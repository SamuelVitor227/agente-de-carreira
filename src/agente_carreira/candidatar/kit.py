"""Kit de candidatura (RF-CA-01), respostas de triagem (RF-CA-02) e eliminatórias primeiro (RF-CA-07).

O kit reúne o CV sob medida (RF-CV-11), uma mensagem curta e as respostas às
perguntas de triagem. Respostas vêm do banco aprovado (Anexo C) ou de fatos
do perfil-mestre; o que faltar fica para o usuário — nada é inventado (RN-02,
RN-09). Uma resposta verdadeira que elimina é mostrada como tal: o agente não
"ajusta" a verdade para passar no filtro.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from ..analise.sob_medida import CoberturaVaga, gerar_sob_medida
from ..analise.variantes import VarianteCV
from ..models import PerfilMestre
from ..radar.aderencia import tecnologias_em
from ..radar.extracao import NOMES_NIVEL_IDIOMA, nivel_idioma
from ..radar.filtros import nivel_no_perfil
from ..respostas import BancoRespostas, chave_da_pergunta
from ..vagas import Vaga

LIMITE_MENSAGEM = 700

_ELIMINATORIA = re.compile(
    r"eliminat[oó]ri|obrigat[oó]ri|requisito|imprescind|\bpossui\b|\btem\b|\bvoc[eê] tem\b|est[aá] cursando|"
    r"disponibilidade para (trabalhar )?presencial|aceita|reside em|mora em|pode iniciar|n[ií]vel de ingl[eê]s|"
    r"anos de experi[eê]ncia|cnh",
    re.IGNORECASE,
)


def _norm(texto: str | None) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


class PerguntaTriagem(BaseModel):
    texto: str
    eliminatoria: bool = False
    chave: str | None = None
    resposta: str | None = None
    origem: Literal["banco", "perfil", "sem_resposta", "usuario"] = "sem_resposta"
    alerta: str | None = None


class VagaDoKit(BaseModel):
    """RF-CA-06: a descrição completa da vaga fica guardada junto do que foi enviado."""

    id: str | None = None
    titulo: str
    empresa: str | None = None
    local: str | None = None
    link: str | None = None
    contrato: str | None = None
    descricao: str = ""
    requisitos_obrigatorios: list[str] = Field(default_factory=list)
    requisitos_desejaveis: list[str] = Field(default_factory=list)


class Kit(BaseModel):
    criado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    vaga: VagaDoKit
    variante: VarianteCV
    cobertura: CoberturaVaga
    mudancas_cv: list[str] = Field(default_factory=list)
    mensagem: str
    motor_mensagem: str | None = None   # RF-IA-06
    apresentacao: str | None = None     # "Apresente-se" da Gupy (RF-PL-05)
    perguntas: list[PerguntaTriagem] = Field(default_factory=list)

    @property
    def eliminatorias(self) -> list[PerguntaTriagem]:
        return [p for p in self.perguntas if p.eliminatoria]

    @property
    def sem_resposta(self) -> list[PerguntaTriagem]:
        return [p for p in self.perguntas if not p.resposta]


def parece_eliminatoria(texto: str) -> bool:
    return bool(_ELIMINATORIA.search(texto))


def _sobre_tecnologia(texto: str) -> list[str]:
    if re.search(r"experi[eê]ncia|conhecimento|possui|tem |domina|trabalhou", texto, re.IGNORECASE):
        return tecnologias_em(texto)
    return []


def responder(pergunta: str, perfil: PerfilMestre, banco: BancoRespostas, contrato: str | None = None,
              eliminatoria: bool | None = None) -> PerguntaTriagem:
    """Resposta só do banco aprovado ou de fatos do perfil; sem isso, fica para o usuário (RN-09)."""
    triagem = PerguntaTriagem(texto=pergunta.strip(),
                              eliminatoria=parece_eliminatoria(pergunta) if eliminatoria is None else eliminatoria)
    triagem.chave = chave = chave_da_pergunta(pergunta, contrato)

    if chave and (pronta := banco.resposta(chave)):
        triagem.resposta, triagem.origem = pronta, "banco"
    elif chave == "links":
        todos = {"linkedin": perfil.links.linkedin, "github": perfil.links.github, "portf": perfil.links.portfolio}
        pedidos = [nome for nome in todos if nome in _norm(pergunta)]
        # Pergunta por um link específico só recebe aquele link; nunca outro no lugar.
        links = [todos[n] for n in (pedidos or todos) if todos[n]]
        if links:
            triagem.resposta, triagem.origem = " | ".join(links), "perfil"
    elif chave == "conclusao_curso":
        previsao = next((f.conclusao_prevista for f in perfil.formacao if f.conclusao_prevista), None)
        if previsao:
            triagem.resposta, triagem.origem = previsao, "perfil"
    elif chave == "ingles":
        nivel = nivel_no_perfil(perfil, "ingles")
        registro = next((i for i in perfil.idiomas if "ingl" in _norm(i.idioma)), None)
        if registro:
            triagem.resposta, triagem.origem = registro.nivel, "perfil"
            exigido = nivel_idioma(pergunta)
            if exigido and nivel < exigido:
                triagem.alerta = (f"a vaga pede inglês {NOMES_NIVEL_IDIOMA[exigido]} e o seu é {NOMES_NIVEL_IDIOMA[nivel]}: "
                                  "a resposta verdadeira pode eliminar")
    elif chave == "diversidade":
        triagem.alerta = "pergunta de diversidade: responda só se quiser (o agente não preenche sem sua autorização)"

    if triagem.resposta is None and (tecnologias := _sobre_tecnologia(pergunta)):
        conhecidas = {_norm(t) for t in perfil.competencias_tecnicas}
        conhecidas |= {_norm(t) for e in perfil.experiencias for t in e.tecnologias}
        conhecidas |= {_norm(t) for p in perfil.projetos for t in p.tecnologias}
        tem = [t for t in tecnologias if _norm(t) in conhecidas]
        falta = [t for t in tecnologias if _norm(t) not in conhecidas]
        if tem and not falta:
            evidencias = [p.nome for p in perfil.projetos if any(_norm(t) in {_norm(x) for x in p.tecnologias} for t in tem)]
            triagem.resposta = "Sim" + (f" — projetos: {', '.join(evidencias[:2])}" if evidencias else "")
            triagem.origem = "perfil"
        elif falta:
            triagem.resposta, triagem.origem = "Não", "perfil"
            triagem.alerta = f"sem lastro no perfil para: {', '.join(falta)} — a resposta verdadeira pode eliminar"
    if triagem.resposta is None and triagem.eliminatoria:
        triagem.alerta = triagem.alerta or "eliminatória sem resposta aprovada: responda você antes de tudo"
    return triagem


def mensagem_curta(perfil: PerfilMestre, vaga: VagaDoKit, cobertura: CoberturaVaga) -> str:
    """Mensagem de candidatura só com fatos do perfil (RN-02)."""
    linhas = [f"Olá, equipe{f' da {vaga.empresa}' if vaga.empresa else ''}!", "",
              f"Tenho interesse na vaga de {vaga.titulo}."]
    if perfil.objetivo:
        linhas.append(perfil.objetivo.rstrip(".") + ".")
    conhecidas = {_norm(t) for t in perfil.competencias_tecnicas}
    conhecidas |= {_norm(t) for e in perfil.experiencias for t in e.tecnologias}
    conhecidas |= {_norm(t) for p in perfil.projetos for t in p.tecnologias}
    tecnologias = [t for t in cobertura.atendidos if _norm(t) in conhecidas]  # sem palavras soltas do título
    if tecnologias:
        linhas.append(f"Trabalho com {', '.join(tecnologias[:4])}.")
        projeto = next((p for p in perfil.projetos
                        if {_norm(t) for t in p.tecnologias} & {_norm(t) for t in tecnologias}), None)
        if projeto:
            linhas.append(f"Um exemplo é o projeto {projeto.nome}" + (f" ({', '.join(projeto.tecnologias)})" if projeto.tecnologias else "") + ".")
    linhas += ["", "Meu currículo segue anexo. Agradeço a atenção.", perfil.contato.nome.split()[0]]
    texto = "\n".join(linhas)
    return texto if len(texto) <= LIMITE_MENSAGEM else texto[:LIMITE_MENSAGEM].rsplit(" ", 1)[0]


def vaga_do_kit(vaga) -> VagaDoKit:
    return VagaDoKit(
        id=getattr(vaga, "id", None), titulo=vaga.titulo, empresa=vaga.empresa, local=getattr(vaga, "local", None),
        link=getattr(vaga, "link", None) or getattr(vaga, "url", None), contrato=getattr(vaga, "contrato", None),
        descricao=vaga.descricao or "", requisitos_obrigatorios=list(getattr(vaga, "requisitos_obrigatorios", [])),
        requisitos_desejaveis=list(getattr(vaga, "requisitos_desejaveis", [])),
    )


def montar_kit(
    perfil: PerfilMestre, vaga, perguntas: list[tuple[str, bool | None]], banco: BancoRespostas, *,
    foco: str = "backend-dotnet", idioma: str = "pt", nivel: str = "estagio",
) -> Kit:
    from ..plataformas.pacote import apresentacao_geral

    dados = vaga_do_kit(vaga)
    alvo = Vaga(titulo=dados.titulo, empresa=dados.empresa, foco=foco, descricao=dados.descricao or dados.titulo, url=dados.link)
    sob_medida = gerar_sob_medida(perfil, alvo, foco=foco, idioma=idioma, nivel=nivel)
    respostas = [responder(texto, perfil, banco, dados.contrato, eliminatoria) for texto, eliminatoria in perguntas]
    respostas.sort(key=lambda p: not p.eliminatoria)  # RF-CA-07: eliminatórias antes de tudo
    return Kit(
        vaga=dados, variante=sob_medida.variante, cobertura=sob_medida.cobertura, mudancas_cv=sob_medida.mudancas,
        mensagem=mensagem_curta(perfil, dados, sob_medida.cobertura), apresentacao=apresentacao_geral(perfil, banco),
        perguntas=respostas,
    )


def kit_markdown(kit: Kit) -> str:
    v = kit.vaga
    linhas = [f"# Kit de candidatura — {v.titulo}{f' — {v.empresa}' if v.empresa else ''}", "",
              f"Link: {v.link or '—'}", ""]
    if kit.eliminatorias:
        linhas += ["## Perguntas eliminatórias (confira antes de tudo)", ""]
        for p in kit.eliminatorias:
            linhas.append(f"- **{p.texto}** → {p.resposta or 'SEM RESPOSTA — responda você'}"
                          + (f"  \n  ⚠ {p.alerta}" if p.alerta else ""))
        linhas.append("")
    linhas += ["## Cobertura da vaga pelo CV", "",
               f"- Atendidos: {', '.join(kit.cobertura.atendidos) or '—'}",
               f"- Incluídos no CV: {', '.join(kit.cobertura.incluidos) or '—'}",
               f"- Sem lastro: {', '.join(kit.cobertura.sem_lastro) or '—'}", "",
               f"## Mensagem (escrita por: {kit.motor_mensagem or 'agente (motor local)'})", "", kit.mensagem, ""]
    outras = [p for p in kit.perguntas if not p.eliminatoria]
    if outras:
        linhas += ["## Outras perguntas", ""]
        for p in outras:
            linhas.append(f"- **{p.texto}** → {p.resposta or 'SEM RESPOSTA — responda você'}"
                          + (f" ({p.alerta})" if p.alerta else ""))
        linhas.append("")
    if kit.apresentacao:
        linhas += ["## Apresente-se (Gupy)", "", kit.apresentacao, ""]
    linhas += ["## Descrição completa da vaga", "", v.descricao or "(não coletada)", ""]
    return "\n".join(linhas)
