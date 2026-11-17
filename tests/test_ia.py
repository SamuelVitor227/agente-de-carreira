"""Testes do uso de IA (RF-IA-01 a RF-IA-05)."""

from datetime import date
from pathlib import Path

import pytest

from agente_carreira.analise.reescrita import montar_prompt as prompt_reescrita
from agente_carreira.ia import (
    Configuracao,
    UsosIA,
    autorizar_pendente,
    carregar_configuracao,
    carregar_usos,
    definir_motor,
    descartar_pendente,
    registrar_pedido,
    registrar_resultado,
    resolver_motor,
    salvar_configuracao,
    salvar_usos,
    sanitizar,
    trocar_motor_no_prompt,
    valores_sensiveis,
)
from agente_carreira.linkedin.ingles import montar_prompt as prompt_ingles
from agente_carreira.linkedin.publicacoes import ItemPauta, prompt_polimento
from agente_carreira.models import Contato, Experiencia, Periodo, PerfilMestre, Vinculo


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _perfil() -> PerfilMestre:
    return PerfilMestre(
        contato=Contato(nome="Samuel", email="samuel@example.com", telefone="(31) 99876-5432"),
        resumo="Backend .NET",
        experiencias=[Experiencia(cargo="Dev", empresa="Z", vinculo=Vinculo.CLT,
                                  periodo=Periodo(inicio=date(2024, 1, 1)), responsabilidades=["APIs"])],
    )


def _pedido(usos: UsosIA, autorizado: bool, motor: str = "claude", prompt: str = "texto\n(para o motor claude; fim)"):
    return registrar_pedido(
        usos, tarefa="reescrita-cv", descricao="reescrever", motor=motor, dados=["resumo"],
        prompt=prompt, removidos={}, nome_arquivo=f"prompt-reescrita-geral-{motor}.md", autorizado=autorizado,
    )


# ---------------------------------------------------------------- RF-IA-01

def test_motor_padrao_e_perguntar_que_propoe_claude():
    config = Configuracao()
    assert config.motor_da_tarefa("reescrita-cv") == "perguntar"
    assert resolver_motor("reescrita-cv", None, config) == "claude"


def test_motor_configurado_por_tarefa_e_persistido():
    config = carregar_configuracao()
    definir_motor(config, "traducao-linkedin", "gemini")
    definir_motor(config, "polimento-post", "local")
    salvar_configuracao(config)
    recarregada = carregar_configuracao()
    assert resolver_motor("traducao-linkedin", None, recarregada) == "gemini"
    assert resolver_motor("polimento-post", None, recarregada) == "local"
    assert resolver_motor("reescrita-cv", None, recarregada) == "claude"   # não configurada


def test_linha_de_comando_tem_prioridade_e_e_validada():
    config = Configuracao(motores={"reescrita-cv": "gemini"})
    assert resolver_motor("reescrita-cv", "claude", config) == "claude"
    with pytest.raises(ValueError):
        resolver_motor("reescrita-cv", "gpt", config)


def test_definir_motor_valida_tarefa_e_motor():
    config = Configuracao()
    with pytest.raises(ValueError, match="Tarefa"):
        definir_motor(config, "inexistente", "claude")
    with pytest.raises(ValueError, match="Motor"):
        definir_motor(config, "reescrita-cv", "gpt")


# ---------------------------------------------------------------- RF-IA-04

def test_remove_contato_documentos_e_endereco():
    texto = (
        "Contato: samuel@example.com, (31) 99876-5432, +55 31 98888-7777.\n"
        "CPF 123.456.789-09, RG: MG-12.345.678, CEP 30140-071.\n"
        "Moro na Rua das Flores, 123.\n"
    )
    limpo, removidos = sanitizar(texto)
    for sensivel in ["samuel@example.com", "99876-5432", "98888-7777", "123.456.789-09",
                     "MG-12.345.678", "30140-071", "Rua das Flores"]:
        assert sensivel not in limpo, sensivel
    assert removidos["e-mail"] == 1
    assert removidos["telefone"] == 2
    assert {"CPF", "RG", "CEP", "endereço"} <= set(removidos)


def test_nao_estraga_datas_numeros_e_links():
    texto = (
        "Período 01/2024 – 06/2025. Reduzi 40% do tempo; 1.200 itens; anos 2023 2024.\n"
        "Código: https://github.com/exemplo/projeto-1234567890 e linkedin.com/in/samuel-vitor-123456789\n"
    )
    limpo, removidos = sanitizar(texto)
    assert limpo == texto
    assert removidos == {}


def test_valores_exatos_do_perfil_sao_removidos():
    perfil = _perfil()
    valores = valores_sensiveis(perfil)
    assert "samuel@example.com" in valores and "31998765432" in valores
    limpo, removidos = sanitizar("ligue 31998765432 ou escreva samuel@example.com", valores)
    assert "31998765432" not in limpo and "samuel@example.com" not in limpo
    assert removidos["dado de contato"] == 2


# ---------------------------------------------------------------- RF-IA-02 / RF-IA-03 / RF-IA-05

def test_pedido_autorizado_gera_prompt_e_registra(dados_em_tmp):
    usos = UsosIA()
    uso = _pedido(usos, autorizado=True)
    assert uso.autorizacao == "aprovado" and uso.autorizado_em is not None
    assert Path(uso.arquivo_prompt).read_text(encoding="utf-8").startswith("texto")
    assert uso.prompt_pendente is None
    assert (uso.tarefa, uso.motor, uso.dados) == ("reescrita-cv", "claude", ["resumo"])


def test_pedido_negado_nao_gera_nada_e_fica_na_fila(dados_em_tmp):
    usos = UsosIA()
    uso = _pedido(usos, autorizado=False)
    assert uso.autorizacao == "pendente"
    assert uso.arquivo_prompt is None
    assert not (dados_em_tmp / "saidas").exists()        # nada foi escrito
    assert usos.pendentes() == [uso]


def test_autorizar_da_fila_trocando_de_motor(dados_em_tmp):
    usos = UsosIA()
    uso = _pedido(usos, autorizado=False)
    autorizar_pendente(usos, uso.id, motor="gemini")
    assert uso.motor == "gemini"
    assert uso.arquivo_prompt.endswith("prompt-reescrita-geral-gemini.md")
    assert "para o motor gemini" in Path(uso.arquivo_prompt).read_text(encoding="utf-8")
    assert usos.pendentes() == []
    with pytest.raises(ValueError, match="não está pendente"):
        autorizar_pendente(usos, uso.id)


def test_descartar_pendente():
    usos = UsosIA()
    uso = _pedido(usos, autorizado=False)
    descartar_pendente(usos, uso.id)
    assert uso.autorizacao == "descartado" and uso.prompt_pendente is None
    with pytest.raises(ValueError):
        descartar_pendente(usos, uso.id)


def test_registro_persiste_e_recebe_resultado():
    usos = UsosIA()
    _pedido(usos, autorizado=True, motor="gemini")
    salvar_usos(usos)
    recarregado = carregar_usos()
    uso = registrar_resultado(recarregado, "reescrita-cv", "gemini", "resposta registrada")
    assert uso is not None and uso.resultado == "resposta registrada"
    assert registrar_resultado(recarregado, "reescrita-cv", "claude", "x") is None


def test_os_tres_prompts_trazem_o_motor_no_rodape():
    """Contrato usado pela troca de motor na fila: rodapé 'para o motor X'."""
    perfil = _perfil()
    prompts = [
        prompt_reescrita(perfil, [], "claude"),
        prompt_ingles({"en:titulo": "Dev"}, "claude"),
        prompt_polimento(ItemPauta(titulo="API"), "rascunho", None, "claude"),
    ]
    for prompt in prompts:
        trocado, nome = trocar_motor_no_prompt(prompt, "prompt-x-claude.md", "claude", "gemini")
        assert "para o motor gemini" in trocado
        assert "para o motor claude" not in trocado
        assert nome == "prompt-x-gemini.md"
