"""Validação de completude e consistência do perfil-mestre (RF-PM-07).

Verifica datas sobrepostas, lacunas na linha do tempo, campos exigidos por
plataforma e consistência interna. A checagem de "mesmos cargos e datas em
todos os canais" contra o LinkedIn real chega com o M2 (RF-LI-15); aqui ela
cobre duplicatas e divergências dentro do próprio perfil.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from .models import Experiencia, PerfilMestre

# Campos exigidos por plataforma (Anexo B). É configuração, não código:
# cresce conforme o catálogo de plataformas do M3 (RF-PL-01, RNF-14).
CAMPOS_EXIGIDOS_POR_PLATAFORMA: dict[str, list[str]] = {
    "gupy": ["contato.nome", "contato.email", "contato.telefone", "contato.pais"],
    "linkedin": ["contato.nome", "resumo", "experiencias|formacao"],
}

MESES_DE_LACUNA_TOLERADOS = 6


class Problema(BaseModel):
    nivel: Literal["erro", "aviso", "info"]
    codigo: str
    mensagem: str


def validar_perfil(perfil: PerfilMestre, hoje: date | None = None) -> list[Problema]:
    hoje = hoje or date.today()
    problemas: list[Problema] = []
    problemas += _validar_datas(perfil, hoje)
    problemas += _validar_campos_por_plataforma(perfil)
    problemas += _validar_completude(perfil)
    problemas += _validar_consistencia(perfil)
    ordem = {"erro": 0, "aviso": 1, "info": 2}
    problemas.sort(key=lambda p: ordem[p.nivel])
    return problemas


def _fim_efetivo(exp: Experiencia, hoje: date) -> date:
    return exp.periodo.fim or hoje


def _meses_entre(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _validar_datas(perfil: PerfilMestre, hoje: date) -> list[Problema]:
    problemas: list[Problema] = []
    for exp in perfil.experiencias:
        if exp.periodo.inicio > hoje:
            problemas.append(
                Problema(
                    nivel="erro",
                    codigo="data-futura",
                    mensagem=f"{exp.cargo} — {exp.empresa}: início {exp.periodo.inicio} está no futuro.",
                )
            )

    ordenadas = sorted(perfil.experiencias, key=lambda e: e.periodo.inicio)
    for anterior, atual in zip(ordenadas, ordenadas[1:]):
        fim_anterior = _fim_efetivo(anterior, hoje)
        if atual.periodo.inicio < fim_anterior:
            problemas.append(
                Problema(
                    nivel="aviso",
                    codigo="datas-sobrepostas",
                    mensagem=(
                        f"{anterior.cargo} ({anterior.empresa}) e {atual.cargo} ({atual.empresa}) "
                        f"se sobrepõem entre {atual.periodo.inicio} e {fim_anterior}. "
                        "Confirme se foi simultâneo."
                    ),
                )
            )
        else:
            lacuna = _meses_entre(fim_anterior, atual.periodo.inicio)
            if lacuna > MESES_DE_LACUNA_TOLERADOS:
                problemas.append(
                    Problema(
                        nivel="info",
                        codigo="lacuna",
                        mensagem=(
                            f"Lacuna de {lacuna} meses entre {anterior.cargo} ({anterior.empresa}) "
                            f"e {atual.cargo} ({atual.empresa}). Plataformas podem perguntar sobre o período."
                        ),
                    )
                )
    return problemas


def _campo_preenchido(perfil: PerfilMestre, caminho: str) -> bool:
    if "|" in caminho:  # pelo menos um dos campos
        return any(_campo_preenchido(perfil, parte) for parte in caminho.split("|"))
    alvo: object = perfil
    for parte in caminho.split("."):
        alvo = getattr(alvo, parte, None)
        if alvo is None:
            return False
    if isinstance(alvo, (list, str)):
        return bool(alvo)
    return True


def _validar_campos_por_plataforma(perfil: PerfilMestre) -> list[Problema]:
    problemas: list[Problema] = []
    for plataforma, campos in CAMPOS_EXIGIDOS_POR_PLATAFORMA.items():
        faltando = [c for c in campos if not _campo_preenchido(perfil, c)]
        if faltando:
            problemas.append(
                Problema(
                    nivel="aviso",
                    codigo="campo-exigido",
                    mensagem=f"{plataforma}: campo(s) exigido(s) sem preencher: {', '.join(faltando)}.",
                )
            )
    return problemas


def _validar_completude(perfil: PerfilMestre) -> list[Problema]:
    problemas: list[Problema] = []
    if not perfil.objetivo:
        problemas.append(Problema(nivel="aviso", codigo="sem-objetivo", mensagem="Objetivo profissional vazio."))
    if not perfil.resumo:
        problemas.append(Problema(nivel="aviso", codigo="sem-resumo", mensagem="Resumo vazio."))
    if not perfil.experiencias and not perfil.projetos:
        problemas.append(
            Problema(nivel="aviso", codigo="sem-experiencias", mensagem="Nenhuma experiência nem projeto registrado.")
        )
    for exp in perfil.experiencias:
        if not exp.responsabilidades and not exp.conquista_ids:
            problemas.append(
                Problema(
                    nivel="aviso",
                    codigo="experiencia-vazia",
                    mensagem=f"{exp.cargo} — {exp.empresa}: sem responsabilidades nem conquistas vinculadas.",
                )
            )
    for formacao in perfil.formacao:
        if not formacao.status:
            problemas.append(
                Problema(
                    nivel="info",
                    codigo="formacao-sem-status",
                    mensagem=f"Formação {formacao.curso} ({formacao.instituicao}) sem status (cursando/concluído).",
                )
            )
    pendentes = len(perfil.rascunhos.experiencias) + len(perfil.rascunhos.formacoes)
    if pendentes:
        problemas.append(
            Problema(
                nivel="aviso",
                codigo="rascunhos-pendentes",
                mensagem=f"{pendentes} rascunho(s) de importação aguardando confirmação (agente rascunhos).",
            )
        )
    return problemas


def _validar_consistencia(perfil: PerfilMestre) -> list[Problema]:
    problemas: list[Problema] = []
    vistos: dict[tuple[str, str], Experiencia] = {}
    for exp in perfil.experiencias:
        chave = (exp.cargo.strip().lower(), exp.empresa.strip().lower())
        if chave in vistos:
            outro = vistos[chave]
            detalhe = (
                "com o mesmo período — provável duplicata"
                if outro.periodo == exp.periodo
                else "com períodos diferentes — confirme as datas para manter o mesmo registro em todos os canais"
            )
            problemas.append(
                Problema(
                    nivel="aviso",
                    codigo="cargo-duplicado",
                    mensagem=f"{exp.cargo} — {exp.empresa} aparece mais de uma vez, {detalhe}.",
                )
            )
        else:
            vistos[chave] = exp

    vinculadas = {cid for e in perfil.experiencias for cid in e.conquista_ids} | {
        cid for p in perfil.projetos for cid in p.conquista_ids
    }
    orfas = [c for c in perfil.banco_conquistas if c.id not in vinculadas]
    if orfas:
        problemas.append(
            Problema(
                nivel="info",
                codigo="conquistas-sem-vinculo",
                mensagem=f"{len(orfas)} conquista(s) do banco sem vínculo com experiência ou projeto.",
            )
        )
    return problemas
