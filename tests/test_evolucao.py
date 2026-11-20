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


# ---------------------------------------------------------------- RF-EV-01

def test_retorno_de_empresa_pelo_outlook_move_o_funil(monkeypatch):
    from email.message import EmailMessage

    from typer.testing import CliRunner

    from agente_carreira.candidaturas import Candidatura, Candidaturas, Etapa, carregar_candidaturas, salvar_candidaturas
    from agente_carreira.cli import app
    from agente_carreira.configuracao import carregar_configuracao, salvar_configuracao
    from agente_carreira.radar import outlook_web

    cand = Candidatura(vaga_titulo="Desenvolvedor .NET Júnior", empresa="Omega Tecnologia", foco="backend-dotnet",
                       variante="cv")
    cand.mudar_status(Etapa.APLICADA)
    encerrada = Candidatura(vaga_titulo="Dev", empresa="Beta", foco="x", variante="cv")
    encerrada.mudar_status(Etapa.APLICADA)
    encerrada.mudar_status(Etapa.REPROVADO)
    salvar_candidaturas(Candidaturas(itens=[cand, encerrada]))
    assert outlook_web.consultas_de_retorno(carregar_candidaturas()) == ['"Omega Tecnologia"']  # só as abertas

    central = carregar_configuracao()
    central.email_navegador.ativo = True
    salvar_configuracao(central)
    msg = EmailMessage()
    msg["Subject"] = "Omega Tecnologia: próxima etapa do processo"
    msg["Message-ID"] = "<outlook-web-abc>"
    msg.set_content("Olá! Gostaríamos de agendar uma entrevista com o RH para a vaga de Desenvolvedor .NET Júnior "
                    "na Omega Tecnologia.")
    vistos = []
    monkeypatch.setattr(outlook_web, "ler_retornos", lambda col, ja, **k: vistos.append(set(ja)) or ([(msg["Message-ID"], msg)], []))
    monkeypatch.setattr("agente_carreira.navegador.playwright_disponivel", lambda: True)
    resultado = CliRunner().invoke(app, ["funil", "emails"])
    assert resultado.exit_code == 0, resultado.output
    assert carregar_candidaturas().buscar(cand.id).status == Etapa.ENTREVISTA_RH
    CliRunner().invoke(app, ["funil", "emails"])
    assert "<outlook-web-abc>" in vistos[-1]  # o mesmo e-mail não é processado duas vezes


# ---------------------------------------------------------------- RF-EV-19

def test_reconhece_pasta_na_nuvem(monkeypatch, tmp_path):
    from agente_carreira.operacao.local_dados import servico_de_nuvem

    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    assert servico_de_nuvem(tmp_path / "OneDrive" / "Área de Trabalho" / "agente" / "data") == "OneDrive"
    assert servico_de_nuvem(tmp_path / "AppData" / "Local" / "AgenteCarreira" / "data") is None
    assert servico_de_nuvem(tmp_path / "Google Drive" / "x") == "Google Drive"


def test_mover_dados_copia_confere_e_aponta_a_variavel(dados, tmp_path, monkeypatch):
    from agente_carreira.operacao import local_dados
    from agente_carreira.radar.modelos import BaseVagas, VagaEncontrada, carregar_base, salvar_base

    salvar_base(BaseVagas(itens=[VagaEncontrada(id="v1", titulo="Dev")]))
    (dados / "navegador").mkdir()
    (dados / "navegador" / "Cookies").write_bytes(b"x")
    gravadas = {}
    destino = tmp_path.parent / f"{tmp_path.name}-destino" / "data"
    novo = local_dados.mover_dados(destino, gravar_variavel=gravadas.update)
    assert novo == destino.resolve() and gravadas == {"AGENTE_CARREIRA_DATA": str(destino.resolve())}
    assert (destino / "navegador" / "Cookies").is_file() and not dados.exists()
    assert [v.id for v in carregar_base().itens] == ["v1"]  # o agente já lê da pasta nova
    with pytest.raises(local_dados.NaoDaParaMover):
        local_dados.mover_dados(destino, gravar_variavel=gravadas.update)  # já está lá


# ---------------------------------------------------------------- RF-EV-20

def test_dados_dos_graficos_da_tela_relatorios():
    from agente_carreira.candidaturas import Candidatura, Candidaturas, Etapa
    from agente_carreira.radar.modelos import Aderencia, BaseVagas, Fonte

    hoje = date(2026, 11, 20)  # sexta: a semana começa na segunda 16/11
    agora = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    base = BaseVagas(itens=[
        VagaEncontrada(titulo="A", primeira_coleta=agora, aderencia=Aderencia(nota=70),
                       fontes=[Fonte(tipo="pagina", origem="gupy:portal"), Fonte(tipo="pagina", origem="pagina:x.gupy.io")]),
        VagaEncontrada(titulo="B", primeira_coleta=agora - timedelta(days=7), aderencia=Aderencia(nota=55),
                       fontes=[Fonte(tipo="email", origem="linkedin-alerta")]),
        VagaEncontrada(titulo="C", primeira_coleta=agora, aderencia=Aderencia(nota=20),
                       fontes=[Fonte(tipo="email", origem="linkedin-alerta")]),
    ])
    assert estado.vagas_por_semana(base, 3, hoje) == [("02/11", 0), ("09/11", 1), ("16/11", 2)]
    assert estado.vagas_boas_por_fonte(base, 50) == [("Gupy", 1), ("LinkedIn (alertas de e-mail)", 1)]  # sem contar 2x
    a, b = Candidatura(vaga_titulo="X", foco="f", variante="v"), Candidatura(vaga_titulo="Y", foco="f", variante="v")
    for c in (a, b):
        c.mudar_status(Etapa.APLICADA)
    a.mudar_status(Etapa.ENTREVISTA_RH)
    funil = dict(estado.funil_das_candidaturas(Candidaturas(itens=[a, b])))
    assert funil["Enviadas"] == 2 and funil["Em análise"] == 1 and funil["Entrevista RH"] == 1 and funil["Proposta"] == 0


# ---------------------------------------------------------------- RF-EV-21

def test_simulado_de_entrevista_com_dica_e_resposta_guardada():
    from agente_carreira.candidatar.kit import VagaDoKit
    from agente_carreira.models import Projeto
    from agente_carreira.preparacao import carregar_treino, guardar_resposta_treino, perguntas_provaveis
    from agente_carreira.respostas import carregar_respostas

    perfil = _perfil()
    perfil.competencias_tecnicas = ["C#", ".NET"]
    perfil.projetos = [Projeto(nome="SistemaPedidos", descricao="API de pedidos em C# e .NET", tecnologias=["C#", ".NET"])]
    vaga = VagaDoKit(titulo="Desenvolvedor .NET Júnior", empresa="Omega", descricao="Requisitos: C#, Docker.",
                     requisitos_obrigatorios=["C#", "Docker"])
    perguntas = perguntas_provaveis(perfil, vaga)
    textos = [p.texto for p in perguntas]
    assert any("C#" in t for t in textos) and any("Docker" in t for t in textos)
    assert next(p for p in perguntas if "C#" in p.texto).dica.startswith("No seu perfil")
    assert "sem inventar" in next(p for p in perguntas if "projeto em que você usou Docker" in p.texto).dica
    por_que = next(p for p in perguntas if p.chave == "por_que_empresa")
    assert "Omega" in por_que.texto
    guardar_resposta_treino(por_que, "Porque a Omega trabalha com .NET e quero crescer em back-end.")
    assert carregar_treino().resposta("Por que você quer trabalhar na Beta?")  # vale para a próxima empresa
    assert carregar_respostas().resposta("por_que_empresa").startswith("Porque a Omega")


# ---------------------------------------------------------------- RF-EV-11

def test_alerta_so_com_rastreamento_vira_vaga_sem_abrir_descadastro():
    from email.message import EmailMessage

    from agente_carreira.radar.coleta import destino_do_rastreamento, so_links_de_rastreamento, vagas_por_rastreamento

    msg = EmailMessage()
    msg["From"] = "Vagas.com <nao-responda@vagas.com.br>"
    msg["Subject"] = "Nova vaga compatível com você"
    msg.set_content(
        '<p><a href="https://tracking.recomendacao.vagas.com.br/c/1">Estagiário de Desenvolvimento Web</a></p>'
        '<p><a href="https://tracking.recomendacao.vagas.com.br/c/2">Analista de Suporte Júnior</a></p>'
        '<p><a href="https://tracking.recomendacao.vagas.com.br/c/9">Descadastrar deste alerta</a></p>'
        '<p><a href="https://tracking.recomendacao.vagas.com.br/c/8">Ver mais</a></p>', subtype="html")
    assert so_links_de_rastreamento(msg)
    abertos = []
    destinos = {"https://tracking.recomendacao.vagas.com.br/c/1": "https://www.vagas.com.br/vagas/v2615001/estagiario-web?utm=x",
                "https://tracking.recomendacao.vagas.com.br/c/2": "https://www.vagas.com.br/vagas/v2615002/analista"}
    vagas = vagas_por_rastreamento(msg, destino=lambda url: abertos.append(url) or destinos.get(url))
    assert [(v.titulo, v.link) for v in vagas] == [
        ("Estagiário de Desenvolvimento Web", "https://www.vagas.com.br/vagas/v2615001"),
        ("Analista de Suporte Júnior", "https://www.vagas.com.br/vagas/v2615002")]
    assert not any(url.endswith("/9") or url.endswith("/8") for url in abertos)  # descadastro e "ver mais" nunca

    saltos = {"https://t.co/a": (302, "https://click.x.com/b"), "https://click.x.com/b": (301, "/vagas/v123/dev"),
              "https://u.x.com/z": (302, "https://www.vagas.com.br/preferencias/descadastrar")}
    assert destino_do_rastreamento("https://t.co/a", cabecalho=lambda u: saltos.get(u, (200, None))) is None
    saltos["https://click.x.com/b"] = (301, "https://www.vagas.com.br/vagas/v123/dev")
    assert destino_do_rastreamento("https://t.co/a", cabecalho=lambda u: saltos[u]) == "https://www.vagas.com.br/vagas/v123/dev"
    assert destino_do_rastreamento("https://u.x.com/z", cabecalho=lambda u: saltos.get(u, (200, None))) is None
