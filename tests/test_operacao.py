"""Testes do M8 — operação (RF-OP-01 a RF-OP-07)."""

import json
from datetime import date, datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

import pytest

from agente_carreira.configuracao import (
    MODOS_PADRAO,
    Configuracao,
    ModoSomenteSugestao,
    carregar_configuracao,
    definir,
    exigir_plataforma,
    plataforma_da_url,
    plataforma_permite_leitura,
    salvar_configuracao,
)
from agente_carreira.ia import UsosIA, carregar_usos, registrar_pedido, salvar_usos
from agente_carreira.linkedin.estado import carregar_log
from agente_carreira.linkedin.pendentes import carregar_pendentes, enfileirar, salvar_pendentes
from agente_carreira.linkedin.propostas import Proposta
from agente_carreira.linkedin.publicacoes import Publicacao, Publicacoes, carregar_publicacoes, salvar_publicacoes
from agente_carreira.models import Contato, Formacao, PerfilMestre
from agente_carreira.operacao import fila
from agente_carreira.operacao.auditoria import listar_acoes, registrar_acao
from agente_carreira.operacao.notificacoes import notificar
from agente_carreira.operacao.saude import LIMITE_FALHAS, LayoutMudou, RegistroSaude, verificar_campos
from agente_carreira.operacao.tarefas import (
    Tarefas,
    cancelar,
    confirmar_passo,
    criar_tarefa,
    falhar,
    garantir_tarefa_rodada,
    pausar,
    retomar,
)
from agente_carreira.radar.modelos import BaseVagas, BuscaSalva, ConfigVagas, EmpresaAlvo, SINONIMOS_POR_FOCO
from agente_carreira.radar.rodada import coletar, executar_rodada


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- RF-OP-01

def test_preferencias_centralizadas_com_padroes_da_especificacao():
    c = Configuracao()
    assert c.limites.candidaturas_por_dia == 10 and c.limites.aderencia_minima_candidatura == 60
    assert c.limites.mensagens_por_dia == 5 and c.limites.acoes_por_sessao == 20
    assert c.modos_plataforma["linkedin"] == "copiloto" and c.modos_plataforma["gupy"] == "assistido"
    assert c.notificacao.canal == "email" and c.horarios.resumo_ate == "08:00"
    assert c.motor_da_tarefa("reescrita-cv") == "perguntar"
    assert c.vagas.limiar_alerta == 80


def test_definir_por_caminho_com_validacao():
    c = Configuracao()
    c = definir(c, "limites.candidaturas_por_dia", "8")
    c = definir(c, "somente_sugestao", "sim")
    c = definir(c, "notificacao.canal", "push")
    c = definir(c, "modos_plataforma.gupy", "copiloto")
    c = definir(c, "vagas.dominios_permitidos", "gupy.io, empresa.com")
    c = definir(c, "notificacao.eventos.resumo_diario", "false")
    assert c.limites.candidaturas_por_dia == 8 and c.somente_sugestao is True
    assert c.notificacao.canal == "push" and c.modos_plataforma["gupy"] == "copiloto"
    assert c.vagas.dominios_permitidos == ["gupy.io", "empresa.com"]
    assert c.notificacao.eventos["resumo_diario"] is False


@pytest.mark.parametrize("caminho, valor, mensagem", [
    ("limites.inexistente", "1", "desconhecida"),
    ("notificacao.canal", "fax", "inválido"),
    ("modos_plataforma.gupy", "turbo", "inválido"),
    ("limites.candidaturas_por_dia", "muitas", "inválido"),
    ("vagas.buscas", "x", "agente busca"),
    ("limites", "1", "grupo"),
])
def test_definir_rejeita_valores_invalidos(caminho, valor, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        definir(Configuracao(), caminho, valor)


def test_migra_preferencias_de_vagas_do_arquivo_antigo(dados_em_tmp):
    antigo = ConfigVagas(buscas=[BuscaSalva(nome="b", cargos=["dev"])], limiar_alerta=75)
    (dados_em_tmp / "vagas-config.json").write_text(antigo.model_dump_json(), encoding="utf-8")
    (dados_em_tmp / "configuracao.json").write_text(json.dumps({"motores": {"reescrita-cv": "gemini"}}), encoding="utf-8")
    c = carregar_configuracao()
    assert c.vagas.buscas[0].nome == "b" and c.vagas.limiar_alerta == 75
    assert c.motores == {"reescrita-cv": "gemini"}                       # preferências antigas preservadas
    assert not (dados_em_tmp / "vagas-config.json").exists()
    assert (dados_em_tmp / "vagas-config.json.migrado").exists()


# ---------------------------------------------------------------- RF-OP-02

def test_plataforma_por_dominio_e_modo():
    c = Configuracao()
    assert plataforma_da_url("https://empresa.gupy.io/jobs/1") == "gupy"
    assert plataforma_da_url("https://www.linkedin.com/jobs/view/1") == "linkedin"
    assert plataforma_da_url("https://carreiras.empresa.com/vagas") == "paginas-de-carreira"
    assert plataforma_permite_leitura(c, "https://empresa.gupy.io/jobs/1")
    c.modos_plataforma["gupy"] = "desligado"
    assert not plataforma_permite_leitura(c, "https://empresa.gupy.io/jobs/1")
    assert plataforma_permite_leitura(c, "https://carreiras.empresa.com/vagas")


def test_somente_sugestao_bloqueia_todas_as_plataformas():
    c = Configuracao(somente_sugestao=True)
    assert not plataforma_permite_leitura(c, "https://carreiras.empresa.com/vagas")
    with pytest.raises(ModoSomenteSugestao, match="nenhuma plataforma"):
        exigir_plataforma(c, "a leitura da página")
    exigir_plataforma(Configuracao(), "a leitura da página")      # desligado: segue


def _perfil() -> PerfilMestre:
    return PerfilMestre(
        contato=Contato(nome="Samuel", email="s@example.com", cidade="Belo Horizonte"),
        competencias_tecnicas=["C#", ".NET"],
        formacao=[Formacao(curso="SI", instituicao="PUC", status="cursando", conclusao_prevista=f"{date.today().year + 1}/2")],
    )


def _config_vagas() -> ConfigVagas:
    busca = BuscaSalva(nome="backend-dotnet", cargos=SINONIMOS_POR_FOCO["backend-dotnet"],
                       empresas_alvo=[EmpresaAlvo(nome="Omega", pagina_carreira="https://omega.gupy.io/")])
    return ConfigVagas(buscas=[busca])


def test_rodada_em_somente_sugestao_nao_toca_nenhuma_pagina(dados_em_tmp):
    chamadas = []

    def baixar_fn(url):
        chamadas.append(url)
        return 200, ""

    central = Configuracao(somente_sugestao=True)
    resultado = executar_rodada(
        _perfil(), _config_vagas(), BaseVagas(), date.today(), pasta_emails=None, imap=None, baixar_fn=baixar_fn,
        dormir=lambda s: None, motor_justificativa="local", pode_ler=lambda url: plataforma_permite_leitura(central, url),
    )
    assert chamadas == []
    assert any("somente sugestão" in e for e in resultado.erros)


# ---------------------------------------------------------------- RF-OP-03

def test_retomar_do_ultimo_passo_confirmado_sem_duplicar():
    tarefas = Tarefas()
    t = criar_tarefa(tarefas, "cadastro-gupy", "Cadastro na Gupy", [("nome", "Nome"), ("email", "E-mail"), ("cpf", "CPF")])
    assert confirmar_passo(t, "nome") is True
    assert confirmar_passo(t, "nome") is False                # retomada não duplica
    pausar(t)
    assert t.status == "pausada"
    proximo = retomar(t)
    assert proximo.nome == "email" and t.ultimo_confirmado().nome == "nome"
    confirmar_passo(t, "email")
    confirmar_passo(t, "cpf", pulado=True)
    assert t.status == "concluida" and t.progresso == "3/3"


def test_cancelar_e_falha_retomavel():
    tarefas = Tarefas()
    t = criar_tarefa(tarefas, "x", "X", [("a", "A"), ("b", "B")])
    confirmar_passo(t, "a")
    falhar(t, "layout mudou")
    assert t.status == "falhou" and t.erro == "layout mudou"
    assert retomar(t).nome == "b" and t.erro is None
    cancelar(t)
    with pytest.raises(ValueError):
        retomar(t)                                            # cancelada não volta (não recorrente)
    with pytest.raises(ValueError):
        pausar(t)


def test_rodada_recorrente_bloqueia_quando_pausada_e_volta_ao_retomar():
    tarefas = Tarefas()
    rodada = garantir_tarefa_rodada(tarefas)
    assert garantir_tarefa_rodada(tarefas) is rodada          # uma só
    assert not rodada.bloqueada
    pausar(rodada)
    assert rodada.bloqueada
    retomar(rodada)
    cancelar(rodada)
    assert rodada.bloqueada
    retomar(rodada)                                           # recorrente: pode voltar mesmo cancelada
    falhar(rodada, "erro de rede")
    assert rodada.status == "ativa" and "erro de rede" in rodada.dados["ultima_falha"]


# ---------------------------------------------------------------- RF-OP-05

def _popular_fila():
    usos = UsosIA()
    uso = registrar_pedido(usos, tarefa="justificativa-vagas", descricao="justificar", motor="claude",
                           dados=["2 vagas"], prompt="texto (para o motor claude; fim)", removidos={},
                           nome_arquivo="prompt-justificativas-claude.md", autorizado=False)
    salvar_usos(usos)
    salvar_publicacoes(Publicacoes(itens=[Publicacao(titulo="API", texto="Post sobre a API")]))
    pendentes = carregar_pendentes()
    enfileirar(pendentes, [Proposta(campo="titulo", rotulo="Título", anterior="Antigo", novo="Desenvolvedor .NET")])
    salvar_pendentes(pendentes)
    return uso


def test_fila_unica_reune_ia_publicacoes_e_linkedin():
    _popular_fila()
    itens = fila.listar_fila()
    assert {i.id.split(":")[0] for i in itens} == {"ia", "post", "li"}
    li = next(i for i in itens if i.id.startswith("li:"))
    assert (li.antes, li.depois) == ("Antigo", "Desenvolvedor .NET")


def test_aprovar_cada_tipo(dados_em_tmp):
    uso = _popular_fila()
    por_tipo = {i.id.split(":")[0]: i.id for i in fila.listar_fila()}

    d_ia = fila.aprovar(por_tipo["ia"], motor="gemini")
    assert Path(d_ia.arquivo).name == "prompt-justificativas-gemini.md"
    assert carregar_usos().buscar(uso.id).autorizacao == "aprovado"

    d_post = fila.aprovar(por_tipo["post"])
    assert d_post.texto_para_copiar == "Post sobre a API" and "publicado" in d_post.proximo_passo
    assert carregar_publicacoes().itens[0].status == "aprovado"

    d_li = fila.aprovar(por_tipo["li"])
    entrada = carregar_log().entradas[0]
    assert d_li.entrada_log == entrada.id and entrada.status == "aprovado" and entrada.novo == "Desenvolvedor .NET"
    assert fila.listar_fila() == []


def test_rejeitar_cada_tipo():
    uso = _popular_fila()
    for item in fila.listar_fila():
        fila.rejeitar(item.id)
    assert fila.listar_fila() == []
    assert carregar_usos().buscar(uso.id).autorizacao == "descartado"
    assert carregar_publicacoes().itens[0].status == "rejeitado"
    assert carregar_log().entradas == []                     # nada aprovado no LinkedIn


def test_editar_mantem_na_fila_e_valida():
    uso = _popular_fila()
    por_tipo = {i.id.split(":")[0]: i.id for i in fila.listar_fila()}
    fila.editar(por_tipo["ia"], motor="gemini")
    assert carregar_usos().buscar(uso.id).motor == "gemini"
    with pytest.raises(ValueError, match="motor"):
        fila.editar(por_tipo["ia"], texto="x")
    fila.editar(por_tipo["post"], texto="Versão nova do post", motor="claude")
    assert carregar_publicacoes().itens[0].motor == "claude"
    decisao = fila.editar(por_tipo["li"], texto="x" * 300)
    assert "Atenção" in decisao.mensagem
    with pytest.raises(ValueError, match="limite"):
        fila.aprovar(por_tipo["li"])                          # acima de 220: não aprova
    assert len(fila.listar_fila()) == 3


def test_enfileirar_nao_duplica_campo():
    pendentes = carregar_pendentes()
    p = Proposta(campo="sobre", rotulo="Sobre", novo="Texto")
    assert enfileirar(pendentes, [p]) == 1
    assert enfileirar(pendentes, [p]) == 0


def test_id_invalido_na_fila():
    with pytest.raises(ValueError, match="não existe"):
        fila.aprovar("xyz")


# ---------------------------------------------------------------- RF-OP-06

def test_auditoria_so_acrescenta_e_guarda_captura(dados_em_tmp):
    captura = dados_em_tmp / "tela.png"
    captura.write_bytes(b"\x89PNG")
    agora = datetime.now(timezone.utc)
    a1 = registrar_acao(plataforma="linkedin", acao="alterar campo", alvo="Título", antes="A", depois="B",
                        aprovado_em=agora, origem_aprovacao="log LinkedIn 1", captura=captura)
    registrar_acao(plataforma="linkedin", acao="publicar post", alvo="API", depois="Post", origem_aprovacao="publicação 9")
    registrar_acao(plataforma="gupy", acao="salvar cadastro", alvo="Experiência", origem_aprovacao="fila")
    linhas = (dados_em_tmp / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 3
    acoes = listar_acoes("linkedin")
    assert [a.acao for a in acoes] == ["alterar campo", "publicar post"]
    assert acoes[0].antes == "A" and acoes[0].depois == "B" and acoes[0].aprovado_em == agora
    assert Path(a1.captura).read_bytes() == b"\x89PNG" and a1.id in a1.captura


# ---------------------------------------------------------------- RF-OP-04

def test_notifica_por_email_e_guarda_arquivo():
    enviados = []
    c = Configuracao()
    c.notificacao.email_para = "eu@example.com"
    env = {"AGENTE_SMTP_HOST": "smtp.x", "AGENTE_SMTP_USUARIO": "u@x", "AGENTE_SMTP_SENHA": "s"}
    r = notificar("resumo_diario", "Resumo", "3 vagas", c, ambiente=env,
                  envio_email=lambda smtp, para, titulo, corpo: enviados.append((smtp["host"], para, titulo)))
    assert r.canal == "email" and r.erro is None and r.arquivo.is_file()
    assert enviados == [("smtp.x", "eu@example.com", "Resumo")]


def test_notifica_por_push():
    enviados = []
    c = Configuracao()
    c.notificacao.canal = "push"
    r = notificar("vaga_acima_limiar", "1 vaga ≥ 80", "Dev .NET", c, ambiente={"AGENTE_NTFY_TOPICO": "segredo"},
                  envio_push=lambda servidor, topico, titulo, corpo: enviados.append((servidor, topico)))
    assert r.canal == "push" and enviados == [("https://ntfy.sh", "segredo")]


def test_sem_configuracao_ou_com_falha_fica_em_arquivo():
    c = Configuracao()
    r = notificar("pedido_aprovacao", "Fila", "1 item", c, ambiente={})
    assert r.canal == "arquivo" and "não configurado" in r.erro
    assert "Ficou só neste arquivo" in r.arquivo.read_text(encoding="utf-8")

    def quebra(*args):
        raise OSError("conexão recusada")
    c.notificacao.canal = "push"
    r = notificar("falha_adaptador", "x", "y", c, ambiente={"AGENTE_NTFY_TOPICO": "t"}, envio_push=quebra)
    assert r.canal == "arquivo" and "conexão recusada" in r.erro


def test_evento_desligado_nao_notifica():
    c = Configuracao()
    c.notificacao.eventos["resumo_diario"] = False
    assert notificar("resumo_diario", "x", "y", c, ambiente={}) is None


# ---------------------------------------------------------------- RF-OP-07

def test_falhas_seguidas_param_o_adaptador():
    saude = RegistroSaude()
    for _ in range(LIMITE_FALHAS - 1):
        assert saude.falha("pagina:Omega", "HTTP 500") is False
        assert saude.obter("pagina:Omega").status == "degradado"
    assert saude.falha("pagina:Omega", "HTTP 500") is True
    assert not saude.pode_usar("pagina:Omega")
    saude.reativar("pagina:Omega")
    assert saude.pode_usar("pagina:Omega")
    saude.falha("pagina:Omega", "erro")
    saude.sucesso("pagina:Omega")
    assert saude.obter("pagina:Omega").falhas_seguidas == 0


def test_conferencia_de_campos_antes_de_preencher():
    verificar_campos(["nome", "email"], ["nome", "email", "telefone"])
    with pytest.raises(LayoutMudou, match="email"):
        verificar_campos(["nome", "email"], ["nome", "e-mail"])


def _alerta_quebrado() -> EmailMessage:
    """Alerta do LinkedIn cujo layout mudou: tem links de vaga, mas nenhum título reconhecível."""
    msg = EmailMessage()
    msg["From"] = "jobalerts-noreply@linkedin.com"
    msg["Message-ID"] = "<quebrado@x>"
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg.set_content("https://www.linkedin.com/comm/jobs/view/3901234567/\n\nhttps://www.linkedin.com/comm/jobs/view/3909999999/\n")
    return msg


def test_layout_novo_no_email_para_o_adaptador_e_guarda_o_email(dados_em_tmp):
    pasta = dados_em_tmp / "caixa"
    pasta.mkdir()
    (pasta / "a.eml").write_bytes(_alerta_quebrado().as_bytes())
    base, saude = BaseVagas(), RegistroSaude()
    brutas, erros, falhas = coletar(ConfigVagas(), base, date.today(), pasta_emails=pasta, imap=None,
                                    saude=saude, usar_paginas=False)
    assert brutas == [] and falhas and "layout do e-mail mudou" in falhas[0]
    assert saude.obter("email:linkedin").status == "parado"
    assert (pasta / "a.eml").exists() and base.emails_processados == []   # guardado para reprocessar

    # Parado: a próxima rodada não tenta de novo nem marca como lido.
    _, erros2, falhas2 = coletar(ConfigVagas(), base, date.today(), pasta_emails=pasta, imap=None,
                                 saude=saude, usar_paginas=False)
    assert falhas2 == [] and any("adaptador parado" in e for e in erros2)


def test_pagina_sem_estrutura_conta_como_falha_e_para_depois_do_limite(dados_em_tmp):
    saude = RegistroSaude()
    config = _config_vagas()

    def baixar_fn(url):
        return (404, "") if url.endswith("robots.txt") else (200, "<html><body>Em manutenção</body></html>")

    for rodada in range(LIMITE_FALHAS):
        _, erros, falhas = coletar(config, BaseVagas(), date.today(), pasta_emails=None, imap=None,
                                   baixar_fn=baixar_fn, dormir=lambda s: None, saude=saude)
        assert any("layout mudou" in e for e in erros)
    assert falhas and saude.obter("pagina:Omega").status == "parado"
    _, erros, _ = coletar(config, BaseVagas(), date.today(), pasta_emails=None, imap=None,
                          baixar_fn=baixar_fn, dormir=lambda s: None, saude=saude)
    assert any("adaptador parado" in e for e in erros)
