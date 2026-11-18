"""Ações rápidas sobre uma vaga, usadas pela linha de comando e direto pelo app (sem janela de texto).

Todas gravam pelo caminho seguro (arquivos.py): se uma busca estiver rodando, ela não desfaz o que você fez.
"""

from __future__ import annotations

from .aderencia import MOTIVOS_FEEDBACK, SugestaoFiltro, aplicar_feedback, aplicar_sugestao
from .modelos import SINONIMOS_POR_FOCO, Feedback, carregar_base, carregar_config, salvar_base, salvar_config


class FocoNecessario(ValueError):
    """A vaga não diz de que área ela é: é preciso escolher um foco para salvá-la nas vagas-alvo."""


def foco_da_vaga(vaga_id: str) -> str | None:
    vaga = carregar_base().buscar(vaga_id)
    return vaga.busca if vaga.busca in SINONIMOS_POR_FOCO else None


def salvar_vaga(vaga_id: str, foco: str | None = None) -> str:
    """Salva a vaga e a põe nas vagas-alvo que alimentam a otimização do currículo (RF-CV-01). Devolve o foco."""
    from ..vagas import Vaga, carregar_vagas, salvar_vagas

    base = carregar_base()
    vaga = base.buscar(vaga_id)
    foco_final = foco or (vaga.busca if vaga.busca in SINONIMOS_POR_FOCO else None)
    if not foco_final:
        raise FocoNecessario(f"Escolha o foco da vaga: {', '.join(SINONIMOS_POR_FOCO)}.")
    alvo = carregar_vagas()

    def mesma(v) -> bool:  # salvar de novo não duplica a vaga-alvo
        if vaga.link:
            return v.url == vaga.link
        return v.titulo == vaga.titulo and (v.empresa or "") == (vaga.empresa or "")

    if not any(mesma(v) for v in alvo.vagas):
        alvo.vagas.append(Vaga(
            titulo=vaga.titulo, empresa=vaga.empresa, foco=foco_final, url=vaga.link,
            fonte=", ".join(f.origem for f in vaga.fontes), descricao=vaga.descricao or vaga.titulo,
        ))
        salvar_vagas(alvo)
    vaga.status = "salva"
    salvar_base(base)
    return foco_final


def descartar_vaga(vaga_id: str) -> None:
    base = carregar_base()
    base.buscar(vaga_id).status = "descartada"
    salvar_base(base)


def registrar_feedback(vaga_id: str, interessa: bool, motivo: str | None = None, *,
                       descartar: bool = False) -> list[SugestaoFiltro]:
    """Guarda se a vaga interessa e por quê; ajusta os pesos e devolve filtros sugeridos (só valem se aceitos)."""
    if motivo and motivo not in MOTIVOS_FEEDBACK:
        raise ValueError(f"Motivo inválido: {motivo}. Use: {', '.join(MOTIVOS_FEEDBACK)}.")
    base, config = carregar_base(), carregar_config()
    vaga = base.buscar(vaga_id)
    vaga.feedback = Feedback(interessa=interessa, motivo=motivo)
    if descartar:
        vaga.status = "descartada"
    sugestoes = aplicar_feedback(config, vaga, interessa, motivo)
    salvar_config(config)
    salvar_base(base)
    return sugestoes


def aceitar_sugestoes(sugestoes: list[SugestaoFiltro]) -> None:
    if not sugestoes:
        return
    config = carregar_config()
    for sugestao in sugestoes:
        aplicar_sugestao(config, sugestao)
    salvar_config(config)
