"""Deduplicação da mesma vaga vinda de fontes diferentes (RF-VG-05).

Critério: mesmo link canônico; ou mesma empresa + mesmo cargo + mesmo local;
ou mesma empresa com cargo parecido e descrição muito similar. Todas as fontes
ficam registradas na vaga resultante.
"""

from __future__ import annotations

from .modelos import BaseVagas, VagaEncontrada
from .texto import cosseno_contagem, jaccard, slug, tokens

SIMILARIDADE_DESCRICAO = 0.85
CAMPOS_COMPLEMENTARES = (
    "empresa", "local", "modelo", "contrato", "nivel", "salario_min", "salario_max", "publicada_em",
    "valida_ate", "link", "horas_dia", "horas_semana", "anos_experiencia", "idioma",
)


def _cidade(local: str | None) -> str:
    return slug((local or "").split(",")[0].split(" - ")[0].split("(")[0])


def mesma_vaga(a: VagaEncontrada, b: VagaEncontrada) -> bool:
    if a.link and b.link and a.link.rstrip("/") == b.link.rstrip("/"):
        return True
    empresa_a, empresa_b = slug(a.empresa), slug(b.empresa)
    if not empresa_a or empresa_a != empresa_b:
        return False
    cidade_a, cidade_b = _cidade(a.local), _cidade(b.local)
    if cidade_a and cidade_b and cidade_a != cidade_b:
        return False
    ambas_com_descricao = bool(a.descricao and b.descricao)
    if slug(a.titulo) == slug(b.titulo):
        # Mesmo cargo na mesma empresa e cidade; descrições muito diferentes indicam vagas distintas.
        return not ambas_com_descricao or cosseno_contagem(a.descricao, b.descricao) >= 0.5
    return (
        ambas_com_descricao
        and jaccard(set(tokens(a.titulo)), set(tokens(b.titulo))) >= 0.6
        and cosseno_contagem(a.descricao, b.descricao) >= SIMILARIDADE_DESCRICAO
    )


def mesclar(destino: VagaEncontrada, origem: VagaEncontrada) -> bool:
    """Junta a origem no destino; devolve True se a descrição ficou mais completa."""
    for fonte in origem.fontes:
        if not any(f.tipo == fonte.tipo and f.origem == fonte.origem and f.url == fonte.url for f in destino.fontes):
            destino.fontes.append(fonte)
    for campo in CAMPOS_COMPLEMENTARES:
        if getattr(destino, campo) in (None, "") and getattr(origem, campo) not in (None, ""):
            setattr(destino, campo, getattr(origem, campo))
    if origem.publicada_em and destino.publicada_em and origem.publicada_em < destino.publicada_em:
        destino.publicada_em = origem.publicada_em
    destino.ultima_coleta = max(destino.ultima_coleta, origem.ultima_coleta)
    if len(origem.descricao) > len(destino.descricao):
        destino.descricao = origem.descricao
        destino.requisitos_obrigatorios = origem.requisitos_obrigatorios
        destino.requisitos_desejaveis = origem.requisitos_desejaveis
        destino.idiomas_exigidos = origem.idiomas_exigidos
        return True
    return False


def incorporar(base: BaseVagas, novas: list[VagaEncontrada]) -> tuple[list[VagaEncontrada], list[VagaEncontrada], list[VagaEncontrada]]:
    """Adiciona as novas à base. Devolve (adicionadas, enriquecidas por mescla, destino de cada nova)."""
    adicionadas: list[VagaEncontrada] = []
    enriquecidas: list[VagaEncontrada] = []
    destinos: list[VagaEncontrada] = []
    for nova in novas:
        alvo = next((v for v in base.itens if mesma_vaga(v, nova)), None)
        if alvo is None:
            base.itens.append(nova)
            adicionadas.append(nova)
            destinos.append(nova)
            continue
        if mesclar(alvo, nova) and alvo not in enriquecidas:
            enriquecidas.append(alvo)
        destinos.append(alvo)
    return adicionadas, enriquecidas, destinos
