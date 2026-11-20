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


# ---------------------------------------------------------------- busca direta no portal da Gupy

def _link_gupy(job_id: int, empresa: str = "empresa") -> str:
    import base64

    codigo = base64.b64encode(json.dumps({"jobId": job_id, "source": "gupy_portal"}).encode()).decode()
    return f"https://{empresa}.gupy.io/job/{codigo}?jobBoardSource=gupy_portal"


def test_cartao_do_portal_vira_vaga_com_link_normal_da_gupy():
    from agente_carreira.radar import gupy_portal as gp

    assert gp.id_da_vaga(_link_gupy(12805520)) == "12805520"
    assert gp.id_da_vaga("https://x.gupy.io/jobs/987654") == "987654"
    vaga = gp.cartao_para_vaga({"href": _link_gupy(12805520, "vagasagis"), "linhas": [
        "Agis Distribuição", "Estágio - Infraestrutura TI", "Belo Horiz... - MG", "Híbrido", "Estágio",
        "Também p/ PcD", "Publicada em: 17/11/2026"]})
    assert vaga.link == "https://vagasagis.gupy.io/jobs/12805520" and vaga.fonte_origem == gp.ORIGEM
    assert (vaga.empresa, vaga.titulo, vaga.local) == ("Agis Distribuição", "Estágio - Infraestrutura TI", "Belo Horizonte - MG")
    assert (vaga.modelo, vaga.contrato, vaga.publicada_em) == ("hibrido", "estagio", date(2026, 11, 17))
    assert gp.cartao_para_vaga({"href": "https://site.com/job/x", "linhas": ["a", "b"]}) is None


def test_termos_da_gupy_revezam_e_respeitam_o_limite():
    from agente_carreira.radar.gupy_portal import termos_da_rodada

    buscas = [BuscaSalva(nome="a", cargos=["desenvolvedor .net"]), BuscaSalva(nome="b", cargos=["analista de dados"])]
    hoje = termos_da_rodada(buscas, ["estágio TI", "trainee tecnologia"], 3, date(2026, 11, 18))
    amanha = termos_da_rodada(buscas, ["estágio TI", "trainee tecnologia"], 3, date(2026, 11, 19))
    assert len(hoje) == 3 and hoje != amanha
    assert set(termos_da_rodada(buscas, ["estágio TI", "trainee tecnologia"], 10)) == {
        "estágio TI", "trainee tecnologia", "desenvolvedor .net", "analista de dados"}


def test_coletor_da_gupy_sem_conta_e_com_robots(monkeypatch):
    from agente_carreira.radar import gupy_portal as gp

    class Pagina:
        def evaluate(self, _js):
            return [{"href": _link_gupy(1234567), "linhas": ["Omega", "Estágio TI", "Contagem - MG", "Presencial"]}]

    class Navegador:
        def __enter__(self):
            return lambda url: Pagina()

        def __exit__(self, *exc):
            return False
    saude = RegistroSaude()
    coletar = gp.coletor_da_rodada(ConfigVagas(), ["estágio ti"], saude, abrir_navegador=Navegador,
                                   permite=lambda url: True, dormir=_sem_pausa)
    vagas, avisos, falhas = coletar(BaseVagas())
    assert [v.link for v in vagas] == ["https://empresa.gupy.io/jobs/1234567"] and falhas == []
    bloqueado = gp.coletor_da_rodada(ConfigVagas(), ["x"], saude, abrir_navegador=Navegador, permite=lambda url: False)
    assert "robots" in bloqueado(BaseVagas())[1][0]


# ---------------------------------------------------------------- e-mails que não são alertas, dicas do LinkedIn, paralelo

def _email(remetente, assunto, html):
    from email.message import EmailMessage

    m = EmailMessage()
    m["From"], m["Subject"] = remetente, assunto
    m.set_content(html, subtype="html")
    return m


def test_emails_comuns_nao_param_a_fonte_e_rastreamento_vira_aviso():
    from agente_carreira.radar.coleta import parece_alerta, so_links_de_rastreamento

    assert not parece_alerta(_email("alertas@indeed.com", "Atualizamos os nossos Termos de Serviço", "<p>oi</p>"))
    assert not parece_alerta(_email("no-reply@gupy.io", "samuel, vamos confirmar seu e-mail de cadastro?", "<p>x</p>"))
    assert parece_alerta(_email("x@vagas.com.br", "Nova vaga compatível", "<p>x</p>"))
    assert parece_alerta(_email("jobalerts-noreply@linkedin.com", "LUZA Group Engenheiro", "<p>x</p>"))
    rastreio = _email("x@vagas.com.br", "Nova vaga compatível",
                      '<a href="https://tracking.recomendacao.vagas.com.br/tracking/1/click/abc">Ver oportunidade</a>')
    assert so_links_de_rastreamento(rastreio)
    assert not so_links_de_rastreamento(_email("x@gupy.io", "Vagas", '<a href="https://omega.gupy.io/jobs/123">Dev</a>'))


def test_alerta_novo_do_linkedin_separa_empresa_e_local_e_ignora_dicas():
    from agente_carreira.radar.coleta import vagas_de_email

    html = ('<table><tr><td><a href="https://www.linkedin.com/comm/jobs/view/4489776621/?trk=x">Estagiário em TI</a></td></tr>'
            '<tr><td>Orguel · Belo Horizonte, MG (Híbrido)</td></tr><tr><td>47 ex-alunos da instituição de ensino</td></tr>'
            '<tr><td><a href="https://www.linkedin.com/comm/jobs/view/4489776622/">Estagiário(a) - Suporte Técnico em TI</a></td></tr>'
            '<tr><td>Tractebel · Belo Horizonte, MG (Presencial)</td></tr><tr><td>Recrutando agora</td></tr></table>')
    vagas = vagas_de_email(_email("jobalerts-noreply@linkedin.com", "Vagas para você", html))
    assert [(v.titulo, v.empresa, v.local) for v in vagas] == [
        ("Estagiário em TI", "Orguel", "Belo Horizonte, MG (Híbrido)"),
        ("Estagiário(a) - Suporte Técnico em TI", "Tractebel", "Belo Horizonte, MG (Presencial)")]


def test_trabalhadores_respeitam_o_limite_de_memoria():
    from agente_carreira.operacao.recursos import trabalhadores

    assert trabalhadores(20, total_mb=65_000) == 8            # teto por educação com os sites
    assert trabalhadores(20, total_mb=4_000) == 3             # 800 MB / 256 MB
    assert trabalhadores(20, total_mb=1_000) == 1


def test_descricoes_em_paralelo_por_site_e_robots_uma_vez_por_site():
    from agente_carreira.radar.modelos import VagaEncontrada
    from agente_carreira.radar.rodada import enriquecer

    pedidos = []
    html = '<script type="application/ld+json">{"@type":"JobPosting","title":"Dev","description":"<p>C# e SQL</p>"}</script>'

    def baixar(url):
        pedidos.append(url)
        return (200, "User-agent: *\nAllow: /") if url.endswith("robots.txt") else (200, html)
    vagas = [VagaEncontrada(titulo=f"Dev {i}", link=f"https://emp{i % 3}.gupy.io/jobs/{i}") for i in range(6)]
    lidas = enriquecer(vagas, ConfigVagas(), baixar, _sem_pausa, paralelo=4)
    assert lidas == 6 and all("C# e SQL" in v.descricao for v in vagas)
    assert sum(1 for u in pedidos if u.endswith("robots.txt")) == 3   # um por site


def test_anexa_curriculo_no_campo_de_arquivo_e_dominio_raiz(navegador, tmp_path):
    from agente_carreira.preenchimento_auto import campo_curriculo, dominio_raiz, preencher_vazios

    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    pagina = navegador.new_page()
    pagina.set_content('<input type="file" id="foto" accept="image/*"><input type="file" id="cv" accept=".pdf,.doc">')
    feitos = preencher_vazios(pagina, [campo_curriculo(cv)], set())
    assert feitos == ["Currículo (arquivo)"]
    assert pagina.evaluate("document.getElementById('cv').files.length") == 1
    assert pagina.evaluate("document.getElementById('foto').files.length") == 0      # foto não recebe currículo
    pagina.close()
    assert dominio_raiz("https://omega.gupy.io/jobs/1") == "gupy.io"
    assert dominio_raiz("https://www.vagas.com.br/vagas/v1") == "vagas.com.br"
    assert dominio_raiz("https://br.linkedin.com/jobs/view/1") == "linkedin.com"


# ---------------------------------------------------------------- região (BH e RMBH), andamento e currículo

def test_regiao_so_bh_e_regiao_metropolitana():
    from agente_carreira.radar.filtros import na_regiao
    from agente_carreira.radar.modelos import REGIAO_BH

    assert len(REGIAO_BH) == 34
    for local in ("Belo Horizonte e Região (Presencial)", "Região Metropolitana de Belo Horizonte", "Grande BH",
                  "Ribeirão das Neves, MG", "Esmeraldas - MG", "Nova Lima, Minas Gerais, Brasil", "BH"):
        assert na_regiao(local, REGIAO_BH), local
    for local in ("São Paulo e Região", "Uberlândia, MG", "Vitória, ES"):
        assert not na_regiao(local, REGIAO_BH), local


def test_sem_modelo_fora_da_regiao_e_presencial_sem_local_saem():
    from agente_carreira.models import Formacao
    from agente_carreira.radar.filtros import avaliar_filtros

    perfil = PerfilMestre(contato=Contato(nome="Ana", email="a@example.com"),
                          formacao=[Formacao(curso="SI", instituicao="PUC", status="cursando", conclusao_prevista="2027/1")])
    config = ConfigVagas(buscas=[BuscaSalva(nome="b", cargos=["desenvolvedor"])])
    _, motivos = avaliar_filtros(VagaEncontrada(titulo="Desenvolvedor", local="São Paulo, SP"), config, perfil, date.today())
    assert any("fora da região" in m for m in motivos)                   # sem modelo = presencial
    _, motivos = avaliar_filtros(VagaEncontrada(titulo="Desenvolvedor", modelo="presencial"), config, perfil, date.today())
    assert any("sem local" in m for m in motivos)
    _, motivos = avaliar_filtros(VagaEncontrada(titulo="Desenvolvedor", modelo="remoto", local="Vitória, ES"), config,
                                 perfil, date.today())
    assert motivos == []                                                  # remoto vale de qualquer lugar


def test_cidade_com_nova_nao_e_selo_e_local_do_topo_do_linkedin():
    from agente_carreira.radar.coleta import separar_empresa_local

    assert separar_empresa_local("Brandt", "Nova Lima, Minas Gerais, Brasil") == ("Brandt", "Nova Lima, Minas Gerais, Brasil")
    assert separar_empresa_local("Brandt · Nova Lima, MG (Presencial)", "22 ex-alunos da instituição de ensino") == (
        "Brandt", "Nova Lima, MG (Presencial)")
    topo = ("Brandt\n\nEstágio\n\nNova Lima, Minas Gerais, Brasil  · há 4 dias · 94 pessoas clicaram\n\nPresencial\nEstágio")
    assert auto.local_e_modelo_do_topo(topo) == ("Nova Lima, Minas Gerais, Brasil", "presencial")


def test_vaga_ja_recomendada_e_eliminada_quando_as_regras_mudam():
    from agente_carreira.radar.rodada import reavaliar_base

    perfil = PerfilMestre(contato=Contato(nome="Ana", email="a@example.com"))
    config = ConfigVagas(buscas=[BuscaSalva(nome="b", cargos=["desenvolvedor"])])
    base = BaseVagas(itens=[VagaEncontrada(id="x", titulo="Desenvolvedor", status="no_resumo", local="Curitiba, PR")])
    reavaliar_base(base, perfil, config, date.today())
    assert base.itens[0].status == "eliminada"


def test_andamento_registra_etapas_e_detecta_fim():
    from agente_carreira.operacao import andamento

    with andamento.tarefa("Busca de vagas") as registro:
        andamento.etapa("Lendo as descrições", 3, 10)
        estado = andamento.ler()
        assert estado["rodando"] and "(3 de 10)" in andamento.descrever(estado)
        assert andamento.em_andamento("Busca de vagas") is not None
        registro["resultado"] = "5 vaga(s) nova(s)"
    estado = andamento.ler()
    assert not estado["rodando"] and "5 vaga(s) nova(s)" in andamento.descrever(estado)
    assert any("começou" in l for l in andamento.ultimas_linhas())          # log só guarda etapas marcantes
    andamento.etapa("sem tarefa: não faz nada")                           # fora de uma tarefa, ignora


def test_curriculo_html_ats_e_competencias_agrupadas():
    from agente_carreira.analise.cv_html import agrupar_competencias, html_curriculo
    from agente_carreira.analise.variantes import ItemCV, SecaoCV, VarianteCV

    grupos = dict(agrupar_competencias("C#, .NET, HTML5, CSS3, MySQL, Git, Scrum, Resolução de problemas"))
    assert grupos["linguagens"] == ["C#"] and grupos["front"] == ["HTML5", "CSS3"]
    assert "Resolução de problemas" in grupos["metodos"]
    v = VarianteCV(foco="x", idioma="pt", nivel="estagio", nome="Ana <Souza>", cabecalho=["a@b.com | https://github.com/ana"],
                   secoes=[SecaoCV(titulo="Competências", paragrafo="C#, Git"),
                           SecaoCV(titulo="Idiomas", itens=[ItemCV(titulo="Inglês", subtitulo="intermediário")])])
    pagina = html_curriculo(v)
    assert "&lt;Souza&gt;" in pagina and "github.com/ana" in pagina and "https://" not in pagina
    assert "<table" not in pagina and "<img" not in pagina                # ATS: sem tabelas nem imagens
    assert "<b>Inglês</b> (intermediário)" in pagina


def test_navegador_ocupado_diz_o_que_esta_usando(tmp_path):
    import json
    import os

    from agente_carreira.navegador import NavegadorOcupado, _Trava, uso_atual_do_navegador
    from agente_carreira.storage import diretorio_dados

    (diretorio_dados() / "navegador.dono").write_text(json.dumps({"uso": "a candidatura no site da vaga",
                                                                   "pid": os.getpid()}), encoding="utf-8")
    assert uso_atual_do_navegador() == "a candidatura no site da vaga"
    primeira, segunda = _Trava(diretorio_dados() / "navegador.trava"), _Trava(diretorio_dados() / "navegador.trava")
    primeira.adquirir()
    with pytest.raises(NavegadorOcupado, match="aberto em: a candidatura no site da vaga"):
        segunda.adquirir()
    primeira.soltar()


# ---------------------------------------------------------------- vaga que não aceita mais candidaturas

TOPO_ENCERRADA = ("Tata Consultancy Services\nAnalista de Dados Junior (Databricks)\n"
                  "Belo Horizonte, Minas Gerais, Brasil · há 6 meses · Mais de 100 candidaturas\n"
                  "Promovida por quem está contratando · Ainda não há estatísticas de resposta disponíveis\n"
                  "Presencial\nContrato\nNão aceita mais candidaturas\n")


@pytest.mark.parametrize("topo, encerrada, dias", [
    (TOPO_ENCERRADA, "Não aceita mais candidaturas", 180),
    ("Nova Lima, Minas Gerais, Brasil · há 4 dias · 94 pessoas clicaram\nPresencial", None, 4),
    ("Contagem, MG · Republicada há uma semana · 12 candidaturas", None, 7),
    ("Belo Horizonte · 3 weeks ago · Over 100 applicants\nNo longer accepting applications", "No longer accepting applications", 21),
    ("Belo Horizonte, MG · há 5 horas", None, 0),
])
def test_topo_da_vaga_diz_se_fechou_e_quando_foi_publicada(topo, encerrada, dias):
    from datetime import timedelta

    hoje = date(2026, 11, 19)
    assert auto.situacao_do_topo(topo, hoje) == (encerrada, hoje - timedelta(days=dias))


def test_vaga_que_nao_aceita_mais_candidaturas_sai_da_lista():
    """O caso real: veio de um alerta de e-mail, foi recomendada, e no LinkedIn já estava fechada havia meses."""
    from datetime import timedelta

    from agente_carreira.radar.rodada import expirar, precisa_conferir

    class Vazio:
        def count(self):
            return 0

    class Pagina:
        url = "https://www.linkedin.com/jobs/view/4416453564"

        def goto(self, *_a, **_k):
            pass

        def evaluate(self, js):
            return [] if "ld+json" in js else TOPO_ENCERRADA

        def locator(self, _seletor):
            return Vazio()

        def title(self):
            return "Analista de Dados Junior (Databricks) | Tata Consultancy Services | LinkedIn"

    class Sessao:
        pagina = Pagina()

        def __init__(self, **_k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    vaga = VagaEncontrada(id="t", titulo="Analista de Dados Junior (Databricks)", empresa="Tata Consultancy Services",
                          local="Belo Horizonte, Minas Gerais, Brasil", link=Pagina.url, status="no_resumo",
                          descricao="Sobre a vaga: dados com Python e SQL.", publicada_em=date.today(),
                          aderencia=Aderencia(nota=62))
    assert precisa_conferir(vaga)  # aberta, com link e nunca conferida
    enriquecer = auto.enriquecedor_da_rodada(LinkedInAutomatico(), RegistroSaude(), abrir_sessao=Sessao,
                                             dormir=lambda _s: None)
    assert enriquecer([vaga]) == 1
    assert vaga.motivo_expiracao == "o LinkedIn diz: Não aceita mais candidaturas"
    assert vaga.publicada_em <= date.today() - timedelta(days=170)  # a data do e-mail dava a vaga como nova
    assert not precisa_conferir(vaga)  # acabou de ser conferida
    base = BaseVagas(itens=[vaga])
    assert [v.id for v in expirar(base, date.today(), ConfigVagas())] == ["t"] and vaga.status == "expirada"


def test_vaga_conferida_ha_pouco_ou_fora_da_lista_nao_e_aberta_de_novo():
    from datetime import timedelta

    from agente_carreira.radar.rodada import precisa_conferir

    agora = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
    vaga = VagaEncontrada(titulo="Dev", link="https://www.linkedin.com/jobs/view/1", status="no_resumo",
                          conferida_em=agora - timedelta(days=1))
    assert not precisa_conferir(vaga, agora)
    vaga.conferida_em = agora - timedelta(days=3)
    assert precisa_conferir(vaga, agora)
    vaga.status = "eliminada"
    assert not precisa_conferir(vaga, agora)


def test_texto_de_vaga_fechada_no_anuncio():
    from agente_carreira.radar.filtros import PADRAO_ENCERRADA

    for texto in ("Não aceita mais candidaturas", "This job has expired", "Esta vaga expirou", "Candidaturas encerradas"):
        assert PADRAO_ENCERRADA.search(texto), texto


# ---------------------------------------------------------------- perguntas do formulário (RF-EV-07 e RF-EV-08)

FORM_PERGUNTAS = """
<form onsubmit="window.enviado = true; return false">
  <div><p>Qual a sua pretensão salarial (bolsa) para o estágio?</p><input id="pretensao" type="text"></div>
  <div><label for="ingles">Qual o seu nível de inglês?</label>
    <select id="ingles"><option>Selecione</option><option>Básico</option><option>Intermediário</option></select></div>
  <div><label for="genero">Com qual gênero você se identifica?</label><input id="genero"></div>
  <div><label for="carta">Carta de apresentação</label><textarea id="carta"></textarea></div>
  <div><label for="viagem">Tem disponibilidade para viagens?</label><input id="viagem"></div>
  <div><label for="ja">Por que você quer trabalhar aqui?</label><input id="ja" value="Porque sim"></div>
  <input type="search" id="busca" placeholder="Buscar vagas">
  <button type="submit">Enviar candidatura</button>
</form>"""


def test_responde_perguntas_so_com_respostas_aprovadas(navegador):
    from agente_carreira.preenchimento_auto import responder_perguntas

    respostas = {"pretensao": "R$ 1.500", "ingles": "Básico"}

    def responder(rotulo: str) -> str | None:
        if "pretens" in rotulo.lower():
            return respostas["pretensao"]
        if "ingl" in rotulo.lower():
            return respostas["ingles"]
        if "gênero" in rotulo.lower():
            return "não deveria ser usado"
        return None

    pagina = navegador.new_page()
    pagina.set_content(FORM_PERGUNTAS)
    ja = set()
    feitos = responder_perguntas(pagina, responder, "Olá! Sou estudante de Sistemas de Informação...", ja)
    valor = lambda i: pagina.locator(f"#{i}").input_value()
    assert valor("pretensao") == "R$ 1.500"
    assert pagina.locator("#ingles").evaluate("e => e.options[e.selectedIndex].text") == "Básico"
    assert valor("carta").startswith("Olá! Sou estudante")      # a mensagem da vaga vai no campo de apresentação
    assert valor("genero") == ""                                 # diversidade é sua
    assert valor("viagem") == ""                                 # sem resposta aprovada: fica para você
    assert valor("ja") == "Porque sim"                           # nunca sobrescreve
    assert pagina.evaluate("window.enviado") is None             # nunca envia
    assert len(feitos) == 3
    assert responder_perguntas(pagina, responder, "x", ja) == []  # não repete
    pagina.close()


# ---------------------------------------------------------------- RF-EV-03: página nova de resultados

PAGINA_NOVA = """
<main><p>21 resultados</p>
<div role="button" componentkey="job-card-component-ref-4491521055"><p>Selecionada, Vaga de Estágio - TI - MG2026</p>
  <p>Vaga de Estágio - TI - MG2026</p><p>Faculdade Católica Paulista</p><p>Belo Horizonte, MG</p>
  <p>3 ex-alunos da instituição trabalham aqui</p></div>
<div role="button" componentkey="job-card-component-ref-4492972409"><p>Robotics Intern</p><p>Pronto</p>
  <p>Nova Lima, MG (Presencial)</p><p>Visto</p><p>·</p></div>
<div role="button" componentkey="job-card-component-ref-4492000001"><p>Desenvolvedor .Net (vaga verificada)</p>
  <p>Desenvolvedor .Net</p><p>Jobbol</p><p>Belo Horizonte, MG (Remoto)</p><p>Anunciada há 2 dias</p></div>
<div role="button" componentkey="auto-component-x"><p>Última semana</p></div>
</main>"""


def test_cartoes_da_pagina_nova_do_linkedin(navegador):
    pagina = navegador.new_page()
    pagina.set_content(PAGINA_NOVA)
    vagas = auto.cartoes_para_vagas(pagina.evaluate(auto.JS_CARTOES))
    assert [(v.titulo, v.empresa, v.local, v.link) for v in vagas] == [
        ("Vaga de Estágio - TI - MG2026", "Faculdade Católica Paulista", "Belo Horizonte, MG",
         "https://www.linkedin.com/jobs/view/4491521055"),
        ("Robotics Intern", "Pronto", "Nova Lima, MG (Presencial)", "https://www.linkedin.com/jobs/view/4492972409"),
        ("Desenvolvedor .Net", "Jobbol", "Belo Horizonte, MG (Remoto)", "https://www.linkedin.com/jobs/view/4492000001"),
    ]
    pagina.close()


# ---------------------------------------------------------------- RF-EV-16: réplicas das páginas reais (sem dados pessoais)

CAIXA_OUTLOOK = """
<input aria-label="Pesquisar">
<div role="listbox">
  <div role="option" data-convid="AAQkAD1" aria-label="Não lidos LinkedIn Vagas Estágio em TI em Belo Horizonte"></div>
  <div role="option" data-convid="AAQkAD2" aria-label="Gupy Atualização da sua candidatura"></div>
</div>"""


def test_replica_da_caixa_do_outlook(navegador):
    from agente_carreira.radar.outlook_web import JS_LINHAS, SELETOR_PESQUISA, nao_lido

    pagina = navegador.new_page()
    pagina.set_content(CAIXA_OUTLOOK)
    assert pagina.locator(SELETOR_PESQUISA).count() == 1
    linhas = pagina.evaluate(JS_LINHAS)
    assert [l["convid"] for l in linhas] == ["AAQkAD1", "AAQkAD2"]
    assert [nao_lido(l["rotulo"]) for l in linhas] == [True, False]  # o não lido continua não lido depois
    pagina.close()
