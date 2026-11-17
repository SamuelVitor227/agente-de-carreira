"""Fila única de aprovações (RF-OP-05): ações externas e usos de IA, item a item.

A fila é uma visão sobre as pendências que já existem em cada módulo — usos de
IA negados ou criados pela rodada, publicações em rascunho e alterações do
LinkedIn enviadas para a fila — e não uma cópia, para nunca ficar
desatualizada. Cada item pode ser aprovado, editado ou rejeitado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..ia import (
    MOTORES_EXTERNOS,
    autorizar_pendente,
    carregar_usos,
    descartar_pendente,
    salvar_usos,
    trocar_motor_no_prompt,
)
from ..linkedin.estado import carregar_log, registrar_aprovacao, salvar_log
from ..linkedin.limites import LIMITES
from ..linkedin.pendentes import carregar_pendentes, salvar_pendentes
from ..linkedin.propostas import limite_do_campo, validar_texto
from ..linkedin.publicacoes import (
    aprovar_publicacao,
    carregar_publicacoes,
    editar_publicacao,
    rejeitar_publicacao,
    salvar_publicacoes,
    validar_publicacao,
)

PREFIXOS = {"ia": "uso de IA", "post": "publicação", "li": "alteração no LinkedIn"}


@dataclass
class ItemFila:
    id: str
    tipo: str
    titulo: str
    antes: str | None
    depois: str
    criado_em: datetime
    detalhes: list[str] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)


@dataclass
class Decisao:
    mensagem: str
    texto_para_copiar: str | None = None
    arquivo: str | None = None
    proximo_passo: str | None = None
    entrada_log: str | None = None


def listar_fila() -> list[ItemFila]:
    itens: list[ItemFila] = []
    for uso in carregar_usos().pendentes():
        removidos = ", ".join(f"{t} ({q})" for t, q in uso.removidos.items())
        itens.append(ItemFila(
            id=f"ia:{uso.id}", tipo=PREFIXOS["ia"], titulo=f"Uso de IA · {uso.tarefa} · {uso.motor}",
            antes=None, depois=f"Gerar o prompt ({uso.caracteres} caracteres) para colar no {uso.motor.capitalize()}: {uso.descricao}",
            criado_em=uso.pedido_em,
            detalhes=list(uso.dados) + ([f"removidos automaticamente: {removidos}"] if removidos else []),
        ))
    for pub in carregar_publicacoes().itens:
        if pub.status == "rascunho":
            itens.append(ItemFila(
                id=f"post:{pub.id}", tipo=PREFIXOS["post"], titulo=f"Publicação no LinkedIn · {pub.titulo}",
                antes=None, depois=pub.texto, criado_em=pub.criada_em,
                detalhes=[f"{len(pub.texto)}/{LIMITES['publicacao']} caracteres", f"escrito por: {pub.motor or 'agente (local)'}"],
                problemas=validar_publicacao(pub.texto),
            ))
    for alteracao in carregar_pendentes().itens:
        limite = limite_do_campo(alteracao.campo)
        itens.append(ItemFila(
            id=f"li:{alteracao.id}", tipo=PREFIXOS["li"], titulo=f"LinkedIn · {alteracao.rotulo}",
            antes=alteracao.anterior, depois=alteracao.novo, criado_em=alteracao.criada_em,
            detalhes=[f"{len(alteracao.novo)}{f'/{limite}' if limite else ''} caracteres"]
            + ([f"escrito por: {alteracao.motor}"] if alteracao.motor else []),
            problemas=validar_texto(alteracao.campo, alteracao.novo),
        ))
    itens.sort(key=lambda i: i.criado_em)
    return itens


def _separar(id_: str) -> tuple[str, str]:
    prefixo, _, ref = id_.partition(":")
    if prefixo not in PREFIXOS or not ref:
        raise ValueError(f"Item {id_!r} não existe na fila (use o ID mostrado em 'agente fila').")
    return prefixo, ref


def aprovar(id_: str, motor: str | None = None) -> Decisao:
    prefixo, ref = _separar(id_)
    if prefixo == "ia":
        usos = carregar_usos()
        uso = autorizar_pendente(usos, ref, motor=motor)
        salvar_usos(usos)
        return Decisao(
            mensagem=f"Uso de IA autorizado (motor {uso.motor}); prompt gerado.", arquivo=uso.arquivo_prompt,
            proximo_passo=f"Cole o prompt no {uso.motor.capitalize()} e traga a resposta de volta.",
        )
    if prefixo == "post":
        colecao = carregar_publicacoes()
        pub = colecao.buscar(ref)
        aprovar_publicacao(pub)
        salvar_publicacoes(colecao)
        return Decisao(
            mensagem="Publicação aprovada.", texto_para_copiar=pub.texto,
            proximo_passo=f"Publique você mesmo no LinkedIn e rode 'agente li post publicado {pub.id}'.",
        )
    pendentes = carregar_pendentes()
    item = pendentes.buscar(ref)
    if problemas := validar_texto(item.campo, item.novo):
        raise ValueError("; ".join(problemas))
    log = carregar_log()
    entrada = registrar_aprovacao(log, item.campo, item.anterior, item.novo, motor=item.motor)
    salvar_log(log)
    pendentes.itens.remove(item)
    salvar_pendentes(pendentes)
    return Decisao(
        mensagem=f"Alteração aprovada (log {entrada.id}).", texto_para_copiar=item.novo,
        proximo_passo=f"Cole no LinkedIn e rode 'agente li aplicado {entrada.id}'.", entrada_log=entrada.id,
    )


def rejeitar(id_: str) -> Decisao:
    prefixo, ref = _separar(id_)
    if prefixo == "ia":
        usos = carregar_usos()
        descartar_pendente(usos, ref)
        salvar_usos(usos)
        return Decisao(mensagem="Uso de IA rejeitado; nada foi gerado nem enviado.")
    if prefixo == "post":
        colecao = carregar_publicacoes()
        rejeitar_publicacao(colecao.buscar(ref))
        salvar_publicacoes(colecao)
        return Decisao(mensagem="Publicação rejeitada; não será publicada.")
    pendentes = carregar_pendentes()
    pendentes.itens.remove(pendentes.buscar(ref))
    salvar_pendentes(pendentes)
    return Decisao(mensagem="Alteração do LinkedIn rejeitada; nada muda no perfil.")


def editar(id_: str, *, texto: str | None = None, motor: str | None = None) -> Decisao:
    """Edita o item, que continua na fila esperando aprovação."""
    prefixo, ref = _separar(id_)
    if prefixo == "ia":
        if motor not in MOTORES_EXTERNOS:
            raise ValueError("Num uso de IA, a edição é trocar o motor: informe claude ou gemini.")
        usos = carregar_usos()
        uso = usos.buscar(ref)
        if uso.autorizacao != "pendente" or uso.prompt_pendente is None:
            raise ValueError(f"O uso {ref} não está pendente.")
        if motor != uso.motor:
            uso.prompt_pendente, uso.nome_arquivo = trocar_motor_no_prompt(uso.prompt_pendente, uso.nome_arquivo, uso.motor, motor)
            uso.motor = motor
        salvar_usos(usos)
        return Decisao(mensagem=f"Motor trocado para {motor}; o pedido continua na fila.")
    if not texto or not texto.strip():
        raise ValueError("Informe o novo texto.")
    if prefixo == "post":
        colecao = carregar_publicacoes()
        editar_publicacao(colecao.buscar(ref), texto, motor=motor)
        salvar_publicacoes(colecao)
        return Decisao(mensagem="Texto da publicação atualizado; continua na fila.")
    pendentes = carregar_pendentes()
    item = pendentes.buscar(ref)
    item.novo, item.motor = texto.strip(), motor
    salvar_pendentes(pendentes)
    avisos = validar_texto(item.campo, item.novo)
    return Decisao(mensagem="Texto atualizado; continua na fila." + (f" Atenção: {'; '.join(avisos)}." if avisos else ""))
