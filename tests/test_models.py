"""Testes dos modelos do perfil-mestre (RF-PM-01, 03, 04, 05)."""

from datetime import date

import pytest
from pydantic import ValidationError

from agente_carreira.models import (
    Area,
    Conquista,
    Contato,
    Experiencia,
    Periodo,
    PerfilMestre,
    Projeto,
    Vinculo,
)


def _contato() -> Contato:
    return Contato(nome="Samuel Vitor", email="samuel@example.com")


def test_perfil_minimo_valido():
    perfil = PerfilMestre(contato=_contato())
    assert perfil.contato.nome == "Samuel Vitor"
    assert perfil.experiencias == []
    assert perfil.banco_conquistas == []


def test_email_invalido_rejeitado():
    with pytest.raises(ValidationError):
        Contato(nome="X", email="nao-e-email")


def test_periodo_fim_antes_do_inicio_rejeitado():
    with pytest.raises(ValidationError):
        Periodo(inicio=date(2025, 5, 1), fim=date(2024, 1, 1))


def test_periodo_sem_fim_e_atual():
    p = Periodo(inicio=date(2025, 1, 1))
    assert p.atual


def test_experiencia_completa_rf_pm_03():
    exp = Experiencia(
        cargo="Estagiário de desenvolvimento",
        empresa="Empresa X",
        vinculo=Vinculo.ESTAGIO,
        periodo=Periodo(inicio=date(2025, 3, 1)),
        local="Belo Horizonte, MG",
        responsabilidades=["Manter APIs internas"],
        tecnologias=["C#", ".NET"],
    )
    assert exp.area == Area.TI
    assert exp.periodo.atual


def test_experiencia_fora_de_ti_rf_pm_05():
    exp = Experiencia(
        cargo="Atendente",
        empresa="Loja Y",
        vinculo=Vinculo.CLT,
        periodo=Periodo(inicio=date(2022, 1, 1), fim=date(2023, 6, 1)),
        area=Area.FORA_DE_TI,
        competencias_transferiveis=["atendimento", "compras e estoque", "escala de equipe"],
    )
    assert exp.area == Area.FORA_DE_TI
    assert "atendimento" in exp.competencias_transferiveis


def test_projeto_academico_rf_pm_05():
    proj = Projeto(nome="TCC — sistema de recomendação", tipo="academico", tecnologias=["Python"])
    perfil = PerfilMestre(contato=_contato(), projetos=[proj])
    assert perfil.projetos[0].tipo == "academico"


def test_conquista_exige_verbo_de_acao_rf_pm_04():
    with pytest.raises(ValidationError):
        Conquista(verbo_acao="   ", descricao="x")


def test_conquista_com_resultado_e_numero():
    c = Conquista(
        verbo_acao="Reduzi",
        descricao="tempo de busca de produtos no estoque",
        resultado="busca mais rápida",
        numero="30%",
        evidencia="relato do gerente",
    )
    assert c.id  # id gerado automaticamente
    assert c.numero == "30%"


def test_referencia_a_conquista_inexistente_rejeitada():
    exp = Experiencia(
        cargo="Dev",
        empresa="X",
        vinculo=Vinculo.CLT,
        periodo=Periodo(inicio=date(2024, 1, 1)),
        conquista_ids=["nao-existe"],
    )
    with pytest.raises(ValidationError):
        PerfilMestre(contato=_contato(), experiencias=[exp])


def test_referencia_valida_a_conquista_aceita():
    c = Conquista(verbo_acao="Automatizei", descricao="deploys")
    exp = Experiencia(
        cargo="Dev",
        empresa="X",
        vinculo=Vinculo.CLT,
        periodo=Periodo(inicio=date(2024, 1, 1)),
        conquista_ids=[c.id],
    )
    perfil = PerfilMestre(contato=_contato(), experiencias=[exp], banco_conquistas=[c])
    assert perfil.experiencias[0].conquista_ids == [c.id]
