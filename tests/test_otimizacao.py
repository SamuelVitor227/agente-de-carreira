"""Testes de ordenação, nota ATS e fechamento de lacunas (RF-CV-04 a RF-CV-06)."""

from datetime import date, datetime, timezone

import pytest

from agente_carreira.analise.ats import calcular_nota, comparar, registrar_nota
from agente_carreira.analise.fechamento import sugerir_fechamento
from agente_carreira.analise.lacunas import ItemLacuna
from agente_carreira.analise.ordenacao import ordenar_cv
from agente_carreira.analise.termos import extrair_termos
from agente_carreira.models import (
    Area,
    Conquista,
    Contato,
    Experiencia,
    Formacao,
    Idioma,
    Periodo,
    PerfilMestre,
    Projeto,
    Vinculo,
)
from agente_carreira.vagas import Vaga


def _perfil_completo() -> PerfilMestre:
    return PerfilMestre(
        contato=Contato(nome="Samuel", email="s@example.com", telefone="31999990000", cidade="BH"),
        objetivo="Estágio backend .NET",
        resumo="Estudante de SI com foco em backend C#/.NET.",
        formacao=[Formacao(curso="Sistemas de Informação", instituicao="PUC Minas", status="cursando", conclusao_prevista="2026/2")],
        projetos=[Projeto(nome="API de tarefas", tipo="pessoal", tecnologias=["C#", ".NET"]), Projeto(nome="Estudo sem stack", tipo="academico")],
        experiencias=[
            Experiencia(
                cargo="Atendente", empresa="Loja", vinculo=Vinculo.CLT,
                periodo=Periodo(inicio=date(2022, 1, 1), fim=date(2023, 6, 1)),
                area=Area.FORA_DE_TI, responsabilidades=["Atendimento ao cliente"],
            ),
            Experiencia(
                cargo="Estagiário de TI", empresa="Empresa Z", vinculo=Vinculo.ESTAGIO,
                periodo=Periodo(inicio=date(2024, 1, 1)),
                area=Area.TI, responsabilidades=["Suporte a sistemas internos"],
                tecnologias=["SQL"],
            ),
        ],
        competencias_tecnicas=["C#", ".NET", "SQL"],
        idiomas=[Idioma(idioma="Inglês", nivel="intermediário")],
        banco_conquistas=[Conquista(verbo_acao="Reduzi", descricao="fila de chamados", numero="20%")],
    )


VAGAS = [
    Vaga(titulo="Estágio .NET", foco="backend-dotnet", descricao="C#, .NET, SQL Server, Docker", salva_em=datetime.now(timezone.utc)),
    Vaga(titulo="Dev júnior", foco="backend-dotnet", descricao="C#, SQL Server e Docker", salva_em=datetime.now(timezone.utc)),
]


# ---------------------------------------------------------------- RF-CV-04

def test_nivel_inicial_formacao_e_projetos_antes_de_fora_da_area():
    estrutura = ordenar_cv(_perfil_completo(), nivel="estagio")
    titulos = [s.titulo for s in estrutura.secoes]
    assert titulos.index("Formação Acadêmica") < titulos.index("Outras Experiências")
    assert titulos.index("Projetos") < titulos.index("Outras Experiências")
    assert titulos.index("Experiência Profissional") < titulos.index("Outras Experiências")


def test_nivel_pleno_experiencia_lidera():
    estrutura = ordenar_cv(_perfil_completo(), nivel="pleno")
    titulos = [s.titulo for s in estrutura.secoes]
    assert titulos.index("Experiência Profissional") < titulos.index("Formação Acadêmica")


def test_projetos_com_tecnologias_vem_primeiro():
    estrutura = ordenar_cv(_perfil_completo(), nivel="estagio")
    projetos = next(s for s in estrutura.secoes if s.titulo == "Projetos")
    assert projetos.itens[0].startswith("API de tarefas")


def test_secoes_vazias_sao_omitidas():
    perfil = PerfilMestre(contato=Contato(nome="S", email="s@example.com"))
    estrutura = ordenar_cv(perfil, nivel="estagio")
    assert estrutura.secoes == []


def test_experiencia_fora_da_area_e_sinalizada():
    estrutura = ordenar_cv(_perfil_completo(), nivel="estagio")
    fora = next(s for s in estrutura.secoes if s.titulo == "Outras Experiências")
    assert "[fora da área]" in fora.itens[0]


# ---------------------------------------------------------------- RF-CV-05

@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def test_nota_ats_componentes_e_total():
    termos = extrair_termos(VAGAS)
    nota = calcular_nota(_perfil_completo(), termos, foco="backend-dotnet")
    assert 0 < nota.total <= 100
    criterios = {i.criterio for i in nota.itens}
    assert any("contato" in c for c in criterios)
    assert any("termos das vagas" in c for c in criterios)
    assert any("títulos de seção" in c for c in criterios)
    soma_maximos = sum(i.maximo for i in nota.itens)
    assert soma_maximos == 100


def test_nota_sem_vagas_explica_termos_zerados():
    nota = calcular_nota(_perfil_completo(), [], foco=None)
    item = next(i for i in nota.itens if "termos das vagas" in i.criterio)
    assert item.pontos == 0
    assert "sem vagas-alvo" in (item.detalhe or "")


def test_historico_mostra_o_que_mudou_entre_revisoes():
    termos = extrair_termos(VAGAS)
    perfil = _perfil_completo()
    nota1 = calcular_nota(perfil, termos, foco="backend-dotnet")
    assert registrar_nota(nota1) is None  # primeira revisão

    perfil.competencias_tecnicas.append("Docker")  # cobre mais um termo
    nota2 = calcular_nota(perfil, termos, foco="backend-dotnet")
    anterior = registrar_nota(nota2)
    assert anterior is not None

    mudancas = comparar(anterior, nota2)
    assert any("nota total" in m for m in mudancas)
    assert any("termos das vagas" in m for m in mudancas)


def test_melhora_de_cobertura_aumenta_a_nota():
    termos = extrair_termos(VAGAS)
    perfil = _perfil_completo()
    antes = calcular_nota(perfil, termos, foco=None).total
    perfil.competencias_tecnicas += ["Docker", "SQL Server"]
    depois = calcular_nota(perfil, termos, foco=None).total
    assert depois > antes


# ---------------------------------------------------------------- RF-CV-06

def _lacuna(termo: str) -> ItemLacuna:
    return ItemLacuna(termo=termo, vagas_em_que_aparece=2, percentual=100)


def test_termo_conhecido_prioriza_catalogo_dio():
    sugestoes = sugerir_fechamento([_lacuna("AWS")])
    assert sugestoes[0].catalogo == "DIO"  # catálogo que o usuário já tem vem primeiro
    tipos = {s.tipo for s in sugestoes}
    assert {"curso", "certificacao", "projeto"} <= tipos


def test_termo_desconhecido_recebe_sugestao_generica():
    sugestoes = sugerir_fechamento([_lacuna("Terraform")])
    assert any(s.tipo == "projeto" and "Terraform" in s.descricao for s in sugestoes)
    assert any(s.tipo == "curso" and "DIO" in s.descricao for s in sugestoes)


def test_sem_lacunas_sem_sugestoes():
    assert sugerir_fechamento([]) == []


def test_sugestoes_seguem_a_ordem_das_lacunas():
    sugestoes = sugerir_fechamento([_lacuna("Docker"), _lacuna("AWS")])
    termos_na_ordem = [s.termo for s in sugestoes]
    assert termos_na_ordem.index("Docker") < termos_na_ordem.index("AWS")
