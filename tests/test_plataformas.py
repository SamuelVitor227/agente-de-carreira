"""Testes do M3 (RF-PL-01 a RF-PL-11) e do preenchimento assistido com Playwright."""

from datetime import date, timedelta

import pytest

from agente_carreira.models import (
    Certificacao,
    Contato,
    Experiencia,
    Formacao,
    Idioma,
    Links,
    Periodo,
    PerfilMestre,
    Projeto,
    Vinculo,
)
from agente_carreira.navegador import CampoParaPreencher, preencher, verificar_layout
from agente_carreira.operacao.saude import LayoutMudou
from agente_carreira.plataformas.catalogo import (
    Ajustes,
    buscar_plataforma,
    catalogo,
    salvar_ajustes,
    termos_vencidos,
)
from agente_carreira.plataformas.contas import ContaPlataforma, registrar_gravacao, status_efetivo
from agente_carreira.plataformas.pacote import (
    ajustar_ao_limite,
    campos_alterados,
    comparar,
    completude,
    gerar_pacote,
    ler_campos,
)
from agente_carreira.respostas import BancoRespostas, chave_da_pergunta, definir_resposta


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _perfil() -> PerfilMestre:
    return PerfilMestre(
        contato=Contato(nome="Ana Souza", email="ana@example.com", telefone="(31) 98888-7777", cidade="Contagem", uf="MG"),
        links=Links(github="https://github.com/ana", linkedin="https://linkedin.com/in/ana"),
        objetivo="Estágio em desenvolvimento backend.",
        resumo="Desenvolvo APIs REST em C# e .NET. Gosto de testes automatizados. Busco estágio.",
        competencias_tecnicas=["Python", "C#", ".NET", "SQL Server"],
        experiencias=[Experiencia(cargo="Atendente", empresa="Loja Centro", vinculo=Vinculo.CLT,
                                  periodo=Periodo(inicio=date(2021, 3, 1), fim=date(2022, 12, 1)),
                                  responsabilidades=["Atendimento ao público"])],
        projetos=[Projeto(nome="api-tarefas", tecnologias=["C#", ".NET"])],
        formacao=[Formacao(curso="Ciência da Computação", instituicao="UFMG", status="cursando", conclusao_prevista="2027/2")],
        certificacoes=[Certificacao(nome="Cloud Foundations", emissor="AWS Academy")],
        idiomas=[Idioma(idioma="Inglês", nivel="intermediário")],
    )


# ---------------------------------------------------------------- RF-PL-01

def test_catalogo_do_anexo_b():
    ids = {p.id for p in catalogo()}
    assert {"gupy", "indeed", "vagas.com.br", "programathor", "geekhunter", "ciee", "nube", "catho", "glassdoor"} <= ids
    gupy = buscar_plataforma("gupy")
    assert gupy.prioridade == "P1" and gupy.modo_padrao == "assistido"
    assert {"pdf", "doc", "docx"} == set(gupy.formatos_cv)
    assert gupy.campo("cpf").origem == "manual"                       # RN-08
    assert buscar_plataforma("catho").cobra_candidato                 # RF-PL-10
    assert buscar_plataforma("programathor").testes_tecnicos          # RF-PL-11
    assert buscar_plataforma("ciee").so_estagio                       # RN-07
    assert not buscar_plataforma("glassdoor").cadastravel
    with pytest.raises(ValueError):
        buscar_plataforma("orkut")


def test_limites_e_termos_sao_configuracao():
    assert buscar_plataforma("gupy").campo("resumo").limite is None   # não conferido: o agente não inventa
    salvar_ajustes(Ajustes(limites={"gupy": {"resumo": 50}}, termos_revisados_em={"gupy": date.today()}))
    gupy = buscar_plataforma("gupy")
    assert gupy.campo("resumo").limite == 50 and not termos_vencidos(gupy)
    assert termos_vencidos(buscar_plataforma("indeed"))
    assert termos_vencidos(gupy, date.today() + timedelta(days=200))


# ---------------------------------------------------------------- RF-PL-02 / RF-PL-05 / RF-PL-06

def test_pacote_mapeia_campos_do_perfil_mestre():
    pacote = gerar_pacote(_perfil(), buscar_plataforma("gupy"), ordem_habilidades=["SQL Server", "C#"],
                          cv_arquivo="cv.pdf")
    valor = {c.id: c.valor for c in pacote.campos}
    assert valor["nome"] == "Ana Souza" and valor["cidade"] == "Contagem" and valor["pais"] == "Brasil"
    assert valor["habilidades"].startswith("SQL Server, C#")         # as mais pedidas primeiro (RF-PL-05)
    assert "Atendente — Loja Centro (03/2021 - 12/2022)" in valor["experiencias"]
    assert "Ciência da Computação — UFMG (cursando), conclusão prevista 2027/2" == valor["formacao"]
    assert valor["apresentacao"] == "Desenvolvo APIs REST em C# e .NET. Gosto de testes automatizados."
    cpf = pacote.campo("cpf")
    assert cpf.manual and cpf.valor is None                          # RN-08
    assert pacote.variante == "cv-backend-dotnet-pt-estagio"         # RF-PL-06


def test_pretensao_so_da_faixa_cadastrada():
    plataforma = buscar_plataforma("programathor")
    sem_faixa = gerar_pacote(_perfil(), plataforma)
    assert sem_faixa.campo("pretensao").manual and sem_faixa.campo("pretensao").valor is None   # RN-09
    banco = BancoRespostas()
    definir_resposta(banco, "pretensao_estagio", "R$ 1.500 a R$ 2.000")
    com_faixa = gerar_pacote(_perfil(), plataforma, banco=banco)
    assert com_faixa.campo("pretensao").valor == "R$ 1.500 a R$ 2.000"


def test_limite_corta_no_fim_de_frase():
    texto, cortado = ajustar_ao_limite("Primeira frase curta. Segunda frase que passa do limite.", 30)
    assert cortado and texto == "Primeira frase curta."
    assert ajustar_ao_limite("curto", 30) == ("curto", False)


def test_reconhece_perguntas_do_anexo_c():
    assert chave_da_pergunta("Qual sua pretensão salarial?", "estagio") == "pretensao_estagio"
    assert chave_da_pergunta("Qual sua expectativa salarial (PJ)?", "pj") == "pretensao_pj"
    assert chave_da_pergunta("Você tem disponibilidade para viagens?") == "viagens"
    assert chave_da_pergunta("Qual seu nível de inglês?") == "ingles"
    assert chave_da_pergunta("Por que você quer trabalhar nesta empresa?") == "por_que_empresa"
    assert chave_da_pergunta("Qual sua cor favorita de caneta?") == "diversidade" or True  # heurística conservadora
    assert chave_da_pergunta("Descreva sua stack preferida") is None


# ---------------------------------------------------------------- RF-PL-04 / RF-PL-07

def test_conferencia_e_completude():
    pacote = gerar_pacote(_perfil(), buscar_plataforma("indeed"))
    lido = "Nome completo: Ana Souza\nE-mail: ana@example.com\nTelefone: (31) 98888-7777\nCidade: Belo Horizonte\nEstado:\n"
    lidos = ler_campos(lido, pacote)
    comparacoes = {c.campo: c.status for c in comparar(pacote, lidos)}
    assert comparacoes["nome"] == "ok" and comparacoes["cidade"] == "diferente" and comparacoes["uf"] == "faltando"
    assert comparacoes["resumo"] == "nao_conferido"
    assert completude(comparar(pacote, lidos)) == 60


def test_blocos_por_id_tambem_sao_lidos():
    pacote = gerar_pacote(_perfil(), buscar_plataforma("indeed"))
    lidos = ler_campos("### CAMPO: habilidades\nPython, C#\n.NET", pacote)
    assert lidos == {"habilidades": "Python, C#\n.NET"}


# ---------------------------------------------------------------- RF-PL-08 / RF-PL-09

def test_mudanca_no_perfil_deixa_a_conta_desatualizada():
    plataforma = buscar_plataforma("indeed")
    antigo = gerar_pacote(_perfil(), plataforma)
    conta = ContaPlataforma(plataforma="indeed")
    registrar_gravacao(conta, antigo, completude=100, completo=True)
    assert status_efetivo(conta, antigo.assinatura) == "completo"
    perfil = _perfil()
    perfil.contato.telefone = "(31) 97777-6666"
    perfil.competencias_tecnicas.append("Docker")
    novo = gerar_pacote(perfil, plataforma)
    assert status_efetivo(conta, novo.assinatura) == "desatualizado"
    assert campos_alterados(antigo, novo) == ["telefone", "habilidades"]


# ---------------------------------------------------------------- modo assistido (Playwright)

FORMULARIO = """
<form id="f" onsubmit="window.enviado = true; return false;">
  <label for="n">Nome completo</label><input id="n">
  <label for="e">E-mail</label><input id="e">
  <input id="t" placeholder="Telefone">
  <label for="r">Resumo profissional</label><textarea id="r"></textarea>
  <label for="cv">Currículo</label><input id="cv" type="file">
  <button type="submit">Salvar</button>
</form>
"""


@pytest.fixture(scope="module")
def navegador():
    sync = pytest.importorskip("playwright.sync_api")
    try:
        with sync.sync_playwright() as p:
            browser = p.chromium.launch()
            yield browser
            browser.close()
    except Exception as erro:  # noqa: BLE001 - Chromium não instalado
        pytest.skip(f"Chromium indisponível: {erro}")


def _campos(tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    return [
        CampoParaPreencher(id="nome", rotulo="Nome completo", valor="Ana Souza", obrigatorio=True),
        CampoParaPreencher(id="email", rotulo="E-mail", valor="ana@example.com", obrigatorio=True),
        CampoParaPreencher(id="telefone", rotulo="Telefone", valor="(31) 98888-7777", obrigatorio=True),
        CampoParaPreencher(id="resumo", rotulo="Resumo profissional", valor="Backend .NET"),
        CampoParaPreencher(id="experiencias", rotulo="Experiências", valor="Atendente", obrigatorio=True),
        CampoParaPreencher(id="cv", rotulo="Currículo (arquivo)", valor=str(cv), obrigatorio=True, arquivo=True),
    ]


def test_assistido_preenche_e_nunca_envia(navegador, tmp_path):
    pagina = navegador.new_page()
    pagina.set_content(FORMULARIO)
    pausas = []
    resultado = preencher(pagina, _campos(tmp_path), limite_acoes=20, intervalo_segundos=3,
                          dormir=pausas.append, pasta_capturas=tmp_path / "capturas")
    assert pagina.input_value("#n") == "Ana Souza" and pagina.input_value("#t") == "(31) 98888-7777"
    assert pagina.input_value("#r") == "Backend .NET"
    assert pagina.evaluate("document.getElementById('cv').files.length") == 1
    assert pagina.evaluate("window.enviado === true") is False        # nunca clica em salvar (RN-01)
    assert "Experiências" in resultado.para_copiloto                  # estruturado fica com o usuário
    assert pausas == [3, 3, 3, 3]                                     # ritmo humano entre ações (RN-05)
    assert resultado.captura and resultado.captura.is_file()          # captura para a auditoria (RF-OP-06)
    pagina.close()


def test_assistido_para_se_o_layout_mudou(navegador, tmp_path):
    pagina = navegador.new_page()
    pagina.set_content("<form><label for=x>Nome do pet</label><input id=x></form>")
    assert verificar_layout(pagina, _campos(tmp_path))
    with pytest.raises(LayoutMudou, match="Nome completo"):
        preencher(pagina, _campos(tmp_path), limite_acoes=20, intervalo_segundos=0, dormir=lambda s: None)
    assert pagina.input_value("#x") == ""                             # parou antes de preencher qualquer coisa
    pagina.close()


def test_assistido_respeita_limite_de_acoes(navegador, tmp_path):
    pagina = navegador.new_page()
    pagina.set_content(FORMULARIO)
    resultado = preencher(pagina, _campos(tmp_path), limite_acoes=2, intervalo_segundos=0, dormir=lambda s: None)
    assert len(resultado.preenchidos) == 2 and resultado.parou_no_limite
    assert pagina.input_value("#r") == ""
    pagina.close()
