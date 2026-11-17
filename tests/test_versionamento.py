"""Testes do versionamento do perfil-mestre (RF-PM-06)."""

import pytest

from agente_carreira import storage
from agente_carreira.models import Contato, PerfilMestre
from agente_carreira.versionamento import (
    carregar_versao,
    listar_versoes,
    restaurar_versao,
    resumo_diferencas,
)


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _perfil(objetivo: str) -> PerfilMestre:
    return PerfilMestre(contato=Contato(nome="Samuel", email="s@example.com"), objetivo=objetivo)


def test_primeiro_salvamento_nao_gera_versao(dados_em_tmp):
    storage.salvar_perfil(_perfil("v1"))
    assert listar_versoes(dados_em_tmp) == []


def test_salvamentos_seguintes_arquivam_a_anterior(dados_em_tmp):
    storage.salvar_perfil(_perfil("v1"))
    storage.salvar_perfil(_perfil("v2"))
    storage.salvar_perfil(_perfil("v3"))
    versoes = listar_versoes(dados_em_tmp)
    assert len(versoes) == 2
    # Mais recente primeiro: a última arquivada era a v2.
    assert carregar_versao(versoes[0]).objetivo == "v2"
    assert carregar_versao(versoes[1]).objetivo == "v1"


def test_restaurar_versao_volta_o_conteudo_e_preserva_atual(dados_em_tmp):
    storage.salvar_perfil(_perfil("v1"))
    storage.salvar_perfil(_perfil("v2"))
    alvo = listar_versoes(dados_em_tmp)[0]  # v1
    restaurar_versao(alvo, storage.caminho_perfil())
    assert storage.carregar_perfil().objetivo == "v1"
    # A v2 (que estava ativa) foi arquivada antes da restauração.
    objetivos = {carregar_versao(v).objetivo for v in listar_versoes(dados_em_tmp)}
    assert "v2" in objetivos


def test_resumo_diferencas_entre_versoes(dados_em_tmp):
    storage.salvar_perfil(_perfil("antigo"))
    perfil = _perfil("novo")
    perfil.competencias_tecnicas = ["C#", ".NET"]
    storage.salvar_perfil(perfil)
    storage.salvar_perfil(perfil)  # arquiva a versão "novo"
    versoes = listar_versoes(dados_em_tmp)
    mudancas = resumo_diferencas(versoes[1], versoes[0])
    assert any("objetivo" in m for m in mudancas)
    assert any("competencias_tecnicas: 0 → 2" in m for m in mudancas)
