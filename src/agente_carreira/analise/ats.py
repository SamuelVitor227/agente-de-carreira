"""Nota de compatibilidade com ATS (RF-CV-05).

Avalia estrutura, títulos de seção padrão, termos cobertos e legibilidade no
motor local, guarda o histórico em data/notas-ats.json e mostra o que mudou
em relação à revisão anterior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ..arquivos import gravar_modelo, ler_modelo
from ..models import PerfilMestre
from ..storage import diretorio_dados
from .lacunas import gerar_relatorio
from .ordenacao import ordenar_cv
from .termos import TermoFrequente

ARQUIVO_HISTORICO = "notas-ats.json"

# Títulos de seção que ATS reconhecem bem (a ordenação RF-CV-04 já os usa).
TITULOS_PADRAO = {
    "Resumo", "Formação Acadêmica", "Projetos", "Certificações",
    "Experiência Profissional", "Outras Experiências", "Competências", "Idiomas",
}

TAMANHO_MAXIMO_RESUMO = 600
TAMANHO_MAXIMO_BULLET = 220


class ItemNota(BaseModel):
    criterio: str
    pontos: float
    maximo: float
    detalhe: str | None = None


class NotaATS(BaseModel):
    quando: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    foco: str | None = None
    nivel: str = "estagio"
    total: float = 0
    itens: list[ItemNota] = Field(default_factory=list)


class HistoricoNotas(BaseModel):
    notas: list[NotaATS] = Field(default_factory=list)


def calcular_nota(
    perfil: PerfilMestre, termos: list[TermoFrequente], foco: str | None, nivel: str = "estagio"
) -> NotaATS:
    nota = NotaATS(foco=foco, nivel=nivel)

    # --- Estrutura (30)
    contato_ok = bool(perfil.contato.email) + bool(perfil.contato.telefone) + bool(perfil.contato.cidade)
    nota.itens.append(ItemNota(
        criterio="estrutura: contato completo (e-mail, telefone, cidade)",
        pontos=round(10 * contato_ok / 3, 1), maximo=10,
        detalhe=None if contato_ok == 3 else "faltam dados de contato",
    ))
    nota.itens.append(ItemNota(
        criterio="estrutura: formação presente", pontos=5.0 if perfil.formacao else 0.0, maximo=5,
    ))
    nota.itens.append(ItemNota(
        criterio="estrutura: experiências ou projetos",
        pontos=10.0 if (perfil.experiencias or perfil.projetos) else 0.0, maximo=10,
    ))
    estrutura = ordenar_cv(perfil, nivel=nivel)
    titulos_ok = all(secao.titulo in TITULOS_PADRAO for secao in estrutura.secoes)
    nota.itens.append(ItemNota(
        criterio="estrutura: títulos de seção padrão", pontos=5.0 if titulos_ok else 0.0, maximo=5,
    ))

    # --- Termos cobertos (40)
    if termos:
        relatorio = gerar_relatorio(perfil, termos)
        cobertos = len(relatorio.ja_no_cv)
        nota.itens.append(ItemNota(
            criterio="termos das vagas cobertos no CV",
            pontos=round(40 * cobertos / len(termos), 1), maximo=40,
            detalhe=f"{cobertos} de {len(termos)} termos do conjunto de vagas",
        ))
    else:
        nota.itens.append(ItemNota(
            criterio="termos das vagas cobertos no CV", pontos=0.0, maximo=40,
            detalhe="sem vagas-alvo salvas — adicione com 'agente vaga adicionar'",
        ))

    # --- Legibilidade (30)
    if perfil.resumo:
        resumo_ok = len(perfil.resumo) <= TAMANHO_MAXIMO_RESUMO
        nota.itens.append(ItemNota(
            criterio="legibilidade: resumo presente e enxuto",
            pontos=10.0 if resumo_ok else 5.0, maximo=10,
            detalhe=None if resumo_ok else f"resumo com {len(perfil.resumo)} caracteres (alvo ≤ {TAMANHO_MAXIMO_RESUMO})",
        ))
    else:
        nota.itens.append(ItemNota(
            criterio="legibilidade: resumo presente e enxuto", pontos=0.0, maximo=10, detalhe="sem resumo",
        ))

    bullets = [
        r for e in perfil.experiencias for r in e.responsabilidades
    ] + [c.descricao for c in perfil.banco_conquistas]
    if bullets:
        curtos = sum(1 for b in bullets if len(b) <= TAMANHO_MAXIMO_BULLET)
        nota.itens.append(ItemNota(
            criterio="legibilidade: frases curtas nos marcadores",
            pontos=round(10 * curtos / len(bullets), 1), maximo=10,
            detalhe=None if curtos == len(bullets) else f"{len(bullets) - curtos} marcador(es) acima de {TAMANHO_MAXIMO_BULLET} caracteres",
        ))
    else:
        nota.itens.append(ItemNota(
            criterio="legibilidade: frases curtas nos marcadores", pontos=0.0, maximo=10,
            detalhe="sem responsabilidades nem conquistas registradas",
        ))

    if perfil.banco_conquistas:
        com_numero = sum(1 for c in perfil.banco_conquistas if c.numero)
        nota.itens.append(ItemNota(
            criterio="legibilidade: conquistas quantificadas",
            pontos=round(5 * com_numero / len(perfil.banco_conquistas), 1), maximo=5,
            detalhe=f"{com_numero} de {len(perfil.banco_conquistas)} conquistas com número",
        ))
    else:
        nota.itens.append(ItemNota(
            criterio="legibilidade: conquistas quantificadas", pontos=0.0, maximo=5,
            detalhe="banco de conquistas vazio",
        ))

    pendentes = len(perfil.rascunhos.experiencias) + len(perfil.rascunhos.formacoes)
    nota.itens.append(ItemNota(
        criterio="legibilidade: sem rascunhos pendentes",
        pontos=5.0 if pendentes == 0 else 0.0, maximo=5,
        detalhe=None if pendentes == 0 else f"{pendentes} rascunho(s) pendente(s)",
    ))

    nota.total = round(sum(i.pontos for i in nota.itens), 1)
    return nota


# ---------------------------------------------------------------- histórico

def caminho_historico() -> Path:
    return diretorio_dados() / ARQUIVO_HISTORICO


def carregar_historico() -> HistoricoNotas:
    caminho = caminho_historico()
    return ler_modelo(caminho, HistoricoNotas)


def registrar_nota(nota: NotaATS) -> NotaATS | None:
    """Guarda a nota no histórico e devolve a revisão anterior do mesmo foco, se houver."""
    historico = carregar_historico()
    anterior = next((n for n in reversed(historico.notas) if n.foco == nota.foco), None)
    historico.notas.append(nota)
    caminho = caminho_historico()
    gravar_modelo(caminho, historico)
    return anterior


def comparar(anterior: NotaATS, atual: NotaATS) -> list[str]:
    """O que mudou entre duas revisões (RF-CV-05)."""
    mudancas: list[str] = []
    delta = round(atual.total - anterior.total, 1)
    sinal = "+" if delta >= 0 else ""
    mudancas.append(f"nota total: {anterior.total} → {atual.total} ({sinal}{delta})")
    anteriores = {i.criterio: i for i in anterior.itens}
    for item in atual.itens:
        antigo = anteriores.get(item.criterio)
        if antigo and antigo.pontos != item.pontos:
            mudancas.append(f"{item.criterio}: {antigo.pontos} → {item.pontos}")
    return mudancas
