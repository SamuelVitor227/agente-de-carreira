"""Frases "a confirmar" e bloqueio de exportação (RF-CV-13, RN-02).

Toda frase nova sem lastro — por exemplo, vinda de uma reescrita com IA —
deve carregar o marcador [A CONFIRMAR]. Enquanto houver marcador no material,
a exportação do CV fica bloqueada; o comando 'agente confirmar' percorre as
pendências para o usuário aprovar (remove o marcador) ou manter.
"""

from __future__ import annotations

from pydantic import BaseModel

from .models import PerfilMestre

MARCADOR = "[A CONFIRMAR]"


class FrasePendente(BaseModel):
    local: str   # onde está (ex.: "resumo", "experiência X › responsabilidade 2")
    texto: str


def frases_pendentes(perfil: PerfilMestre) -> list[FrasePendente]:
    pendentes: list[FrasePendente] = []

    def checar(local: str, texto: str | None) -> None:
        if texto and MARCADOR in texto:
            pendentes.append(FrasePendente(local=local, texto=texto))

    checar("resumo", perfil.resumo)
    checar("objetivo", perfil.objetivo)
    for exp in perfil.experiencias:
        origem = f"experiência {exp.cargo} ({exp.empresa})"
        for i, resp in enumerate(exp.responsabilidades, 1):
            checar(f"{origem} › responsabilidade {i}", resp)
    for proj in perfil.projetos:
        checar(f"projeto {proj.nome} › descrição", proj.descricao)
    for conq in perfil.banco_conquistas:
        checar(f"conquista {conq.id} › descrição", conq.descricao)
        checar(f"conquista {conq.id} › resultado", conq.resultado)
    return pendentes


def confirmar_frase(perfil: PerfilMestre, pendente: FrasePendente) -> None:
    """Remove o marcador da frase confirmada, no campo onde ela está."""
    confirmado = pendente.texto.replace(MARCADOR, "").strip()

    if pendente.local == "resumo":
        perfil.resumo = confirmado
        return
    if pendente.local == "objetivo":
        perfil.objetivo = confirmado
        return
    for exp in perfil.experiencias:
        exp.responsabilidades = [
            confirmado if r == pendente.texto else r for r in exp.responsabilidades
        ]
    for proj in perfil.projetos:
        if proj.descricao == pendente.texto:
            proj.descricao = confirmado
    for conq in perfil.banco_conquistas:
        if conq.descricao == pendente.texto:
            conq.descricao = confirmado
        if conq.resultado == pendente.texto:
            conq.resultado = confirmado


def pendencias_na_variante(variante) -> list[str]:
    """Trechos com marcador dentro de uma variante de CV (bloqueiam exportação)."""
    achados: list[str] = []
    for secao in variante.secoes:
        if secao.paragrafo and MARCADOR in secao.paragrafo:
            achados.append(f"{secao.titulo}: {secao.paragrafo[:80]}…")
        for item in secao.itens:
            for marcador in item.marcadores:
                if MARCADOR in marcador:
                    achados.append(f"{secao.titulo} › {item.titulo}: {marcador[:80]}…")
    return achados
