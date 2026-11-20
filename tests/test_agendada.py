"""Busca diária agendada: tarefa sem janela, que roda depois se o PC estava desligado, e aviso na tela Início."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agente_carreira.operacao import agendada
from agente_carreira.radar.agenda import NOME_TAREFA


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    monkeypatch.setenv("AGENTE_ORIGEM", "teste")  # rodar() muda essas duas; o monkeypatch desfaz no fim
    monkeypatch.setenv("COLUMNS", "112")
    # rodar() lê as variáveis AGENTE_* do Windows; nos testes, as do seu computador não entram.
    monkeypatch.setattr("agente_carreira.operacao.credenciais.carregar_variaveis_do_usuario", lambda: None)
    return tmp_path


def _registro(dados: Path, **campos) -> None:
    (dados / agendada.ARQUIVO).write_text(json.dumps({"vagas rodada": campos}), encoding="utf-8")


def _iso(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).isoformat(timespec="seconds")


AGORA = datetime(2026, 11, 19, 12, 0).astimezone()


def test_sem_tarefa_nao_mostra_nada():
    assert agendada.situacao(False, "07:00", AGORA) is None
    assert agendada.situacao(None, "07:00", AGORA) is None


def test_tarefa_antiga_pede_para_recriar(dados):
    s = agendada.situacao(True, "07:00", AGORA)
    assert s.problema and "versão antiga" in s.texto


def test_busca_que_rodou_hoje(dados):
    _registro(dados, instalada_em=_iso(AGORA - timedelta(days=2)), hora="07:00",
              inicio=_iso(AGORA.replace(hour=7, minute=0)), fim=_iso(AGORA.replace(hour=7, minute=4)), codigo=0)
    s = agendada.situacao(True, "07:00", AGORA)
    assert not s.problema and s.texto.endswith("última: hoje às 07:04 ✓")


def test_busca_que_nao_rodou_avisa(dados):
    _registro(dados, instalada_em=_iso(AGORA - timedelta(days=3)), hora="07:00",
              inicio=_iso(AGORA - timedelta(days=2)), fim=_iso(AGORA - timedelta(days=2)), codigo=0)
    s = agendada.situacao(True, "07:00", AGORA)
    assert s.problema and "não rodou" in s.texto and "19/11" in s.texto


def test_busca_com_erro_avisa(dados):
    _registro(dados, instalada_em=_iso(AGORA - timedelta(days=2)), hora="07:00",
              inicio=_iso(AGORA.replace(hour=7)), fim=_iso(AGORA.replace(hour=7, minute=1)), codigo=1)
    s = agendada.situacao(True, "07:00", AGORA)
    assert s.problema and "erro" in s.texto


def test_recem_criada_diz_quando_sera_a_primeira(dados):
    _registro(dados, instalada_em=_iso(AGORA - timedelta(hours=1)), hora="07:00")
    s = agendada.situacao(True, "07:00", AGORA)
    assert not s.problema and "a primeira será 20/11 às 07:00" in s.texto


def test_instalar_cria_a_tarefa_pelo_xml_e_tira_o_script_antigo(dados, monkeypatch):
    monkeypatch.setattr(agendada, "lancador_tarefa", lambda: (Path("C:/Python/pythonw.exe"), dados / "app" / "tarefa.pyw"))
    (dados / "rodada-vagas.cmd").write_text("@echo off", encoding="utf-8")
    chamadas = []

    class Ok:
        returncode, stdout, stderr = 0, "", ""

    xml = agendada.instalar(NOME_TAREFA, ["vagas", "rodada"], "07:00", executar=lambda c, **_k: chamadas.append(c) or Ok())
    conteudo = xml.read_text(encoding="utf-16")
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in conteudo and "vagas rodada" in conteudo
    assert chamadas[0][:4] == ["schtasks", "/Create", "/TN", NOME_TAREFA] and str(xml) in chamadas[0]
    assert not (dados / "rodada-vagas.cmd").exists()
    assert agendada.ler()["vagas rodada"]["hora"] == "07:00"


def test_instalar_mostra_o_erro_do_agendador(dados, monkeypatch):
    monkeypatch.setattr(agendada, "lancador_tarefa", lambda: (Path("C:/Python/pythonw.exe"), dados / "app" / "tarefa.pyw"))

    class Falha:
        returncode, stdout, stderr = 1, "", "ERRO: Acesso negado."

    with pytest.raises(RuntimeError, match="Acesso negado"):
        agendada.instalar(NOME_TAREFA, ["vagas", "rodada"], "07:00", executar=lambda *_a, **_k: Falha())


def test_rodar_grava_o_log_e_o_resultado(dados):
    import sys

    saida_antes = sys.stdout
    codigo = agendada.rodar(["andamento"])
    assert sys.stdout is saida_antes  # devolve a saída de volta
    assert codigo == 0
    log = (dados / "agendada.log").read_text(encoding="utf-8")
    assert "agente andamento (automática)" in log and "fim: código 0" in log
    registro = agendada.ler()["andamento"]
    assert registro["codigo"] == 0 and registro["fim"]
