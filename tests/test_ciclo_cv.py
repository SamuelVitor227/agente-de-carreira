"""Testes de revisão, desempenho, sob medida, confirmação e candidaturas (RF-CV-09 a RF-CV-14)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from agente_carreira.analise.desempenho import medir, recomendar_por_foco
from agente_carreira.analise.revisao import (
    comparar,
    instantaneo,
    registrar_revisao,
    revisao_pendente,
)
from agente_carreira.analise.sob_medida import gerar_sob_medida
from agente_carreira.candidaturas import (
    Candidatura,
    Candidaturas,
    StatusCandidatura,
    guardar_cv_enviado,
)
from agente_carreira.confirmacao import (
    MARCADOR,
    confirmar_frase,
    frases_pendentes,
    pendencias_na_variante,
)
from agente_carreira.analise.variantes import gerar_variante
from agente_carreira.models import (
    Contato,
    Experiencia,
    Periodo,
    PerfilMestre,
    Projeto,
    Vinculo,
)
from agente_carreira.vagas import Vaga


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _perfil() -> PerfilMestre:
    return PerfilMestre(
        contato=Contato(nome="Samuel", email="s@example.com"),
        resumo="Backend em C# e .NET.",
        competencias_tecnicas=["C#", ".NET", "Docker"],
        experiencias=[
            Experiencia(
                cargo="Estagiário", empresa="Z", vinculo=Vinculo.ESTAGIO,
                periodo=Periodo(inicio=date(2024, 1, 1)),
                responsabilidades=["APIs REST em C#"], tecnologias=["C#"],
            )
        ],
        projetos=[
            Projeto(nome="API de tarefas", tecnologias=["C#", ".NET"]),
            Projeto(nome="Infra na nuvem", tecnologias=["AWS", "Docker"]),
        ],
    )


def _vaga(descricao: str = "C#, .NET e SQL Server") -> Vaga:
    return Vaga(titulo="Dev .NET", foco="backend-dotnet", descricao=descricao)


# ---------------------------------------------------------------- RF-CV-09

def test_revisao_pendente_sem_registro():
    assert revisao_pendente([_vaga()]) is not None


def test_revisao_fica_em_dia_e_detecta_mudanca_no_conjunto():
    vagas = [_vaga()]
    registro = instantaneo(_perfil(), vagas, nota_total=50, cobertos=2, total_termos=4)
    registrar_revisao(registro)
    assert revisao_pendente(vagas) is None
    assert "mudou" in revisao_pendente([_vaga(), _vaga("Python")])


def test_revisao_pendente_apos_30_dias():
    vagas = [_vaga()]
    registro = instantaneo(_perfil(), vagas, nota_total=50, cobertos=2, total_termos=4)
    registrar_revisao(registro)
    futuro = datetime.now(timezone.utc) + timedelta(days=31)
    assert "dias" in revisao_pendente(vagas, agora=futuro)


def test_antes_x_depois_entre_revisoes():
    vagas = [_vaga()]
    a = instantaneo(_perfil(), vagas, nota_total=50, cobertos=2, total_termos=4)
    perfil = _perfil()
    perfil.competencias_tecnicas.append("SQL Server")
    b = instantaneo(perfil, vagas, nota_total=60, cobertos=3, total_termos=4)
    mudancas = comparar(a, b)
    assert any("nota ATS: 50.0 → 60.0" in m for m in mudancas)
    assert any("termos cobertos" in m for m in mudancas)


# ---------------------------------------------------------------- RF-CV-10

def _cand(variante: str, foco: str, status: StatusCandidatura) -> Candidatura:
    c = Candidatura(vaga_titulo="X", foco=foco, variante=variante)
    if status != StatusCandidatura.PREPARADA:
        c.mudar_status(status)
    return c


def test_desempenho_candidaturas_x_retornos():
    colecao = Candidaturas(itens=[
        _cand("cv-a", "backend-dotnet", StatusCandidatura.ENTREVISTA),
        _cand("cv-a", "backend-dotnet", StatusCandidatura.SEM_RESPOSTA),
        _cand("cv-b", "backend-dotnet", StatusCandidatura.SEM_RESPOSTA),
    ])
    desempenhos = medir(colecao)
    a = next(d for d in desempenhos if d.variante == "cv-a")
    assert a.candidaturas == 2 and a.retornos == 1 and a.taxa == 0.5
    melhor = recomendar_por_foco(desempenhos)
    assert melhor["backend-dotnet"].variante == "cv-a"


def test_retorno_conta_mesmo_apos_recusa():
    c = _cand("cv-a", "dados", StatusCandidatura.ENTREVISTA)
    c.mudar_status(StatusCandidatura.RECUSADA)
    assert medir(Candidaturas(itens=[c]))[0].retornos == 1


# ---------------------------------------------------------------- RF-CV-11 / RF-CV-12

def test_sob_medida_reordena_pelos_requisitos_da_vaga():
    perfil = _perfil()
    vaga = Vaga(titulo="Cloud", foco="cloud-aws", descricao="AWS e Docker em produção")
    resultado = gerar_sob_medida(perfil, vaga, foco="backend-dotnet")
    projetos = next(s for s in resultado.variante.secoes if s.titulo == "Projetos")
    assert projetos.itens[0].titulo == "Infra na nuvem"  # subiu pela vaga
    assert any("Projetos" in m for m in resultado.mudancas)  # antes × depois registrado


def test_sob_medida_cobertura_em_tres_listas():
    resultado = gerar_sob_medida(_perfil(), _vaga("C#, .NET e SQL Server"), foco="backend-dotnet")
    assert "C#" in resultado.cobertura.atendidos
    assert "C#" in resultado.cobertura.incluidos
    assert "SQL Server" in resultado.cobertura.sem_lastro


def test_sob_medida_nao_acrescenta_conteudo():
    resultado = gerar_sob_medida(_perfil(), _vaga(), foco="backend-dotnet")
    titulos = {i.titulo for s in resultado.variante.secoes for i in s.itens}
    assert titulos <= {"Estagiário", "API de tarefas", "Infra na nuvem", "Inglês"}  # nada novo (RN-02)


# ---------------------------------------------------------------- RF-CV-13

def test_frases_marcadas_sao_encontradas_e_confirmadas():
    perfil = _perfil()
    perfil.resumo = f"Backend em C# e .NET. Atuei com mensageria {MARCADOR}"
    pendentes = frases_pendentes(perfil)
    assert len(pendentes) == 1 and pendentes[0].local == "resumo"
    confirmar_frase(perfil, pendentes[0])
    assert MARCADOR not in perfil.resumo
    assert frases_pendentes(perfil) == []


def test_variante_com_marcador_bloqueia_exportacao():
    perfil = _perfil()
    perfil.experiencias[0].responsabilidades.append(f"Liderei o time {MARCADOR}")
    variante = gerar_variante(perfil, foco="backend-dotnet")
    pendencias = pendencias_na_variante(variante)
    assert pendencias and "Liderei o time" in pendencias[0]


def test_variante_limpa_nao_tem_pendencias():
    assert pendencias_na_variante(gerar_variante(_perfil(), foco="backend-dotnet")) == []


# ---------------------------------------------------------------- RF-CV-14

def test_guardar_cv_enviado_copia_para_a_candidatura(tmp_path):
    origem = tmp_path / "saidas"
    origem.mkdir()
    cv = origem / "cv-backend-dotnet-pt.pdf"
    cv.write_bytes(b"%PDF-1.4 conteudo")
    cand = Candidatura(vaga_titulo="Dev .NET", foco="backend-dotnet", variante="cv-backend-dotnet-pt")
    guardados = guardar_cv_enviado(cand, [cv])
    assert len(guardados) == 1
    assert guardados[0].read_bytes() == b"%PDF-1.4 conteudo"
    assert cand.cv_enviado == [str(guardados[0])]
    assert cand.id in str(guardados[0])  # guardado na pasta da candidatura
