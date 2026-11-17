"""Testes de vagas-alvo, termos, lacunas e reescrita (RF-CV-01 a RF-CV-03)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from agente_carreira.analise.lacunas import gerar_relatorio
from agente_carreira.analise.reescrita import dados_enviados, montar_prompt
from agente_carreira.analise.termos import extrair_termos
from agente_carreira.models import (
    Area,
    Conquista,
    Contato,
    Experiencia,
    Periodo,
    PerfilMestre,
    Vinculo,
)
from agente_carreira.vagas import Vaga, VagasAlvo, conjunto_de_analise


def _vaga(titulo: str, descricao: str, foco: str = "backend-dotnet", dias_atras: int = 0) -> Vaga:
    return Vaga(
        titulo=titulo,
        foco=foco,
        descricao=descricao,
        salva_em=datetime.now(timezone.utc) - timedelta(days=dias_atras),
    )


VAGAS = [
    _vaga("Estágio .NET", "Requisitos: C#, .NET, SQL Server e Git. Desejável Docker e metodologias ageis."),
    _vaga("Dev júnior C#", "Atuar com C#, .NET, APIs REST e SQL Server. Metodologias ageis (Scrum)."),
    _vaga("Backend júnior", "Vaga para backend com C#, Docker e AWS. Inglês intermediário."),
]


# ---------------------------------------------------------------- RF-CV-01

def test_conjunto_filtra_por_foco_e_limita():
    colecao = VagasAlvo(vagas=[
        _vaga("A", "x", foco="backend-dotnet", dias_atras=2),
        _vaga("B", "x", foco="dados", dias_atras=1),
        _vaga("C", "x", foco="backend-dotnet", dias_atras=0),
    ])
    conjunto = conjunto_de_analise(colecao, foco="backend-dotnet")
    assert [v.titulo for v in conjunto] == ["C", "A"]  # mais recente primeiro
    assert len(conjunto_de_analise(colecao, foco="backend-dotnet", limite=1)) == 1


def test_extrai_termos_tecnologias_com_frequencia():
    termos = {t.termo: t for t in extrair_termos(VAGAS)}
    assert termos["C#"].vagas_em_que_aparece == 3
    assert termos["C#"].percentual == 100
    assert termos[".NET"].vagas_em_que_aparece == 2
    assert termos["Docker"].vagas_em_que_aparece == 2
    assert termos["AWS"].vagas_em_que_aparece == 1


def test_extrai_termos_genericos_frequentes():
    termos = {t.termo for t in extrair_termos(VAGAS)}
    assert "ageis" in termos  # aparece em 2 vagas e não é stopword


def test_sem_vagas_sem_termos():
    assert extrair_termos([]) == []


# ---------------------------------------------------------------- RF-CV-02

def _perfil_para_lacunas() -> PerfilMestre:
    conquista = Conquista(verbo_acao="Organizei", descricao="o estoque usando planilhas")
    return PerfilMestre(
        contato=Contato(nome="Samuel", email="s@example.com"),
        resumo="Estudante de SI com projetos em Docker.",
        competencias_tecnicas=["C#", ".NET"],
        experiencias=[
            Experiencia(
                cargo="Atendente",
                empresa="Loja",
                vinculo=Vinculo.CLT,
                periodo=Periodo(inicio=date(2023, 1, 1)),
                area=Area.FORA_DE_TI,
                responsabilidades=["Atendimento ao cliente"],
                conquista_ids=[conquista.id],
            )
        ],
        banco_conquistas=[conquista],
    )


def test_relatorio_de_lacunas_em_tres_grupos():
    relatorio = gerar_relatorio(_perfil_para_lacunas(), extrair_termos(VAGAS))
    ja = {i.termo for i in relatorio.ja_no_cv}
    escondido = {i.termo for i in relatorio.tem_mas_nao_aparece}
    falta = {i.termo for i in relatorio.nao_tem}

    assert {"C#", ".NET"} <= ja               # declarado nas competências
    assert "Docker" in escondido              # só aparece no resumo (texto livre)
    assert {"SQL Server", "AWS"} <= falta     # em lugar nenhum do perfil
    assert ja.isdisjoint(falta) and escondido.isdisjoint(falta)


def test_lacuna_informa_onde_o_termo_escondido_foi_achado():
    relatorio = gerar_relatorio(_perfil_para_lacunas(), extrair_termos(VAGAS))
    docker = next(i for i in relatorio.tem_mas_nao_aparece if i.termo == "Docker")
    assert docker.onde_encontrado == "resumo"


# ---------------------------------------------------------------- RF-CV-03

def test_prompt_de_reescrita_contem_material_termos_e_regras():
    perfil = _perfil_para_lacunas()
    prompt = montar_prompt(perfil, extrair_termos(VAGAS), motor="claude")
    assert "verbo de ação" in prompt
    assert "NÃO invente" in prompt
    assert "[A CONFIRMAR]" in prompt
    assert "Atendente — Loja" in prompt
    assert "Organizei" in prompt      # conquista vinculada entra no material
    assert "C#" in prompt             # termos das vagas listados


def test_prompt_nao_vaza_dados_de_contato():
    perfil = _perfil_para_lacunas()
    prompt = montar_prompt(perfil, extrair_termos(VAGAS), motor="gemini")
    assert "s@example.com" not in prompt
    assert "Samuel" not in prompt


def test_transparencia_dos_dados_enviados():
    relacao = dados_enviados(_perfil_para_lacunas())
    assert any("experiência" in d for d in relacao)
    assert any("NÃO são enviados" in d for d in relacao)
