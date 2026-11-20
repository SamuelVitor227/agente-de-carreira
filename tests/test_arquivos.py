"""Gravação segura dos dados: atômica, com trava e mescla entre tarefas; cópias de segurança diárias."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest

from agente_carreira import copias
from agente_carreira.arquivos import ArquivoDanificado, gravar_texto, ler_modelo, mesclar
from agente_carreira.candidaturas import carregar_candidaturas
from agente_carreira.radar.modelos import (BaseVagas, BuscaSalva, VagaEncontrada, carregar_base, carregar_config,
                                           salvar_base, salvar_config)


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _vaga(id_: str, **kwargs) -> VagaEncontrada:
    return VagaEncontrada(id=id_, titulo=kwargs.pop("titulo", f"Vaga {id_}"), empresa="Omega", **kwargs)


def _base_com(*vagas: VagaEncontrada) -> None:
    salvar_base(BaseVagas(itens=list(vagas)))


# ---------------------------------------------------------------- mescla em três vias

def test_mescla_mantem_o_que_cada_lado_mudou():
    base = {"a": 1, "b": 1, "lista": ["x"]}
    meu = {"a": 2, "b": 1, "lista": ["x", "y"]}
    disco = {"a": 1, "b": 3, "lista": ["x", "z"]}
    assert mesclar(base, meu, disco) == {"a": 2, "b": 3, "lista": ["x", "y", "z"]}


def test_mescla_de_listas_com_id_item_a_item():
    base = {"itens": [{"id": "1", "s": "nova"}, {"id": "2", "s": "nova"}]}
    meu = {"itens": [{"id": "1", "s": "nova"}, {"id": "2", "s": "nova", "nota": 80}, {"id": "3", "s": "nova"}]}
    disco = {"itens": [{"id": "1", "s": "descartada"}, {"id": "2", "s": "nova"}]}
    assert mesclar(base, meu, disco)["itens"] == [
        {"id": "1", "s": "descartada"}, {"id": "2", "s": "nova", "nota": 80}, {"id": "3", "s": "nova"}]


def test_conflito_no_mesmo_valor_segue_a_preferencia():
    base, meu, disco = {"s": "nova"}, {"s": "no_resumo"}, {"s": "descartada"}
    assert mesclar(base, meu, disco, "meu") == {"s": "no_resumo"}
    assert mesclar(base, meu, disco, "disco") == {"s": "descartada"}


def test_item_removido_de_um_lado_some():
    base = {"itens": [{"id": "1"}, {"id": "2"}]}
    assert mesclar(base, {"itens": [{"id": "1"}]}, base) == {"itens": [{"id": "1"}]}
    assert mesclar(base, base, {"itens": [{"id": "2"}]}) == {"itens": [{"id": "2"}]}


# ---------------------------------------------------------------- tarefas ao mesmo tempo

def test_busca_longa_nao_desfaz_o_que_a_pessoa_fez_no_meio(dados):
    _base_com(_vaga("1"), _vaga("2"))
    busca = carregar_base()                      # a busca lê tudo no começo...
    clique = carregar_base()                     # ...e no meio dela você clica "Não tenho interesse"
    clique.buscar("1").status = "descartada"
    salvar_base(clique)
    busca.buscar("1").status = "no_resumo"       # a busca reavalia as mesmas vagas
    busca.buscar("2").status = "no_resumo"
    busca.itens.append(_vaga("3"))
    salvar_base(busca, preferir="disco")         # e grava no fim
    final = carregar_base()
    assert [(v.id, v.status) for v in final.itens] == [("1", "descartada"), ("2", "no_resumo"), ("3", "nova")]


def test_duas_gravacoes_seguidas_do_mesmo_processo_nao_revertem_a_outra_tarefa(dados):
    _base_com(_vaga("1"), _vaga("2"))
    a, b = carregar_base(), carregar_base()
    b.buscar("1").status = "salva"
    salvar_base(b)
    a.buscar("2").status = "descartada"
    salvar_base(a)
    a.buscar("2").status = "salva"
    salvar_base(a)
    assert [(v.id, v.status) for v in carregar_base().itens] == [("1", "salva"), ("2", "salva")]


def test_configuracao_de_busca_mudada_durante_a_busca_fica(dados):
    rodada = carregar_config()
    pessoa = carregar_config()
    pessoa.buscas.append(BuscaSalva(nome="nova-area", cargos=["analista de dados"]))
    salvar_config(pessoa)
    salvar_config(rodada, preferir="disco")      # a busca grava a configuração que leu no começo
    assert [b.nome for b in carregar_config().buscas] == ["nova-area"]


def test_tarefas_em_processos_diferentes_nao_perdem_candidaturas(dados):
    import subprocess
    import sys

    codigo = (
        "import sys\n"
        "from agente_carreira.candidaturas import Candidatura, carregar_candidaturas, salvar_candidaturas\n"
        "for i in range(15):\n"
        "    c = carregar_candidaturas()\n"
        "    c.itens.append(Candidatura(vaga_id=f'{sys.argv[1]}{i}', vaga_titulo='Dev', empresa='X', foco='backend',\n"
        "                               variante='cv-x'))\n"
        "    salvar_candidaturas(c)\n"
    )
    ambiente = dict(os.environ, AGENTE_CARREIRA_DATA=str(dados))
    processos = [subprocess.Popen([sys.executable, "-c", codigo, letra], env=ambiente) for letra in "ab"]
    assert all(p.wait(timeout=120) == 0 for p in processos)
    assert len(carregar_candidaturas().itens) == 30


# ---------------------------------------------------------------- gravação atômica e arquivo danificado

def test_gravacao_que_falha_no_meio_mantem_o_arquivo_antigo(dados, monkeypatch):
    destino = dados / "x.json"
    destino.write_text('{"ok": 1}', encoding="utf-8")

    def falhar(*_a, **_k):
        raise PermissionError("em uso")

    monkeypatch.setattr(os, "replace", falhar)
    with pytest.raises(PermissionError):
        gravar_texto(destino, '{"ok": 2}', tentativas=2)
    assert destino.read_text(encoding="utf-8") == '{"ok": 1}'
    assert [p.name for p in dados.iterdir()] == ["x.json"]  # nada de temporário largado


def test_arquivo_danificado_volta_para_a_copia_de_seguranca(dados, capsys):
    _base_com(_vaga("1"))
    copias.garantir_copia_do_dia()
    (dados / "vagas-encontradas.json").write_text('{"itens": [{"id": "1", "titu', encoding="utf-8")  # cortado no meio
    base = carregar_base()
    assert [v.id for v in base.itens] == ["1"]
    assert "danificado" in capsys.readouterr().err
    assert list(dados.glob("vagas-encontradas.danificado-*.json"))


def test_arquivo_danificado_sem_copia_explica_o_que_fazer(dados):
    (dados / "vagas-encontradas.json").write_text("{", encoding="utf-8")
    with pytest.raises(ArquivoDanificado, match="Cópias de segurança"):
        ler_modelo(dados / "vagas-encontradas.json", BaseVagas)


# ---------------------------------------------------------------- cópias de segurança

def test_copia_do_dia_guarda_os_dados_e_nao_o_estado_do_momento(dados):
    _base_com(_vaga("1"))
    (dados / "andamento.json").write_text("{}", encoding="utf-8")
    (dados / "navegador.sessoes").write_text("{}", encoding="utf-8")
    pasta = copias.garantir_copia_do_dia(date(2026, 11, 18))
    assert pasta is not None and sorted(p.name for p in pasta.iterdir()) == ["vagas-encontradas.json"]
    assert copias.garantir_copia_do_dia(date(2026, 11, 18)) is None  # uma por dia


def test_guarda_so_os_ultimos_sete_dias(dados):
    _base_com(_vaga("1"))
    inicio = date(2026, 11, 1)
    for i in range(10):
        copias.garantir_copia_do_dia(inicio + timedelta(days=i))
    dias = [c.nome for c in copias.listar_copias()]
    assert dias == [(inicio + timedelta(days=i)).isoformat() for i in range(9, 2, -1)]


def test_restaurar_guarda_antes_o_estado_atual(dados):
    _base_com(_vaga("1"))
    copias.garantir_copia_do_dia(date(2026, 11, 17))
    _base_com(_vaga("1"), _vaga("2"))
    restaurados = copias.restaurar("2026-11-17")
    assert restaurados == ["vagas-encontradas.json"]
    assert [v.id for v in carregar_base().itens] == ["1"]
    reserva = [c for c in copias.listar_copias() if c.nome.startswith("antes-de-restaurar-")]
    assert len(reserva) == 1
    dados_reserva = json.loads((reserva[0].pasta / "vagas-encontradas.json").read_text(encoding="utf-8"))
    assert [v["id"] for v in dados_reserva["itens"]] == ["1", "2"]
    with pytest.raises(ValueError):
        copias.restaurar("2020-01-01")


# ---------------------------------------------------------------- versão antiga do código aberta

def test_processo_com_codigo_antigo_nao_apaga_opcao_nova(dados):
    """O app aberto antes de uma atualização não conhece uma opção nova; ao gravar, ela tem que continuar lá."""
    from pydantic import BaseModel, Field

    from agente_carreira.arquivos import gravar_modelo

    class Item(BaseModel):
        id: str
        nome: str

    class ConfigAntiga(BaseModel):
        nome: str = "x"
        itens: list[Item] = Field(default_factory=list)

    caminho = dados / "config-teste.json"
    caminho.write_text(json.dumps({"nome": "a", "email_navegador": {"ativo": True},
                                   "itens": [{"id": "1", "nome": "um", "conferida_em": "2026-11-19"}]}), encoding="utf-8")
    antiga = ler_modelo(caminho, ConfigAntiga)
    antiga.nome = "b"
    gravar_modelo(caminho, antiga)
    salvo = json.loads(caminho.read_text(encoding="utf-8"))
    assert salvo["nome"] == "b" and salvo["email_navegador"] == {"ativo": True}
    assert salvo["itens"][0]["conferida_em"] == "2026-11-19"  # campo novo dentro de item da lista também fica


def test_resposta_apagada_continua_apagada(dados):
    from agente_carreira.respostas import carregar_respostas, definir_resposta, salvar_respostas

    banco = carregar_respostas()
    definir_resposta(banco, "cnh", "B")
    definir_resposta(banco, "viagens", "eventualmente")
    salvar_respostas(banco)
    banco = carregar_respostas()
    banco.itens.pop("cnh")
    salvar_respostas(banco)
    assert set(carregar_respostas().itens) == {"viagens"}
