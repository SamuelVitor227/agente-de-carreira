"""Regras antes de candidatar (UC-06 passo 2; RF-CA-04, RF-CA-05, RN-07, RN-10, RN-12).

Bloqueios duros não têm como passar por cima (vaga repetida, golpe, estágio
sem matrícula, vaga encerrada). Os demais pedem confirmação caso a caso:
mesma empresa e cargo em menos de N dias, limite diário e aderência mínima.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from ..candidaturas import Candidaturas, Etapa
from ..configuracao import Limites
from ..models import PerfilMestre
from ..radar.filtros import eh_estagio, matricula_ativa
from ..radar.texto import jaccard, slug, tokens


@dataclass
class Bloqueio:
    tipo: str
    mensagem: str
    contornavel: bool


def checar_candidatura(
    candidaturas: Candidaturas, vaga, perfil: PerfilMestre, limites: Limites, hoje: date | None = None,
) -> list[Bloqueio]:
    hoje = hoje or date.today()
    bloqueios: list[Bloqueio] = []
    vaga_id = getattr(vaga, "id", None)
    link = getattr(vaga, "link", None)

    # Só conta o que já foi enviado: uma candidatura só preparada (selecionada) é retomada, não repetida.
    ativas = [c for c in candidaturas.itens if c.status not in (Etapa.ENCONTRADA, Etapa.SELECIONADA)]
    if any((vaga_id and c.vaga_id == vaga_id) or (link and c.vaga_link == link) for c in ativas):
        bloqueios.append(Bloqueio("repetida", "Você já se candidatou a esta vaga (RN-10).", False))
    else:
        limite_dias = limites.reaplicar_mesma_empresa_dias
        corte = datetime.now(timezone.utc) - timedelta(days=limite_dias)
        titulo = set(tokens(vaga.titulo))
        for c in ativas:
            mesma_empresa = vaga.empresa and slug(c.empresa) == slug(vaga.empresa)
            if mesma_empresa and jaccard(set(tokens(c.vaga_titulo)), titulo) >= 0.6 and (c.enviada_em or c.criada_em) >= corte:
                bloqueios.append(Bloqueio(
                    "mesma_empresa",
                    f"Você se candidatou a {c.vaga_titulo} na {c.empresa} há menos de {limite_dias} dias (RF-CA-04).", True))
                break

    if getattr(vaga, "risco", False):
        bloqueios.append(Bloqueio("golpe", "A vaga tem indício de golpe ou instrução embutida: não recebe seus dados (RN-12).", False))
    e_estagio = eh_estagio(vaga) if hasattr(vaga, "nivel") else getattr(vaga, "contrato", None) == "estagio"
    if e_estagio and not matricula_ativa(perfil, hoje):
        bloqueios.append(Bloqueio("estagio", "Vaga de estágio sem matrícula ativa no perfil (RN-07).", False))
    if getattr(vaga, "status", None) in ("expirada",):
        bloqueios.append(Bloqueio("encerrada", f"A vaga expirou: {getattr(vaga, 'motivo_expiracao', '')}.", False))

    enviadas_hoje = sum(1 for c in candidaturas.itens if c.enviada_em and c.enviada_em.astimezone().date() == hoje)
    if enviadas_hoje >= limites.candidaturas_por_dia:
        bloqueios.append(Bloqueio("limite_diario",
                                  f"Você já enviou {enviadas_hoje} candidatura(s) hoje (limite {limites.candidaturas_por_dia}, RF-CA-05).", True))
    nota = getattr(vaga, "nota", None)
    if nota is not None and nota < limites.aderencia_minima_candidatura:
        bloqueios.append(Bloqueio("aderencia",
                                  f"Aderência {nota}, abaixo do mínimo de {limites.aderencia_minima_candidatura} (RF-CA-05).", True))
    return bloqueios
