"""Testes do M7 (RF-RL-01 a RF-RL-03, RNF-15, UC-11) e do portão da fase 2 (CA-11, CA-12)."""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agente_carreira.aceite import GOLPES_DE_TESTE, _ca11, _ca12, verificar_fase2
from agente_carreira.candidaturas import Candidatura, Candidaturas, Etapa
from agente_carreira.funil import Lembretes, atualizar_lembretes
from agente_carreira.ia import UsoIA, UsosIA
from agente_carreira.operacao.saude import RegistroSaude
from agente_carreira.plataformas.contas import ContaPlataforma, Contas
from agente_carreira.radar.agenda import linha_cron_semanal, proxima_vez, validar_dia_hora, xml_tarefa
from agente_carreira.radar.modelos import Aderencia, BaseVagas, Fonte, RegistroRodada, Sinal, VagaEncontrada
from agente_carreira.relatorios import (
    competencias_que_faltam,
    exportar,
    montar_painel,
    painel_html,
    relatorio_markdown,
    relatorio_semanal,
    teve_retorno,
)

AGORA = datetime(2026, 11, 15, 20, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _vaga(id_, origem, busca="backend-dotnet", dias=1, nota=70, lacunas=(), status="no_resumo", **kw):
    return VagaEncontrada(id=id_, titulo=f"Vaga {id_}", empresa=f"Empresa {id_}", busca=busca, status=status,
                          fontes=[Fonte(tipo="email", origem=origem)], primeira_coleta=AGORA - timedelta(days=dias),
                          aderencia=Aderencia(nota=nota, lacunas=list(lacunas)), **kw)


def _cand(vaga_id, variante, etapas, foco="backend-dotnet", dias=2, motivo=None):
    c = Candidatura(vaga_id=vaga_id, vaga_titulo=f"Vaga {vaga_id}", empresa=f"Empresa {vaga_id}", foco=foco,
                    variante=variante, status=Etapa.ENCONTRADA)
    for etapa in etapas:
        c.mudar_status(etapa, motivo=motivo if etapa in (Etapa.REPROVADO, Etapa.DESISTENCIA) else None)
    c.enviada_em = AGORA - timedelta(days=dias)
    for m in c.historico:
        m.quando = AGORA - timedelta(days=dias)
    return c


@pytest.fixture
def cenario():
    base = BaseVagas(itens=[
        _vaga("a1", "linkedin-alerta", lacunas=["Docker", "Azure"]),
        _vaga("a2", "linkedin-alerta", lacunas=["Docker"]),
        _vaga("g1", "pagina:omega.gupy.io", lacunas=["Docker", "Kubernetes"]),
        _vaga("g2", "pagina:omega.gupy.io", nota=90),                      # boa e sem candidatura
        _vaga("v1", "linkedin-alerta", busca="dados", dias=20, lacunas=["Power BI"]),
        _vaga("x1", "linkedin-alerta", nota=95, status="eliminada", lacunas=["COBOL"],
              sinais=[Sinal(tipo="golpe:pix", mensagem="pede Pix")]),
    ], rodadas=[RegistroRodada(inicio=AGORA - timedelta(days=1, minutes=3), fim=AGORA - timedelta(days=1),
                               coletadas=12, novas=4, recomendadas=2, erros=1)])
    S, A, R = Etapa.SELECIONADA, Etapa.APLICADA, Etapa.REPROVADO
    cands = Candidaturas(itens=[
        _cand("a1", "cv-backend-pt", [S, A, Etapa.EM_ANALISE, Etapa.ENTREVISTA_RH]),
        _cand("a2", "cv-backend-pt", [S, A, R], motivo="inglês"),
        _cand("g1", "cv-backend-pt", [S, A, Etapa.PROPOSTA]),
        _cand("v1", "cv-dados-pt", [S, A, R], foco="dados", dias=20, motivo="sem retorno"),
        Candidatura(vaga_id="g2", vaga_titulo="Vaga g2", foco="backend-dotnet", variante="cv-backend-pt"),  # só preparada
    ])
    return base, cands


# ---------------------------------------------------------------- RF-RL-01

def test_retorno_conta_reprovacao_mas_nao_falta_de_resposta(cenario):
    _, cands = cenario
    assert [teve_retorno(c) for c in cands.itens[:4]] == [True, True, True, False]


def test_painel_por_fonte_foco_e_variante(cenario):
    base, cands = cenario
    usos = UsosIA(itens=[UsoIA(tarefa="t", descricao="d", motor="claude", autorizacao="aprovado", nome_arquivo="x"),
                         UsoIA(tarefa="t", descricao="d", motor="gemini", autorizacao="descartado", nome_arquivo="y")])
    saude = RegistroSaude()
    saude.obter("gupy").status = "parado"
    p = montar_painel(base, cands, usos_ia=usos, saude=saude)
    t = p.total
    assert (t.vagas, t.candidaturas, t.retornos, t.entrevistas, t.propostas) == (6, 4, 3, 1, 1)   # preparada não conta
    assert t.taxa_retorno == 75
    fontes = {l.grupo: l for l in p.por_fonte}
    assert (fontes["linkedin-alerta"].vagas, fontes["linkedin-alerta"].candidaturas) == (4, 3)
    assert (fontes["pagina:omega.gupy.io"].candidaturas, fontes["pagina:omega.gupy.io"].propostas) == (1, 1)
    assert {l.grupo: l.candidaturas for l in p.por_variante} == {"cv-backend-pt": 3, "cv-dados-pt": 1}
    assert {l.grupo for l in p.por_foco} == {"backend-dotnet", "dados"}
    assert p.motivos_saida == [("Reprovado: inglês", 1), ("Reprovado: sem retorno", 1)]
    e = p.execucao
    assert (e.rodadas, e.coletadas, e.erros, e.duracao_media_s) == (1, 12, 1, 180.0)
    assert e.uso_ia == {"claude": 1} and e.adaptadores_parados == ["gupy"]


def test_painel_filtra_periodo(cenario):
    base, cands = cenario
    p = montar_painel(base, cands, desde=AGORA - timedelta(days=7))
    assert p.total.vagas == 5 and p.total.candidaturas == 3


def test_painel_html_autocontido_e_escapado(cenario):
    base, cands = cenario
    cands.itens[0].variante = "<script>alert(1)</script>"
    pagina = painel_html(montar_painel(base, cands), gerado_em=AGORA)
    assert pagina.startswith("<!doctype html>") and "prefers-color-scheme: dark" in pagina
    assert "<script>" not in pagina and "&lt;script&gt;" in pagina
    assert "http" not in pagina                                   # sem recursos externos
    assert "75%" in pagina


# ---------------------------------------------------------------- RF-RL-02

def test_lacunas_mais_pedidas_ignoram_eliminadas(cenario):
    base, _ = cenario
    contagem, total = competencias_que_faltam(base.itens)
    assert contagem[0] == ("Docker", 3) and total == 5
    assert "COBOL" not in dict(contagem)


def test_relatorio_semanal_numeros_funcionou_lacunas_e_acoes(cenario):
    base, cands = cenario
    lembretes = Lembretes()
    atualizar_lembretes(lembretes, cands.itens[1], 1)               # follow-up vencido
    cands.itens[0].proxima_etapa_em = AGORA + timedelta(days=2)
    contas = Contas(itens={"gupy": ContaPlataforma(plataforma="gupy", status="desatualizado")})
    r = relatorio_semanal(base, cands, agora=AGORA, lembretes=lembretes, contas=contas, fila=["x"], limiar=80)
    assert (r.semana.total.candidaturas, r.geral.total.candidaturas) == (3, 4)
    assert any("Melhor variante de CV: cv-backend-pt — 100%" in f for f in r.funcionou)
    assert r.lacunas[0][:2] == ("Docker", 3)
    texto = "\n".join(r.acoes)
    for esperado in ("agente funil preparar", "g2 (Vaga g2)", "Docker", "gupy", "fila de aprovações"):
        assert esperado in texto
    assert "x1" not in texto                                       # vaga de golpe nunca é sugerida
    md = relatorio_markdown(r)
    for secao in ("## A semana em números", "## O que funcionou", "## Competências mais pedidas que faltam no perfil",
                  "## Próximas ações sugeridas", "### Por variante de CV"):
        assert secao in md


def test_relatorio_sem_dados_nao_inventa_conclusao():
    r = relatorio_semanal(BaseVagas(), Candidaturas(), agora=AGORA)
    assert "Ainda não há dados para comparar" in r.funcionou[0]
    assert r.acoes == ["Nada pendente: siga com a rodada diária e o resumo das 8h."]


def test_agendamento_semanal():
    assert validar_dia_hora("domingo 20:00") == ("SUN", "20:00")
    assert validar_dia_hora("Segunda-feira 7:30") == ("MON", "07:30")
    with pytest.raises(ValueError):
        validar_dia_hora("todo dia 20:00")
    inicio = proxima_vez("20:00", datetime(2026, 11, 18, 10, 0), "SUN")
    assert inicio == datetime(2026, 11, 22, 20, 0)
    xml = xml_tarefa(Path("C:/p/pythonw.exe"), '"C:/p/data/app/tarefa.pyw" relatorio semanal --notificar',
                     Path("C:/p"), inicio, "relatório", "SUN")
    assert "<Sunday />" in xml and "<WeeksInterval>1</WeeksInterval>" in xml and "relatorio semanal --notificar" in xml
    assert linha_cron_semanal(Path("/p"), "uv", "SUN", "20:00").startswith("0 20 * * 0 ")


# ---------------------------------------------------------------- RF-RL-03

def test_exportacao_csv_abre_no_excel(cenario, tmp_path):
    from agente_carreira.operacao.auditoria import listar_acoes, registrar_acao

    base, cands = cenario
    registrar_acao(plataforma="gupy", acao="enviar candidatura", alvo="Vaga g1", origem_aprovacao="kit",
                   aprovado_em=AGORA, depois="CV; mensagem")
    arquivos = exportar(tmp_path / "exp", base=base, candidaturas=cands, acoes=listar_acoes(), usos_ia=UsosIA())
    assert [a.name for a in arquivos] == ["vagas.csv", "candidaturas.csv", "funil-historico.csv", "log-acoes.csv", "uso-ia.csv"]
    bruto = (tmp_path / "exp" / "candidaturas.csv").read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf")                                 # BOM para o Excel
    with (tmp_path / "exp" / "candidaturas.csv").open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    assert len(linhas) == 5 and linhas[1]["motivo_saida"] == "inglês" and linhas[0]["retorno"] == "sim"
    with (tmp_path / "exp" / "log-acoes.csv").open(encoding="utf-8-sig", newline="") as f:
        [acao] = list(csv.DictReader(f, delimiter=";"))
    assert acao["depois"] == "CV; mensagem" and acao["acao"] == "enviar candidatura"   # ';' no texto fica entre aspas


# ---------------------------------------------------------------- CA-11 e CA-12

def test_ca12_todos_os_golpes_de_teste_sinalizados():
    c = _ca12()
    assert c.status == "ok" and f"{len(GOLPES_DE_TESTE)} de {len(GOLPES_DE_TESTE)}" in c.detalhe
    assert "controle" not in c.detalhe                                       # sem falso positivo nos controles


def test_ca11_envio_sem_confirmacao_falha_e_assistido_confirmado_passa():
    from agente_carreira.operacao.auditoria import registrar_acao

    assert _ca11(executar_navegador=False).status == "manual"
    registrar_acao(plataforma="gupy", acao="enviar candidatura", alvo="v", origem_aprovacao="kit", modo="assistido",
                   aprovado_em=AGORA)
    assert _ca11(executar_navegador=False).status == "ok"
    registrar_acao(plataforma="gupy", acao="enviar candidatura", alvo="v2", origem_aprovacao="?")
    assert _ca11(executar_navegador=False).status == "falhou"


def test_ca11_no_navegador_nao_envia():
    pytest.importorskip("playwright.sync_api")
    [ca11, _] = verificar_fase2()
    if ca11.status == "pendente":
        pytest.skip(ca11.detalhe)
    assert ca11.status == "manual" and "nenhum envio" in ca11.detalhe


def test_lacuna_que_o_perfil_ja_tem_sai_da_lista(cenario):
    from agente_carreira.models import Contato, PerfilMestre

    base, _ = cenario
    perfil = PerfilMestre(contato=Contato(nome="Ana", email="ana@example.com"), competencias_tecnicas=["docker"])
    contagem, _ = competencias_que_faltam(base.itens, perfil=perfil)
    assert "Docker" not in dict(contagem) and contagem[0][0] in {"Azure", "Kubernetes", "Power BI"}
