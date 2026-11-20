"""Requisitos de evolução (RF-EV): avisos na tela, fontes paradas, lembretes, respostas prontas e vagas remotas."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from agente_carreira.app import estado
from agente_carreira.configuracao import Configuracao
from agente_carreira.models import Contato, Formacao, Idioma, Links, PerfilMestre
from agente_carreira.operacao import aviso_windows
from agente_carreira.operacao.notificacoes import notificar
from agente_carreira.operacao.saude import RegistroSaude
from agente_carreira.radar.filtros import avaliar_filtros, motivo_remoto, no_brasil
from agente_carreira.radar.modelos import BuscaSalva, ConfigVagas, VagaEncontrada
from agente_carreira.respostas import ESSENCIAIS, sugestoes_do_perfil


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _perfil() -> PerfilMestre:
    return PerfilMestre(
        contato=Contato(nome="Ana Souza", email="ana@example.com"), resumo="Estudante de SI focada em back-end .NET.",
        links=Links(linkedin="https://www.linkedin.com/in/ana", github="https://github.com/ana"),
        formacao=[Formacao(curso="Sistemas de Informação", instituicao="PUC Minas", status="cursando",
                           conclusao_prevista="2027/1")],
        idiomas=[Idioma(idioma="Inglês", nivel="leitura de documentação técnica")],
    )


# ---------------------------------------------------------------- RF-EV-02

def test_aviso_na_tela_resume_o_texto_e_escapa():
    corpo = "# Resumo de vagas\n\n**3** recomendáveis · https://x.com/vaga\n- Dev <C#> & .NET"
    assert aviso_windows.resumo_curto(corpo) == "Resumo de vagas · 3 recomendáveis · Dev <C#> & .NET"
    xml = aviso_windows.xml_aviso("Resumo", corpo)
    assert "&lt;C#&gt; &amp; .NET" in xml and xml.startswith("<toast>")


def test_aviso_na_tela_chama_o_powershell_sem_janela(monkeypatch):
    monkeypatch.setattr(aviso_windows.sys, "platform", "win32")
    chamadas = []

    class Ok:
        returncode = 0

    assert aviso_windows.avisar_na_tela("t", "c", executar=lambda c, **k: chamadas.append((c, k)) or Ok())
    comando, opcoes = chamadas[0]
    assert comando[0] == "powershell.exe" and "AGENTE_AVISO_XML" in opcoes["env"]


def test_notificacao_tambem_avisa_na_tela():
    avisos = []
    config = Configuracao()
    config.notificacao.canal = "arquivo"
    notificar("resumo_diario", "Resumo", "3 vagas", config, aviso_na_tela=lambda t, c: avisos.append(t) or True)
    assert avisos == ["Resumo"]
    config.notificacao.aviso_na_tela = False
    notificar("resumo_diario", "Resumo", "3 vagas", config, aviso_na_tela=lambda t, c: avisos.append(t) or True)
    assert avisos == ["Resumo"]


# ---------------------------------------------------------------- RF-EV-17 e RF-EV-22

def test_fonte_parada_aparece_em_linguagem_simples():
    saude = RegistroSaude()
    saude.falha("pagina:gupy-portal", "o site mudou: cartões não encontrados", parar=True)
    saude.sucesso("email:outlook-web")
    assert estado.fontes_paradas(saude) == [("pagina:gupy-portal", "Portal da Gupy", "o site mudou: cartões não encontrados")]


def test_lembrete_de_atualizar_pelo_linkedin_a_cada_30_dias():
    agora = datetime(2026, 11, 20, tzinfo=timezone.utc)
    assert estado.lembrete_linkedin(None, agora) is None
    assert estado.lembrete_linkedin(agora - timedelta(days=10), agora) is None
    assert "45 dias" in estado.lembrete_linkedin(agora - timedelta(days=45), agora)


# ---------------------------------------------------------------- RF-EV-06

def test_sugestoes_de_resposta_so_com_fatos_do_perfil():
    config = ConfigVagas(buscas=[BuscaSalva(nome="b", cargos=["desenvolvedor"])])
    sugestoes = sugestoes_do_perfil(_perfil(), config)
    assert sugestoes["conclusao_curso"] == "2027/1 (Sistemas de Informação, PUC Minas)"
    assert sugestoes["ingles"] == "Leitura de documentação técnica"
    assert sugestoes["links"] == "https://www.linkedin.com/in/ana | https://github.com/ana"
    assert "6 horas por dia" in sugestoes["carga_horaria"]
    assert not {"pretensao_estagio", "pretensao_clt", "disponibilidade_inicio"} & set(sugestoes)  # nada inventado
    assert set(ESSENCIAIS) >= {"pretensao_estagio", "disponibilidade_inicio"}


# ---------------------------------------------------------------- RF-EV-14

@pytest.mark.parametrize("local, idioma, esperado", [
    ("Brasil (Remoto)", "pt", True), ("Vitória, ES (Remoto)", "pt", True), ("Lisboa, Portugal", "pt", False),
    ("Germany", "en", False), (None, "en", False), (None, "pt", True), ("Remoto", "pt", True),
])
def test_remota_no_brasil(local, idioma, esperado):
    assert no_brasil(VagaEncontrada(titulo="Dev", local=local, modelo="remoto", idioma=idioma)) is esperado


def test_escolha_sobre_vagas_remotas_elimina_ou_nao():
    from agente_carreira.storage import salvar_perfil

    perfil = _perfil()
    salvar_perfil(perfil)
    vaga = VagaEncontrada(titulo="Desenvolvedor", local="Germany", modelo="remoto", idioma="en")
    config = ConfigVagas(buscas=[BuscaSalva(nome="b", cargos=["desenvolvedor"], idiomas=["pt", "en"])])
    assert not any("remota" in m for m in avaliar_filtros(vaga, config, perfil, date.today())[1])
    config.remoto = "brasil"
    assert any("fora do Brasil" in m for m in avaliar_filtros(vaga, config, perfil, date.today())[1])
    assert motivo_remoto(VagaEncontrada(titulo="Dev", local="Brasil", modelo="remoto"), "nao").startswith("remota")
