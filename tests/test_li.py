"""Testes do módulo LinkedIn (RF-LI-01 a RF-LI-09)."""

from datetime import date

import pytest

from agente_carreira.analise.termos import TermoFrequente
from agente_carreira.linkedin.auditoria import ANEXO_A, auditar, marcar
from agente_carreira.linkedin.configuracoes import (
    gerar_alertas,
    montar_open_to_work,
    pacote_ajustes,
    passos_open_to_work,
    passos_rodada,
    sugerir_url,
    validar_url_personalizada,
)
from agente_carreira.linkedin.limites import LIMITES
from agente_carreira.linkedin.textos import (
    gerar_experiencias,
    gerar_sobre,
    gerar_titulos,
    sugerir_competencias,
)
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


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _perfil() -> PerfilMestre:
    return PerfilMestre(
        contato=Contato(nome="Samuel Vitor", email="s@example.com", telefone="31999990000",
                        cidade="Belo Horizonte", uf="MG"),
        links=Links(github="https://github.com/exemplo", portfolio="https://exemplo.dev"),
        objetivo="Desenvolvedor Backend Júnior",
        resumo="Estudante de Sistemas de Informação com foco em backend .NET.",
        formacao=[Formacao(curso="Sistemas de Informação", instituicao="PUC Minas",
                           status="cursando", conclusao_prevista="2026/2")],
        certificacoes=[Certificacao(nome="AWS Cloud Practitioner", emissor="AWS",
                                    id_credencial="ABC123", url_credencial="https://aws.example/abc")],
        projetos=[Projeto(nome="API de tarefas", tecnologias=["C#", ".NET"],
                          descricao="API REST com testes", url="https://github.com/exemplo/api")],
        experiencias=[
            Experiencia(cargo="Estagiário de desenvolvimento", empresa="Empresa Z",
                        vinculo=Vinculo.ESTAGIO, periodo=Periodo(inicio=date(2024, 1, 1)),
                        responsabilidades=["Manutenção de APIs REST"], tecnologias=["C#", ".NET"]),
        ],
        competencias_tecnicas=["C#", ".NET", "SQL Server", "Docker"],
        idiomas=[Idioma(idioma="Inglês", nivel="intermediário")],
    )


# ---------------------------------------------------------------- RF-LI-01

def test_auditoria_cobre_o_anexo_a_e_ordena_por_impacto():
    itens = auditar(_perfil())
    assert len(itens) == len(ANEXO_A) == 19
    pendentes = [i for i in itens if i.status == "pendente"]
    impactos = [i.impacto for i in pendentes]
    assert impactos.index("alto") < impactos.index("baixo") if "baixo" in impactos else True
    assert impactos == sorted(impactos, key={"alto": 0, "medio": 1, "baixo": 2}.get)


def test_auditoria_verifica_o_que_da_pelo_perfil():
    itens = {i.numero: i for i in auditar(_perfil())}
    assert "Belo Horizonte" in itens[4].verificacao
    assert itens[10].verificacao == "todas as certificações têm ID/link"
    assert "e-mail, GitHub e portfólio registrados" == itens[15].verificacao


def test_marcar_item_persiste_e_reordena():
    marcar(3, "feito")
    itens = auditar(_perfil())
    item3 = next(i for i in itens if i.numero == 3)
    assert item3.status == "feito"
    assert itens.index(item3) > len([i for i in itens if i.status == "pendente"]) - 1
    with pytest.raises(ValueError):
        marcar(99, "feito")


# ---------------------------------------------------------------- RF-LI-02

def test_titulos_3_opcoes_dentro_dos_limites():
    opcoes = gerar_titulos(_perfil(), foco="backend-dotnet", cargo_alvo="Desenvolvedor Backend Júnior")
    assert 1 <= len(opcoes) <= 3
    for o in opcoes:
        assert o.dentro_do_limite and o.caracteres <= LIMITES["titulo"]
        assert o.essencial_nos_primeiros_60
    assert any("PUC Minas" in o.texto for o in opcoes)  # diferencial vem do registrado


# ---------------------------------------------------------------- RF-LI-03

def test_sobre_dentro_do_limite_com_abertura():
    sobre = gerar_sobre(_perfil(), foco="backend-dotnet")
    assert sobre.dentro_do_limite and sobre.caracteres <= LIMITES["sobre"]
    assert sobre.abertura.startswith("Estudante de Sistemas")  # proposta de valor na abertura
    assert "API de tarefas" in sobre.texto
    assert "PUC Minas" in sobre.texto
    assert "github.com/exemplo" in sobre.texto


# ---------------------------------------------------------------- RF-LI-04

def test_experiencias_mesmos_cargos_e_datas_do_cv():
    blocos = gerar_experiencias(_perfil())
    assert blocos[0].cargo == "Estagiário de desenvolvimento"
    assert blocos[0].periodo == "01/2024 – atual"  # mesmo formato único do CV
    assert blocos[0].dentro_do_limite
    assert "Tecnologias: C#, .NET" in blocos[0].texto


# ---------------------------------------------------------------- RF-LI-05

def test_competencias_priorizadas_pelas_vagas_com_vinculo():
    termos = [
        TermoFrequente(termo="SQL Server", vagas_em_que_aparece=3, total_de_vagas=3, e_tecnologia=True),
        TermoFrequente(termo="C#", vagas_em_que_aparece=2, total_de_vagas=3, e_tecnologia=True),
    ]
    sugeridas = sugerir_competencias(_perfil(), termos)
    assert sugeridas[0].nome == "SQL Server"      # mais pedida primeiro
    csharp = next(s for s in sugeridas if s.nome == "C#")
    assert any("Empresa Z" in v for v in csharp.vinculos)  # vínculo com a experiência


# ---------------------------------------------------------------- RF-LI-06

def test_open_to_work_valida_limite_de_cargos():
    perfil = _perfil()
    pacote = montar_open_to_work(perfil, ["Desenvolvedor .NET"], "decidir_ao_aplicar")
    assert "Belo Horizonte, MG" in pacote.localidades
    assert any("remoto" in l for l in pacote.localidades)
    passos = passos_open_to_work(pacote)
    assert any("moldura verde" in p for p in passos)
    with pytest.raises(Exception):
        montar_open_to_work(perfil, [f"Cargo {i}" for i in range(6)], "so_recrutadores")


# ---------------------------------------------------------------- RF-LI-07

def test_url_personalizada_validacao_e_sugestao():
    assert validar_url_personalizada("samuelvitor") == []
    assert validar_url_personalizada("ab") != []            # curta demais
    assert validar_url_personalizada("tem espaço") != []
    assert validar_url_personalizada("símbolo!") != []
    assert sugerir_url("Samuel Vítor") == "samuelvitor"


def test_pacote_de_ajustes_reune_campos_do_perfil():
    ajustes = dict(pacote_ajustes(_perfil()))
    assert ajustes["Localização"] == "Belo Horizonte, MG"
    assert "linkedin.com/in/samuelvitor" in ajustes["URL personalizada"]
    assert "ABC123" in ajustes["Certificações (com ID e link)"]
    assert "Inglês: intermediário" in ajustes["Idiomas"]


# ---------------------------------------------------------------- RF-LI-08

def test_rodada_comeca_desligando_e_termina_religando():
    passos = passos_rodada(["3. Título"])
    assert "desligue" in passos[0].lower()
    assert "religue" in passos[-1].lower()
    assert any("3. Título" in p for p in passos)


# ---------------------------------------------------------------- RF-LI-09

def test_alertas_ate_20_diarios_por_email():
    pacote = gerar_alertas(_perfil(), ["backend-dotnet", "cloud-aws", "mobile", "dados", "suporte"])
    assert 0 < len(pacote.alertas) <= LIMITES["alertas"]
    assert all(a.frequencia == "diária" and a.canal == "e-mail" for a in pacote.alertas)
    assert any("Belo Horizonte" in a.local for a in pacote.alertas)
