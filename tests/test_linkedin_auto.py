"""Navegador automático no LinkedIn (RN-04 por opção), e-mail sem terminal e 'candidatar às melhores'."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agente_carreira.app import estado
from agente_carreira.candidaturas import Candidatura, Candidaturas, Etapa
from agente_carreira.cli import app as cli_app
from agente_carreira.configuracao import Configuracao, LinkedInAutomatico, carregar_configuracao, definir
from agente_carreira.linkedin import automatico as auto
from agente_carreira.models import Contato, PerfilMestre
from agente_carreira.operacao import credenciais
from agente_carreira.operacao.saude import LayoutMudou, RegistroSaude
from agente_carreira.radar.agenda import tarefa_agendada
from agente_carreira.radar.modelos import Aderencia, BaseVagas, BuscaSalva, ConfigVagas, VagaBruta, VagaEncontrada
from agente_carreira.respostas import BancoRespostas

RAPIDO = LinkedInAutomatico(intervalo_min_s=0, intervalo_max_s=0)


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _sem_pausa(_segundos):
    return None


# ---------------------------------------------------------------- configuração e CLI

def test_desligado_por_padrao_e_ligar_exige_aceitar_o_risco():
    assert Configuracao().linkedin_automatico.ativo is False
    with pytest.raises(ValueError, match="aceito-o-risco"):
        definir(Configuracao(), "linkedin_automatico.ativo", "true")
    runner = CliRunner()
    assert runner.invoke(cli_app, ["li", "automatico", "ligar"]).exit_code == 1
    assert carregar_configuracao().linkedin_automatico.ativo is False
    assert runner.invoke(cli_app, ["li", "automatico", "ligar", "--aceito-o-risco"]).exit_code == 0
    cfg = carregar_configuracao().linkedin_automatico
    assert cfg.ativo and cfg.aceito_risco_em is not None
    assert runner.invoke(cli_app, ["li", "automatico", "desligar"]).exit_code == 0
    assert carregar_configuracao().linkedin_automatico.ativo is False


def test_intervalo_maximo_nao_pode_ser_menor_que_o_minimo():
    with pytest.raises(ValueError):
        LinkedInAutomatico(intervalo_min_s=10, intervalo_max_s=2)


# ---------------------------------------------------------------- busca

def test_url_de_busca_com_filtros():
    url = auto.url_busca("desenvolvedor .net", "Belo Horizonte, Minas Gerais, Brasil", ["estagio", "junior"],
                         ["estagio", "clt"], ultimas_horas=24)
    assert url.startswith(auto.URL_BUSCA) and "keywords=desenvolvedor+.net" in url
    assert "f_TPR=r86400" in url and "f_E=1%2C2" in url and "f_JT=F%2CI" in url and "sortBy=DD" in url
    assert "f_WT=2" in auto.url_busca("x", "Brasil", [], [], remoto=True)


def test_consultas_tem_pesquisa_geral_e_revezam_as_areas_por_dia():
    from agente_carreira.radar.modelos import PESQUISAS_GERAIS_LINKEDIN

    config = ConfigVagas(buscas=[
        BuscaSalva(nome="backend-dotnet", cargos=["dev .net", "dev c#", "backend"], niveis=["estagio"], contratos=["clt"]),
        BuscaSalva(nome="dados", cargos=["analista de dados"], niveis=["junior"], contratos=["clt"], remoto_brasil=False),
    ])
    cfg = LinkedInAutomatico(consultas_por_rodada=3)
    dia = date(2026, 11, 18)
    lista = auto.consultas(config, cfg, hoje=dia)
    assert lista[0][0] == "geral" and len(lista) == 3
    termo = PESQUISAS_GERAIS_LINKEDIN[dia.toordinal() % len(PESQUISAS_GERAIS_LINKEDIN)]
    assert "keywords=" + termo.replace(" ", "+").replace("é", "%C3%A9").replace("ú", "%C3%BA") in lista[0][1]
    assert "f_E=1%2C2" in lista[0][1]                                            # níveis de todas as buscas
    amanha = auto.consultas(config, cfg, hoje=date(2026, 11, 19))
    assert lista[1][0] != amanha[1][0]                                           # cada dia começa por outra área
    assert all("linkedin.com/jobs/search" in url for _, url in lista)


def test_termos_gerais_de_ti_valem_para_todas_as_buscas():
    from agente_carreira.radar.texto import casa_cargo

    busca = BuscaSalva(nome="mobile", cargos=["desenvolvedor mobile"])
    for titulo in ("Estagiário de TI", "Tecnologia da Informação", "Trainee de Tecnologia", "Analista de TI Júnior",
                   "Programador Jr", "IT Intern", "Estágio em Desenvolvimento"):
        assert casa_cargo(titulo, busca.cargos_efetivos()), titulo
    for titulo in ("Auxiliar Administrativo", "Vendedor Externo", "Analista Financeiro Júnior"):
        assert not casa_cargo(titulo, busca.cargos_efetivos()), titulo
    assert not casa_cargo("Tecnologia da Informação", BuscaSalva(nome="x", cargos=["mobile"], termos_gerais=False).cargos_efetivos())


def test_cartoes_viram_vagas_sem_ruido():
    vagas = auto.cartoes_para_vagas([
        {"id": "4012345678", "titulo": "Desenvolvedor .NET Júnior with verification",
         "linhas": ["Desenvolvedor .NET Júnior", "Desenvolvedor .NET Júnior with verification", "Omega Tecnologia",
                    "Belo Horizonte, MG (Híbrido)", "Candidatura simplificada", "há 2 horas", "25 candidatos"]},
        {"id": "4012345679", "titulo": "", "linhas": ["Estágio em Dados", "Promovida", "Beta", "Contagem, MG"]},
    ])
    assert [(v.titulo, v.empresa, v.local) for v in vagas] == [
        ("Desenvolvedor .NET Júnior", "Omega Tecnologia", "Belo Horizonte, MG (Híbrido)"),
        ("Estágio em Dados", "Beta", "Contagem, MG")]
    assert vagas[0].link == "https://www.linkedin.com/jobs/view/4012345678" and vagas[0].fonte_origem == auto.ORIGEM


def test_respostas_viram_opcoes_e_numeros():
    assert auto.escolher_opcao("Sim — projetos: api", ["Sim", "Não"]) == "Sim"
    assert auto.escolher_opcao("Não", ["Yes", "No"]) == "No"
    assert auto.escolher_opcao("intermediário", ["Básico", "Intermediário", "Avançado"]) == "Intermediário"
    assert auto.escolher_opcao("talvez", ["Sim", "Não"]) is None
    assert auto._so_numero("R$ 1.800") == "1800" and auto._so_numero("2,5 anos") == "2.5" and auto._so_numero("Sim") is None


def test_responder_com_perfil_usa_contato_e_banco_e_nao_inventa():
    perfil = PerfilMestre(contato=Contato(nome="Ana Souza", email="ana@example.com", telefone="(31) 99999-0000",
                                          cidade="Contagem", uf="MG"), competencias_tecnicas=["C#"])
    banco = BancoRespostas()
    from agente_carreira.respostas import definir_resposta
    definir_resposta(banco, "pretensao_estagio", "1800")
    responder = auto.responder_com_perfil(perfil, banco, "estagio")
    assert responder("Número de celular") == "(31) 99999-0000"
    assert responder("Endereço de e-mail") == "ana@example.com"
    assert responder("Cidade") == "Contagem, MG"
    assert responder("Qual sua pretensão salarial?") == "1800"
    assert responder("Você possui experiência com C#?").startswith("Sim")
    assert responder("Quando você pode começar?") is None                   # RN-09: fica para você


def test_pagina_de_login_para_e_avisa():
    class Pagina:
        url = "https://www.linkedin.com/checkpoint/challenge/123"
    with pytest.raises(auto.LoginNecessario):
        auto.checar_pagina(Pagina())


# ---------------------------------------------------------------- navegador (páginas locais)

BUSCA_HTML = """<html><body><ul>
<li><a href="/jobs/view/4012345678/?trk=x">Desenvolvedor .NET Júnior<br>Desenvolvedor .NET Júnior with verification</a>
  <div>Omega Tecnologia</div><div>Belo Horizonte, MG (Híbrido)</div><div>Candidatura simplificada</div></li>
<li><a href="/jobs/view/4012345679/">Estágio em Dados</a><div>Beta</div><div>Contagem, MG</div><div>Promovida</div></li>
</ul></body></html>"""

DETALHE_HTML = """<html><head><script type="application/ld+json">{json}</script></head>
<body><div id="job-details">texto da página</div></body></html>"""

CANDIDATURA_HTML = """<html><body>
<h1>Desenvolvedor .NET</h1>
<button id="abrir" onclick="render()">Candidatura simplificada</button>
<div id="modal"></div>
<script>
window.enviado = false;
const etapas = [
  `<div role="dialog"><label for="tel">Celular</label><input id="tel" required>
     <button onclick="prox()">Avançar</button></div>`,
  `<div role="dialog"><fieldset><legend>Você possui experiência com C#? *</legend>
     <input type="radio" id="s" name="r" required><label for="s">Sim</label>
     <input type="radio" id="n" name="r"><label for="n">Não</label></fieldset>
     <label for="cv">Currículo</label><input type="file" id="cv">
     <button onclick="prox()">Revisar</button></div>`,
  `<div role="dialog"><p>Revise sua candidatura</p>
     <button onclick="window.enviado = true">Enviar candidatura</button></div>`];
let i = 0;
function render() { document.getElementById('modal').innerHTML = etapas[i]; }
function prox() { i++; render(); }
</script></body></html>"""


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


def _arquivo(tmp_path, nome, html) -> str:
    caminho = tmp_path / nome
    caminho.write_text(html, encoding="utf-8")
    return caminho.as_uri()


def test_le_cartoes_da_pagina_de_busca(navegador, tmp_path):
    pagina = navegador.new_page()
    vagas = auto.ler_resultados(pagina, _arquivo(tmp_path, "busca.html", BUSCA_HTML), RAPIDO, _sem_pausa)
    pagina.close()
    assert [(v.titulo, v.empresa) for v in vagas] == [("Desenvolvedor .NET Júnior", "Omega Tecnologia"),
                                                      ("Estágio em Dados", "Beta")]


def test_detalhe_pelo_json_ld(navegador, tmp_path):
    posting = {"@type": "JobPosting", "title": "Desenvolvedor .NET Júnior", "employmentType": "FULL_TIME",
               "description": "<p>Requisitos: C# e SQL Server</p>",
               "hiringOrganization": {"name": "Omega Tecnologia"}}
    url = _arquivo(tmp_path, "vaga.html", DETALHE_HTML.replace("{json}", json.dumps(posting)))
    pagina = navegador.new_page()
    vaga = auto.ler_detalhe(pagina, VagaBruta(titulo="Dev", link=url, fonte_tipo="pagina", fonte_origem=auto.ORIGEM),
                            RAPIDO, _sem_pausa)
    pagina.close()
    assert "C# e SQL Server" in vaga.descricao and vaga.contrato == "clt" and vaga.empresa == "Omega Tecnologia"


def test_candidatura_simplificada_avanca_e_para_antes_de_enviar(navegador, tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    respostas = {"Celular": "(31) 99999-0000", "Você possui experiência com C#?": "Sim — projetos: api"}
    pagina = navegador.new_page()
    resultado = auto.candidatura_simplificada(pagina, _arquivo(tmp_path, "aplicar.html", CANDIDATURA_HTML),
                                              respostas.get, cv, RAPIDO, dormir=_sem_pausa,
                                              pasta_capturas=tmp_path / "capturas")
    assert resultado.parou == "revisao" and resultado.etapas == 3
    assert {"Celular", "Você possui experiência com C#?", "currículo (arquivo)"} <= set(resultado.preenchidos)
    assert pagina.evaluate("window.enviado") is False                    # nunca clica em enviar (RN-01, CA-11)
    assert resultado.captura and resultado.captura.is_file()
    pagina.close()


def test_pergunta_sem_resposta_para_e_deixa_com_voce(navegador, tmp_path):
    pagina = navegador.new_page()
    resultado = auto.candidatura_simplificada(pagina, _arquivo(tmp_path, "aplicar.html", CANDIDATURA_HTML),
                                              {"Celular": "31999990000"}.get, None, RAPIDO, dormir=_sem_pausa)
    assert resultado.parou == "pergunta_sem_resposta"
    assert resultado.sem_resposta == ["Você possui experiência com C#?"]
    assert pagina.evaluate("window.enviado") is False
    pagina.close()


def test_vaga_sem_candidatura_simplificada(navegador, tmp_path):
    pagina = navegador.new_page()
    resultado = auto.candidatura_simplificada(pagina, _arquivo(tmp_path, "externa.html", "<h1>Vaga</h1>"),
                                              lambda _r: None, None, RAPIDO, dormir=_sem_pausa)
    pagina.close()
    assert resultado.parou == "sem_candidatura_simplificada"


# ---------------------------------------------------------------- rodada

class _SessaoFalsa:
    pagina = object()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_coletor_da_rodada_trata_login_e_layout(monkeypatch):
    config = ConfigVagas(buscas=[BuscaSalva(nome="backend-dotnet", cargos=["dev .net"])])
    saude = RegistroSaude()
    vaga = VagaBruta(titulo="Dev", link="https://www.linkedin.com/jobs/view/1", fonte_tipo="pagina", fonte_origem=auto.ORIGEM)

    monkeypatch.setattr(auto, "buscar_vagas", lambda *a, **k: auto.ResultadoBusca(vagas=[vaga]))
    coletar = auto.coletor_da_rodada(config, RAPIDO, saude, abrir_sessao=_SessaoFalsa, dormir=_sem_pausa)
    assert coletar(BaseVagas()) == ([vaga], [], [])

    def pede_login(*a, **k):
        raise auto.LoginNecessario("faça login")
    monkeypatch.setattr(auto, "buscar_vagas", pede_login)
    brutas, avisos, falhas = coletar(BaseVagas())
    assert brutas == [] and "faça login" in avisos[0] and falhas                # vira aviso/notificação

    def layout(*a, **k):
        raise LayoutMudou("layout novo")
    monkeypatch.setattr(auto, "buscar_vagas", layout)
    coletar(BaseVagas())
    assert not saude.pode_usar(auto.ADAPTADOR)                                  # para e avisa (RF-OP-07)
    assert "parado" in coletar(BaseVagas())[1][0]


def test_rodada_inclui_vagas_do_coletor_extra():
    from agente_carreira.radar.rodada import executar_rodada

    perfil = PerfilMestre(contato=Contato(nome="Ana", email="ana@example.com", cidade="Belo Horizonte", uf="MG"),
                          competencias_tecnicas=["C#", ".NET"])
    config = ConfigVagas(buscas=[BuscaSalva(nome="backend-dotnet", cargos=["desenvolvedor .net"], niveis=["junior"],
                                            contratos=["clt"])])
    extra = VagaBruta(titulo="Desenvolvedor .NET Júnior", empresa="Omega", local="Belo Horizonte, MG",
                      descricao="Requisitos: C# e .NET. CLT.", link="https://www.linkedin.com/jobs/view/4012345678",
                      fonte_tipo="pagina", fonte_origem=auto.ORIGEM)
    base = BaseVagas()
    executar_rodada(perfil, config, base, date.today(), pasta_emails=None, imap=None, usar_paginas=False,
                    enriquecer_links=False, motor_justificativa="local",
                    coletores_extras=[lambda b: ([extra], ["aviso do LinkedIn"], [])])
    [vaga] = base.itens
    assert vaga.fontes[0].origem == auto.ORIGEM and vaga.titulo == "Desenvolvedor .NET Júnior"


# ---------------------------------------------------------------- e-mail sem terminal

def test_variaveis_do_email_e_avisos():
    valores = credenciais.variaveis(credenciais.ConfigEmail("gmail", "ana@gmail.com", "abcd efgh ijkl mnop"))
    assert valores["AGENTE_IMAP_HOST"] == "imap.gmail.com" and valores["AGENTE_IMAP_SENHA"] == "abcdefghijklmnop"
    assert valores["AGENTE_SMTP_HOST"] == "smtp.gmail.com" and valores["AGENTE_IMAP_PASTA"] == "INBOX"
    sem_avisos = credenciais.variaveis(credenciais.ConfigEmail("outlook", "a@hotmail.com", "x", avisos=False))
    assert "AGENTE_SMTP_HOST" not in sem_avisos and sem_avisos["AGENTE_IMAP_HOST"] == "outlook.office365.com"
    with pytest.raises(ValueError):
        credenciais.variaveis(credenciais.ConfigEmail("gmail", "sem-arroba", "x"))


def test_gravar_variaveis_usa_setx_e_atualiza_o_processo(monkeypatch):
    import os
    chamadas = []

    class Ok:
        returncode, stdout, stderr = 0, "SUCCESS", ""
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.delenv("AGENTE_TESTE_X", raising=False)
    credenciais.gravar_variaveis_do_usuario({"AGENTE_TESTE_X": "1"}, executar=lambda cmd, **k: chamadas.append(cmd) or Ok())
    assert chamadas == [["setx", "AGENTE_TESTE_X", "1"]] and os.environ["AGENTE_TESTE_X"] == "1"
    monkeypatch.delenv("AGENTE_TESTE_X")


def test_testar_imap_so_le():
    class Imap:
        def __init__(self, host):
            self.host, self.readonly = host, None

        def login(self, u, s):
            pass

        def select(self, pasta, readonly=False):
            self.readonly = readonly
            return "OK", [b"3"]

        def search(self, *a):
            return "OK", [b"1 2 3"]

        def logout(self):
            pass
    criadas = []
    assert credenciais.testar_imap("h", "u", "s", "INBOX", imap_factory=lambda h: criadas.append(Imap(h)) or criadas[-1]) == 3
    assert criadas[0].readonly is True                                          # RNF-03


def test_tarefa_agendada_consulta_o_agendador(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")

    class R:
        def __init__(self, codigo):
            self.returncode = codigo
    assert tarefa_agendada(executar=lambda *a, **k: R(0)) is True
    assert tarefa_agendada(executar=lambda *a, **k: R(1)) is False


# ---------------------------------------------------------------- candidatar às melhores

def test_melhores_respeitam_nota_golpe_aplicadas_e_limite_do_dia():
    from agente_carreira.radar.modelos import Sinal

    base = BaseVagas(itens=[
        VagaEncontrada(id=f"v{n}", titulo=f"Vaga {n}", status="no_resumo", aderencia=Aderencia(nota=n))
        for n in (95, 90, 85, 80, 75, 72, 50)
    ] + [VagaEncontrada(id="g", titulo="Golpe", status="no_resumo", aderencia=Aderencia(nota=99),
                        sinais=[Sinal(tipo="golpe:pix", mensagem="pix")])])
    feita = Candidatura(vaga_id="v95", vaga_titulo="Vaga 95", foco="x", variante="cv")
    feita.mudar_status(Etapa.APLICADA)
    candidaturas = Candidaturas(itens=[feita])
    assert estado.vagas_restantes_hoje(candidaturas, 10) == 9
    escolhidas = estado.melhores_para_candidatar(base, candidaturas, 70, estado.vagas_restantes_hoje(candidaturas, 10))
    assert [l.id for l in escolhidas] == ["v90", "v85", "v80", "v75", "v72"]     # lote de no máximo 5
    assert [l.id for l in estado.melhores_para_candidatar(base, candidaturas, 70, 2)] == ["v90", "v85"]
    assert estado.melhores_para_candidatar(base, candidaturas, 70, 0) == []


# ---------------------------------------------------------------- um uso por vez e erros curtos

def test_trava_impede_dois_usos_do_navegador(tmp_path):
    from agente_carreira.navegador import NavegadorOcupado, _Trava

    primeira, segunda = _Trava(tmp_path / "navegador.trava"), _Trava(tmp_path / "navegador.trava")
    primeira.adquirir()
    with pytest.raises(NavegadorOcupado, match="já está aberto"):
        segunda.adquirir()
    primeira.soltar()
    segunda.adquirir()                                                          # liberada, a próxima consegue
    segunda.soltar()


def test_navegador_ocupado_na_rodada_vira_aviso_sem_falha(monkeypatch):
    from agente_carreira.navegador import NavegadorOcupado

    class Ocupado:
        def __enter__(self):
            raise NavegadorOcupado()

        def __exit__(self, *exc):
            return False
    saude = RegistroSaude()
    brutas, avisos, falhas = auto.coletor_da_rodada(ConfigVagas(buscas=[BuscaSalva(nome="x", cargos=["dev"])]), RAPIDO,
                                                    saude, abrir_sessao=Ocupado)(BaseVagas())
    assert brutas == [] and falhas == [] and "não pesquisado" in avisos[0]
    assert saude.obter(auto.ADAPTADOR).falhas_seguidas == 0 and saude.pode_usar(auto.ADAPTADOR)


def test_erro_curto_corta_o_log_do_chromium():
    from agente_carreira.navegador import erro_curto

    erro = RuntimeError("BrowserType.launch_persistent_context: Target closed\nBrowser logs:\n--disable-x\n" + "y" * 900)
    assert erro_curto(erro) == "BrowserType.launch_persistent_context: Target closed"


def test_login_detectado_em_qualquer_aba():
    class Aba:
        def __init__(self, url):
            self.url = url

        def is_closed(self):
            return False

    class Contexto:
        pages = [Aba("https://www.linkedin.com/login"), Aba("https://www.linkedin.com/feed/")]

    class Pagina:
        context = Contexto()

        def goto(self, *a, **k):
            pass
    assert auto.esperar_login(Pagina(), minutos=1, dormir=_sem_pausa) is True
    Contexto.pages = [Aba("https://www.linkedin.com/checkpoint/challenge")]
    assert auto.esperar_login(Pagina(), minutos=1, dormir=_sem_pausa) is False


# ---------------------------------------------------------------- Gupy: preenchimento automático das informações básicas

FORM_GUPY = """<html><body><form onsubmit="window.enviado = true; return false;">
<label for="n">Nome</label><input id="n">
<label for="s">Sobrenome</label><input id="s">
<label for="e">E-mail</label><input id="e" value="meu@outro.com">
<label for="c">Celular</label><input id="c">
<label for="cpf">CPF</label><input id="cpf">
<label for="uf">Estado</label><select id="uf"><option>Selecione</option><option>Minas Gerais</option><option>São Paulo</option></select>
<label for="ci">Cidade</label><input id="ci">
<label for="pw">Senha</label><input id="pw" type="password">
<label for="li">LinkedIn</label><input id="li">
<button type="submit">Salvar</button></form></body></html>"""


def _perfil_basico():
    from agente_carreira.models import Links

    return PerfilMestre(contato=Contato(nome="Ana Maria Souza", email="ana@example.com", telefone="(31) 99999-0000",
                                        cidade="Contagem", uf="MG"),
                        links=Links(linkedin="https://www.linkedin.com/in/ana"))


def test_preenche_so_basico_vazio_sem_cpf_senha_nem_envio(navegador):
    from agente_carreira.preenchimento_auto import campos_basicos, preencher_vazios

    pagina = navegador.new_page()
    pagina.set_content(FORM_GUPY)
    ja = set()
    feitos = preencher_vazios(pagina, campos_basicos(_perfil_basico()), ja)
    valor = lambda i: pagina.locator(f"#{i}").input_value()
    assert (valor("n"), valor("s"), valor("c"), valor("ci")) == ("Ana", "Maria Souza", "(31) 99999-0000", "Contagem")
    assert valor("e") == "meu@outro.com"                                        # nunca sobrescreve
    assert valor("cpf") == "" and valor("pw") == ""                             # RN-08 e senha são seus
    assert pagina.locator("#uf").evaluate("e => e.options[e.selectedIndex].text") == "Minas Gerais"
    assert pagina.locator("#li").input_value() == "https://www.linkedin.com/in/ana"
    assert pagina.evaluate("window.enviado") is None                            # nunca clica em salvar
    pagina.locator("#c").fill("")                                               # você limpou: não preenche de novo
    assert preencher_vazios(pagina, campos_basicos(_perfil_basico()), ja) == []
    assert "Celular" in feitos
    pagina.close()


def test_nome_sozinho_recebe_nome_completo(navegador):
    from agente_carreira.preenchimento_auto import campos_basicos, preencher_vazios

    pagina = navegador.new_page()
    pagina.set_content('<label for="n">Nome</label><input id="n">')
    preencher_vazios(pagina, campos_basicos(_perfil_basico()), set())
    assert pagina.locator("#n").input_value() == "Ana Maria Souza"
    pagina.close()


def test_acompanha_so_os_dominios_da_plataforma(monkeypatch):
    from agente_carreira import preenchimento_auto as pa

    class Pagina:
        def __init__(self, url):
            self.url = url

        def is_closed(self):
            return False

    class Contexto:
        pages = [Pagina("https://portal.gupy.io/candidato"), Pagina("https://www.google.com/")]
    visitadas = []
    monkeypatch.setattr(pa, "preencher_vazios", lambda p, c, j: visitadas.append(p.url) or ["E-mail"])
    avisos = []
    total = pa.acompanhar(Contexto(), ["gupy.io"], [], ao_preencher=lambda u, r: avisos.append(u), dormir=_sem_pausa,
                          horas=0.001, intervalo_s=1)
    assert set(visitadas) == {"https://portal.gupy.io/candidato"} and total == len(visitadas) and avisos
