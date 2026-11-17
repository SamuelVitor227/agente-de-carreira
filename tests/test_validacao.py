"""Testes da validação de completude e consistência (RF-PM-07)."""

from datetime import date

from agente_carreira.models import Contato, Experiencia, Periodo, PerfilMestre, Vinculo
from agente_carreira.validacao import validar_perfil

HOJE = date(2026, 11, 16)


def _perfil(**kwargs) -> PerfilMestre:
    base = dict(
        contato=Contato(nome="Samuel", email="s@example.com", telefone="(31) 99999-0000"),
        objetivo="Estágio backend",
        resumo="Resumo",
    )
    base.update(kwargs)
    return PerfilMestre(**base)


def _exp(cargo, empresa, inicio, fim=None, **kwargs) -> Experiencia:
    return Experiencia(
        cargo=cargo, empresa=empresa, vinculo=Vinculo.CLT,
        periodo=Periodo(inicio=inicio, fim=fim),
        responsabilidades=kwargs.pop("responsabilidades", ["algo"]),
        **kwargs,
    )


def _codigos(perfil):
    return [p.codigo for p in validar_perfil(perfil, hoje=HOJE)]


def test_datas_sobrepostas_geram_aviso():
    perfil = _perfil(experiencias=[
        _exp("Dev", "A", date(2024, 1, 1), date(2025, 6, 1)),
        _exp("Analista", "B", date(2025, 1, 1), date(2025, 12, 1)),
    ])
    assert "datas-sobrepostas" in _codigos(perfil)


def test_lacuna_longa_e_apontada():
    perfil = _perfil(experiencias=[
        _exp("Dev", "A", date(2022, 1, 1), date(2022, 12, 1)),
        _exp("Analista", "B", date(2024, 6, 1)),
    ])
    assert "lacuna" in _codigos(perfil)


def test_inicio_no_futuro_e_erro():
    perfil = _perfil(experiencias=[_exp("Dev", "A", date(2027, 1, 1))])
    problemas = validar_perfil(perfil, hoje=HOJE)
    assert any(p.codigo == "data-futura" and p.nivel == "erro" for p in problemas)


def test_campos_exigidos_por_plataforma():
    perfil = PerfilMestre(contato=Contato(nome="S", email="s@example.com"))  # sem telefone
    problemas = validar_perfil(perfil, hoje=HOJE)
    gupy = [p for p in problemas if p.codigo == "campo-exigido" and "gupy" in p.mensagem]
    assert gupy and "contato.telefone" in gupy[0].mensagem


def test_cargo_duplicado_apontado():
    perfil = _perfil(experiencias=[
        _exp("Dev", "A", date(2023, 1, 1), date(2023, 6, 1)),
        _exp("Dev", "A", date(2024, 1, 1), date(2024, 6, 1)),
    ])
    assert "cargo-duplicado" in _codigos(perfil)


def test_experiencia_sem_conteudo_apontada():
    perfil = _perfil(experiencias=[
        _exp("Dev", "A", date(2024, 1, 1), responsabilidades=[]),
    ])
    assert "experiencia-vazia" in _codigos(perfil)


def test_perfil_completo_sem_apontamentos():
    perfil = _perfil(
        contato=Contato(nome="S", email="s@example.com", telefone="31999990000", cidade="BH"),
        experiencias=[_exp("Dev", "A", date(2024, 1, 1))],
    )
    assert _codigos(perfil) == []
