"""Testes do armazenamento local do perfil-mestre."""

from datetime import date

import pytest

from agente_carreira import storage
from agente_carreira.models import Contato, Experiencia, Periodo, PerfilMestre, Vinculo


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def test_salvar_e_carregar_roundtrip():
    perfil = PerfilMestre(
        contato=Contato(nome="Samuel", email="s@example.com", telefone="(31) 99999-0000"),
        objetivo="Estágio em backend .NET",
        experiencias=[
            Experiencia(
                cargo="Atendente",
                empresa="Loja",
                vinculo=Vinculo.CLT,
                periodo=Periodo(inicio=date(2022, 1, 1), fim=date(2023, 1, 1)),
            )
        ],
    )
    caminho = storage.salvar_perfil(perfil)
    assert caminho.is_file()

    carregado = storage.carregar_perfil()
    assert carregado.contato.nome == "Samuel"
    assert carregado.objetivo == "Estágio em backend .NET"
    assert carregado.experiencias[0].cargo == "Atendente"
    assert carregado.experiencias[0].periodo.fim == date(2023, 1, 1)


def test_carregar_sem_perfil_da_erro_claro():
    with pytest.raises(FileNotFoundError, match="agente perfil criar"):
        storage.carregar_perfil()


def test_salvar_atualiza_carimbo():
    perfil = PerfilMestre(contato=Contato(nome="S", email="s@example.com"))
    antes = perfil.atualizado_em
    storage.salvar_perfil(perfil)
    assert perfil.atualizado_em >= antes
