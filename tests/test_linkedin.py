"""Testes da importação da exportação de dados do LinkedIn (RF-PM-02)."""

import zipfile

import pytest

from agente_carreira.importadores.linkedin import importar_exportacao_linkedin
from agente_carreira.importadores.mesclar import aplicar_importacao
from agente_carreira.models import Contato, PerfilMestre


@pytest.fixture
def export_zip(tmp_path):
    caminho = tmp_path / "Basic_LinkedInDataExport.zip"
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr(
            "Profile.csv",
            '"First Name","Last Name","Headline","Summary"\n'
            '"Samuel","Vitor","Estudante de SI","Backend .NET e dados"\n',
        )
        zf.writestr(
            "Positions.csv",
            '"Company Name","Title","Description","Location","Started On","Finished On"\n'
            '"Loja Y","Atendente","Atendimento e estoque","Belo Horizonte","Jan 2022","Jun 2023"\n',
        )
        zf.writestr("Skills.csv", '"Name"\n"C#"\n".NET"\n"SQL"\n')
        zf.writestr(
            "Languages.csv",
            '"Name","Proficiency"\n"Português","Native or bilingual proficiency"\n"Inglês","Professional working proficiency"\n',
        )
        zf.writestr(
            "Education.csv",
            '"School Name","Start Date","End Date","Notes","Degree Name","Activities"\n'
            '"PUC Minas","2023","","","Sistemas de Informação",""\n',
        )
    return caminho


def test_importa_perfil_e_posicoes(export_zip):
    r = importar_exportacao_linkedin(export_zip)
    assert r.nome == "Samuel Vitor"
    assert r.resumo == "Backend .NET e dados"
    assert len(r.experiencias) == 1
    exp = r.experiencias[0]
    assert exp.cargo == "Atendente"
    assert exp.empresa == "Loja Y"
    assert exp.periodo_texto == "Jan 2022 – Jun 2023"


def test_importa_competencias_idiomas_e_formacao(export_zip):
    r = importar_exportacao_linkedin(export_zip)
    assert r.competencias == ["C#", ".NET", "SQL"]
    assert [i.idioma for i in r.idiomas] == ["Português", "Inglês"]
    assert r.formacoes[0].instituicao == "PUC Minas"


def test_mescla_preenche_sem_sobrescrever(export_zip):
    r = importar_exportacao_linkedin(export_zip)
    perfil = PerfilMestre(
        contato=Contato(nome="Samuel", email="ja-tinha@example.com"),
        resumo="Resumo que eu já tinha escrito",
        competencias_tecnicas=["C#"],
    )
    alteracoes = aplicar_importacao(perfil, r)

    # Não sobrescreve o que já existia (RN-02).
    assert perfil.resumo == "Resumo que eu já tinha escrito"
    assert perfil.contato.email == "ja-tinha@example.com"
    # Acrescenta sem duplicar.
    assert perfil.competencias_tecnicas == ["C#", ".NET", "SQL"]
    # Experiências entram como rascunho pendente, não como registro definitivo.
    assert len(perfil.experiencias) == 0
    assert len(perfil.rascunhos.experiencias) == 1
    assert alteracoes
