"""Testes de RF-IA-06 (autoria de cada texto) e RF-IA-07 (recusa por limite de uso)."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from agente_carreira.ia import (
    HORAS_LIMITE,
    UsosIA,
    autoria,
    motor_em_limite,
    prompt_para_outro_motor,
    registrar_pedido,
    registrar_recusa,
    resposta_e_recusa_por_limite,
    sugerir_motor,
    ultimo_aprovado,
)
from agente_carreira.linkedin.pendentes import carregar_pendentes, enfileirar, salvar_pendentes
from agente_carreira.linkedin.propostas import Proposta
from agente_carreira.linkedin.publicacoes import Publicacao, Publicacoes, carregar_publicacoes, salvar_publicacoes
from agente_carreira.operacao import fila
from agente_carreira.operacao.auditoria import listar_acoes, registrar_acao
from agente_carreira.radar.modelos import ConfigVagas, VagaEncontrada
from agente_carreira.radar.resumo import item_resumo, montar_resumo, resumo_markdown


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- RF-IA-06

@pytest.mark.parametrize("motor, esperado", [
    ("claude", "Claude Pro"), ("gemini", "Gemini Pro"), ("usuario", "você"),
    (None, "agente (motor local)"), ("local", "agente (motor local)"),
])
def test_autoria(motor, esperado):
    assert autoria(motor) == esperado


def test_fila_mostra_quem_escreveu_e_edicao_vira_do_usuario():
    salvar_publicacoes(Publicacoes(itens=[Publicacao(titulo="API", texto="Post", motor="claude")]))
    pendentes = carregar_pendentes()
    enfileirar(pendentes, [Proposta(campo="titulo", rotulo="Título", novo="Dev .NET")], motor="gemini")
    salvar_pendentes(pendentes)
    itens = {i.id.split(":")[0]: i for i in fila.listar_fila()}
    assert "escrito por: Claude Pro" in itens["post"].detalhes
    assert "escrito por: Gemini Pro" in itens["li"].detalhes

    fila.editar(itens["post"].id, texto="Minha versão")
    fila.editar(itens["li"].id, texto="Desenvolvedor .NET Júnior")
    itens = {i.id.split(":")[0]: i for i in fila.listar_fila()}
    assert "escrito por: você" in itens["post"].detalhes and "escrito por: você" in itens["li"].detalhes
    assert carregar_publicacoes().itens[0].motor == "usuario"


def test_auditoria_guarda_autoria():
    registrar_acao(plataforma="linkedin", acao="publicar post", alvo="API", depois="Post",
                   origem_aprovacao="publicação 1", autoria=autoria("gemini"))
    assert listar_acoes()[0].autoria == "Gemini Pro"


def test_resumo_identifica_motor_local_e_motor_da_justificativa():
    config = ConfigVagas()
    vaga = VagaEncontrada(titulo="Dev .NET", empresa="Omega", descricao="C#",
                          justificativa_ia="Combina pelo C#.", motor_justificativa="claude")
    item = item_resumo(vaga, config)
    assert item.autoria_justificativa == "Claude Pro"
    from agente_carreira.radar.modelos import BaseVagas
    md = resumo_markdown(montar_resumo(BaseVagas(itens=[vaga]), config, date.today()), config)
    assert "**Motivo (agente (motor local)):**" in md
    assert "**Justificativa (Claude Pro):** Combina pelo C#." in md


# ---------------------------------------------------------------- RF-IA-07

@pytest.mark.parametrize("texto", [
    "You've reached your usage limit. Please try again after 3:00 PM.",
    "Você atingiu o limite de mensagens. Tente novamente mais tarde.",
    "Quota exceeded for Gemini. Try again later.",
    "Limite de uso atingido para o seu plano.",
])
def test_reconhece_recusa_por_limite(texto):
    assert resposta_e_recusa_por_limite(texto)


def test_resposta_de_verdade_nao_e_recusa():
    longa = "### CAMPO: en:sobre\n" + "Backend developer with a usage limit API project. " * 20
    assert not resposta_e_recusa_por_limite(longa)
    assert not resposta_e_recusa_por_limite("### CAMPO: en:titulo\nBackend Developer | C# · .NET")
    assert not resposta_e_recusa_por_limite("")


def _uso_aprovado(usos: UsosIA, motor: str = "claude"):
    return registrar_pedido(
        usos, tarefa="traducao-linkedin", descricao="traduzir", motor=motor, dados=["título"],
        prompt=f"texto\n(Pacote gerado para o motor {motor}; revisão humana)", removidos={},
        nome_arquivo=f"prompt-linkedin-en-{motor}.md", autorizado=True,
    )


def test_registrar_recusa_e_janela_do_limite():
    usos = UsosIA()
    uso = _uso_aprovado(usos)
    registrar_recusa(usos, uso.id)
    assert uso.recusado_por_limite and "limite" in uso.resultado
    agora = datetime.now(timezone.utc)
    assert motor_em_limite(usos, "claude", agora)
    assert motor_em_limite(usos, "claude", agora + timedelta(hours=HORAS_LIMITE + 1)) is None
    assert motor_em_limite(usos, "gemini", agora) is None


def test_nao_registra_recusa_de_pedido_nao_enviado():
    usos = UsosIA()
    pendente = registrar_pedido(usos, tarefa="x", descricao="x", motor="claude", dados=[], prompt="p",
                                removidos={}, nome_arquivo="p-claude.md", autorizado=False)
    with pytest.raises(ValueError, match="não foi enviado"):
        registrar_recusa(usos, pendente.id)


def test_sugere_o_outro_motor_e_avisa_quando_os_dois_estao_no_limite():
    usos = UsosIA()
    assert sugerir_motor(usos, "claude") == ("claude", None)
    registrar_recusa(usos, _uso_aprovado(usos, "claude").id)
    motor, aviso = sugerir_motor(usos, "claude")
    assert motor == "gemini" and "recusou por limite" in aviso
    registrar_recusa(usos, _uso_aprovado(usos, "gemini").id)
    motor, aviso = sugerir_motor(usos, "claude")
    assert motor == "claude" and "motor local" in aviso


def test_prompt_refeito_para_o_outro_motor_exige_novo_pedido():
    usos = UsosIA()
    uso = _uso_aprovado(usos)
    prompt, nome = prompt_para_outro_motor(usos, uso.id, "gemini")
    assert "para o motor gemini" in prompt and nome == "prompt-linkedin-en-gemini.md"
    with pytest.raises(ValueError, match="outro motor"):
        prompt_para_outro_motor(usos, uso.id, "claude")
    Path(uso.arquivo_prompt).unlink()
    with pytest.raises(ValueError, match="não está mais em disco"):
        prompt_para_outro_motor(usos, uso.id, "gemini")

    novo = registrar_pedido(usos, tarefa=uso.tarefa, descricao=uso.descricao, motor="gemini", dados=uso.dados,
                            prompt=prompt, removidos={}, nome_arquivo=nome, autorizado=False, substitui=uso.id)
    assert novo.substitui == uso.id and novo.autorizacao == "pendente"   # nova autorização (RF-IA-02)


def test_ultimo_aprovado_por_tarefa_e_motor():
    usos = UsosIA()
    _uso_aprovado(usos, "claude")
    segundo = _uso_aprovado(usos, "claude")
    assert ultimo_aprovado(usos, "traducao-linkedin", "claude") is segundo
    assert ultimo_aprovado(usos, "traducao-linkedin", "gemini") is None
