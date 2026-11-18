"""Fechamento do MVP: CA-01 a CA-10, RF-IA-08 e o comando de aceite."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pypdf import PdfReader

from agente_carreira.aceite import _ca08, verificar_mvp
from agente_carreira.analise.exportar import exportar_pdf
from agente_carreira.analise.lacunas import gerar_relatorio
from agente_carreira.analise.lastro import verificar_lastro
from agente_carreira.analise.sob_medida import gerar_sob_medida
from agente_carreira.analise.termos import extrair_termos
from agente_carreira.analise.variantes import ItemCV, gerar_variante
from agente_carreira.ia import (
    UsosIA,
    carregar_usos,
    criar_lote,
    lote_que_cobre,
    registrar_pedido,
    revogar_lote,
    salvar_usos,
)
from agente_carreira.importadores.extrator import extrair_de_texto
from agente_carreira.importadores.mesclar import aplicar_importacao
from agente_carreira.linkedin.textos import gerar_titulos
from agente_carreira.models import (
    Certificacao,
    Contato,
    Experiencia,
    Formacao,
    Idioma,
    Periodo,
    PerfilMestre,
    Projeto,
    Vinculo,
)
from agente_carreira.radar.modelos import BaseVagas, RegistroRodada, salvar_base
from agente_carreira.radar.rodada import pedir_justificativa
from agente_carreira.radar.modelos import VagaEncontrada
from agente_carreira.storage import salvar_perfil
from agente_carreira.vagas import Vaga, VagasAlvo, salvar_vagas


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


CV_TEXTO = """Ana Beatriz Souza
Endereço: Contagem, Minas Gerais, Brasil
Contato: (31) 98888-7777 / ana.souza@example.com
LinkedIn: linkedin.com/in/ana-souza / GitHub: github.com/anasouza
Objetivo Profissional
Estágio em Desenvolvimento de Software.
Desenvolvo APIs REST em .NET e C# e aplicativos em React Native.
Formação Acadêmica
Bacharelado em Ciência da Computação - UFMG - 6º período (Previsão de Conclusão: 2/2027)
Habilidades e Competências
• Linguagens: C#, Python, SQL
• Back-end: .NET / ASP.NET Core, APIs REST
• Idiomas: Português (nativo) e Inglês (intermediário)
Projetos de Desenvolvimento
api-tarefas | C#, .NET, SQL Server
• API REST de tarefas com autenticação e testes
automatizados.
painel-energia | Python, Pandas
• Painel de consumo de energia.
Experiência Profissional
Loja Centro | Atendente, 03/2021 – 12/2022
• Atendimento ao público e controle de estoque.
Cursos e Certificações
• AWS Academy - Cloud Foundations (2024)
"""


# ---------------------------------------------------------------- CA-01

def test_ca01_leitura_das_secoes_do_cv():
    r = extrair_de_texto(CV_TEXTO, origem="teste")
    assert r.nome == "Ana Beatriz Souza" and (r.cidade, r.uf) == ("Contagem", "MG")
    assert r.objetivo == "Estágio em Desenvolvimento de Software."
    assert "APIs REST em .NET" in r.resumo
    assert {"C#", "Python", "SQL", ".NET", "ASP.NET Core", "APIs REST"} <= set(r.competencias)
    assert [(i.idioma, i.nivel) for i in r.idiomas] == [("Português", "nativo"), ("Inglês", "intermediário")]
    assert [(p.nome, p.tecnologias) for p in r.projetos] == [
        ("api-tarefas", ["C#", ".NET", "SQL Server"]), ("painel-energia", ["Python", "Pandas"])]
    assert r.projetos[0].descricao == "API REST de tarefas com autenticação e testes automatizados."
    exp = r.experiencias[0]
    assert (exp.empresa, exp.cargo, exp.periodo_texto) == ("Loja Centro", "Atendente", "03/2021 – 12/2022")
    form = r.formacoes[0]
    assert (form.curso, form.instituicao) == ("Bacharelado em Ciência da Computação", "UFMG")
    assert "2/2027" in form.periodo_texto
    cert = r.certificacoes[0]
    assert (cert.nome, cert.emissor, cert.data_texto) == ("Cloud Foundations", "AWS Academy", "2024")


def test_ca01_importacao_gera_o_perfil():
    r = extrair_de_texto(CV_TEXTO, origem="teste")
    perfil = PerfilMestre(contato=Contato(nome=r.nome, email=r.email))
    aplicar_importacao(perfil, r)
    assert perfil.contato.cidade == "Contagem" and perfil.objetivo
    assert [p.nome for p in perfil.projetos] == ["api-tarefas", "painel-energia"]
    assert perfil.rascunhos.experiencias[0].empresa == "Loja Centro"     # experiência fica para confirmar


def test_tecnologia_detectada_nao_duplica_competencia_da_secao():
    r = extrair_de_texto("Habilidades\n• Web: HTML5, CSS3, AWS (fundamentos)\n• Linguagens: JavaScript", origem="t")
    assert "HTML" not in r.competencias and "AWS" not in r.competencias
    assert "JavaScript" in r.competencias and "Java" not in r.competencias


# ---------------------------------------------------------------- CA-02

def _perfil() -> PerfilMestre:
    return PerfilMestre(
        contato=Contato(nome="Ana", email="ana@example.com", cidade="Contagem", uf="MG"),
        objetivo="Estágio em desenvolvimento",
        resumo="Desenvolvo APIs REST em C# e .NET.",
        competencias_tecnicas=["C#", ".NET", "SQL Server", "Python", "Git"],
        experiencias=[
            Experiencia(cargo="Estagiário de desenvolvimento", empresa="Empresa Z", vinculo=Vinculo.ESTAGIO,
                        periodo=Periodo(inicio=date(2024, 2, 1)), responsabilidades=["APIs REST em C#"],
                        tecnologias=["C#", ".NET"]),
            Experiencia(cargo="Atendente", empresa="Loja Centro", vinculo=Vinculo.CLT,
                        periodo=Periodo(inicio=date(2021, 3, 1), fim=date(2022, 12, 1)),
                        responsabilidades=["Atendimento ao público"]),
        ],
        projetos=[Projeto(nome="api-tarefas", tecnologias=["C#", ".NET", "SQL Server"], descricao="API de tarefas")],
        formacao=[Formacao(curso="Ciência da Computação", instituicao="UFMG", status="cursando", conclusao_prevista="2027/2")],
        certificacoes=[Certificacao(nome="Cloud Foundations", emissor="AWS Academy")],
        idiomas=[Idioma(idioma="Inglês", nivel="intermediário")],
    )


DESCRICOES = [
    "Requisitos: C#, .NET, SQL Server, Docker", "Requisitos: Java, Spring, Kubernetes", "Python, Django, AWS",
    "React Native, TypeScript, Git", "Azure, C#, Angular", "Go, Kafka, PostgreSQL", "PHP, Laravel, MySQL",
    "Node.js, MongoDB, Docker", "Scrum, Kanban, Git", ".NET, Entity Framework, REST", "Kotlin, Swift",
    "SQL, Power BI, Python", "Linux, Docker, AWS", "C++, Python", "Java, AWS, Kubernetes", "GraphQL, React",
    "C#, Azure, Docker", "HTML, CSS, JavaScript", "Flutter, Firebase", "ASP.NET, SQL Server, C#",
]


def test_ca02_vinte_cvs_sob_medida_sem_nada_fora_do_perfil():
    perfil = _perfil()
    for i, descricao in enumerate(DESCRICOES):
        vaga = Vaga(titulo=f"Vaga {i}", foco="backend-dotnet", descricao=descricao)
        variante = gerar_sob_medida(perfil, vaga, foco="backend-dotnet").variante
        assert verificar_lastro(variante, perfil) == [], descricao
    assert len(DESCRICOES) == 20


def test_ca02_checagem_pega_item_inventado():
    perfil = _perfil()
    variante = gerar_variante(perfil, foco="backend-dotnet")
    secao_exp = next(s for s in variante.secoes if s.titulo == "Experiência Profissional")
    secao_exp.itens.append(ItemCV(titulo="Tech Lead", subtitulo="Google", periodo="01/2020 – atual",
                                  marcadores=["Liderei migração para Kubernetes"]))
    problemas = verificar_lastro(variante, perfil)
    assert "cargo sem lastro: Tech Lead" in problemas
    assert "empresa sem lastro: Google" in problemas
    assert any("data sem lastro: 01/2020" in p for p in problemas)
    assert "tecnologia sem lastro: Kubernetes" in problemas


# ---------------------------------------------------------------- CA-03

def test_ca03_pdf_le_experiencias_e_habilidades_sem_perda(tmp_path):
    perfil = _perfil()
    caminho, paginas = exportar_pdf(gerar_variante(perfil, foco="backend-dotnet"), tmp_path / "cv.pdf")
    texto = "\n".join(p.extract_text() for p in PdfReader(str(caminho)).pages)
    for item in [e.cargo for e in perfil.experiencias] + [e.empresa for e in perfil.experiencias] + perfil.competencias_tecnicas:
        assert item in texto, item
    # Modelo HTML/Chromium mantém o travessão (Unicode legível por ATS); o motor simples troca por hífen.
    assert ("03/2021 – 12/2022" in texto or "03/2021 - 12/2022" in texto) and "?" not in texto
    assert paginas == 1


# ---------------------------------------------------------------- CA-04

def test_ca04_cada_termo_aponta_as_vagas_de_origem():
    vagas = [Vaga(titulo=f"Dev {i}", empresa=f"Empresa {i}", foco="backend-dotnet",
                  descricao=DESCRICOES[i % len(DESCRICOES)] + " requisitos backend") for i in range(30)]
    relatorio = gerar_relatorio(_perfil(), extrair_termos(vagas))
    itens = relatorio.ja_no_cv + relatorio.tem_mas_nao_aparece + relatorio.nao_tem
    assert relatorio.ja_no_cv and relatorio.nao_tem
    for item in itens:
        assert len(item.origens) == item.vagas_em_que_aparece
    csharp = next(i for i in itens if i.termo == "C#")
    assert "Dev 0 (Empresa 0)" in csharp.origens


# ---------------------------------------------------------------- CA-05

@pytest.mark.parametrize("perfil", [
    _perfil(),
    PerfilMestre(contato=Contato(nome="A", email="a@example.com"), competencias_tecnicas=["C#"]),
])
def test_ca05_tres_opcoes_com_cargo_nos_primeiros_60(perfil):
    cargo = "Desenvolvedor Backend Júnior"
    opcoes = gerar_titulos(perfil, "backend-dotnet", cargo)
    assert len(opcoes) == 3 and len({o.texto for o in opcoes}) == 3
    for opcao in opcoes:
        assert opcao.texto.startswith(cargo) and opcao.caracteres <= 220 and opcao.essencial_nos_primeiros_60


def test_ca05_titulo_longo_e_cortado_no_limite():
    perfil = _perfil()
    perfil.formacao[0].curso = "Bacharelado em " + "Ciência da Computação " * 12
    for opcao in gerar_titulos(perfil, "backend-dotnet", "Desenvolvedor Backend Júnior"):
        assert opcao.dentro_do_limite


# ---------------------------------------------------------------- RF-IA-08

def test_lote_desligado_por_padrao_com_prazo_e_revogavel():
    usos = UsosIA()
    agora = datetime.now(timezone.utc)
    assert lote_que_cobre(usos, "justificativa-vagas", "claude") is None          # padrão: nenhum lote
    lote = criar_lote(usos, ["justificativa-vagas"], agora + timedelta(hours=2))
    assert lote_que_cobre(usos, "justificativa-vagas", "claude") is lote
    assert lote_que_cobre(usos, "justificativa-vagas", "gemini") is lote
    assert lote_que_cobre(usos, "reescrita-cv", "claude") is None                  # só as tarefas escolhidas
    assert lote_que_cobre(usos, "justificativa-vagas", "claude", agora + timedelta(hours=3)) is None  # venceu
    revogar_lote(usos, lote.id)
    assert lote_que_cobre(usos, "justificativa-vagas", "claude") is None
    with pytest.raises(ValueError, match="24"):
        criar_lote(usos, ["justificativa-vagas"], agora + timedelta(hours=30))
    with pytest.raises(ValueError, match="passou"):
        criar_lote(usos, ["justificativa-vagas"], agora - timedelta(minutes=1))


def test_uso_coberto_por_lote_fica_registrado_com_o_lote():
    usos = UsosIA()
    lote = criar_lote(usos, ["polimento-post"], datetime.now(timezone.utc) + timedelta(hours=1), motor="claude")
    uso = registrar_pedido(usos, tarefa="polimento-post", descricao="p", motor="claude", dados=[], prompt="x",
                           removidos={}, nome_arquivo="p-claude.md", autorizado=True, lote=lote.id)
    assert uso.lote == lote.id and lote.usos == [uso.id] and uso.arquivo_prompt
    revogar_lote(usos, lote.id)
    with pytest.raises(ValueError, match="não está ativa"):
        registrar_pedido(usos, tarefa="polimento-post", descricao="p", motor="claude", dados=[], prompt="x",
                         removidos={}, nome_arquivo="p2-claude.md", autorizado=True, lote=lote.id)


def test_rodada_com_lote_gera_a_justificativa_sem_fila():
    usos = carregar_usos()
    criar_lote(usos, ["justificativa-vagas"], datetime.now(timezone.utc) + timedelta(hours=1))
    salvar_usos(usos)
    uso = pedir_justificativa([VagaEncontrada(titulo="Dev", descricao="C#")], _perfil(), "perguntar", date.today())
    assert uso.autorizacao == "aprovado" and uso.lote and Path(uso.arquivo_prompt).is_file()
    assert carregar_usos().pendentes() == []


# ---------------------------------------------------------------- CA-08

def _rodada_em(dia: date, hora: int) -> RegistroRodada:
    fim = datetime(dia.year, dia.month, dia.day, hora, 5).astimezone()
    return RegistroRodada(inicio=fim - timedelta(minutes=3), fim=fim)


def test_ca08_cinco_dias_uteis_ate_as_8h():
    hoje = date(2026, 11, 20)  # sexta
    dias = [date(2026, 11, d) for d in (16, 17, 18, 19, 20)]
    salvar_base(BaseVagas(rodadas=[_rodada_em(d, 7) for d in dias]))
    agora = datetime(2026, 11, 20, 9, 0).astimezone()
    assert _ca08(hoje, agora).status == "ok"

    salvar_base(BaseVagas(rodadas=[_rodada_em(d, 7) for d in dias[:4]] + [_rodada_em(dias[4], 9)]))
    resultado = _ca08(hoje, agora)
    assert resultado.status == "pendente" and resultado.detalhe.startswith("0/5")


def test_ca08_fim_de_semana_nao_conta():
    dias = [date(2026, 11, d) for d in (13, 16, 17, 18, 19)]  # sexta + segunda a quinta
    salvar_base(BaseVagas(rodadas=[_rodada_em(d, 7) for d in dias]))
    assert _ca08(date(2026, 11, 22), datetime(2026, 11, 22, 10, 0).astimezone()).status == "pendente"
    assert _ca08(date(2026, 11, 19), datetime(2026, 11, 19, 10, 0).astimezone()).status == "ok"


# ---------------------------------------------------------------- aceite

def test_aceite_sem_dados_fica_pendente_sem_falhar():
    criterios = {c.codigo: c for c in verificar_mvp()}
    assert len(criterios) == 10
    assert criterios["CA-01"].status == "pendente"
    assert not [c for c in criterios.values() if c.status == "falhou"]


def test_aceite_com_perfil_e_vagas(dados_em_tmp):
    salvar_perfil(_perfil())
    salvar_vagas(VagasAlvo(vagas=[Vaga(titulo=f"Dev {i}", foco="backend-dotnet", descricao=DESCRICOES[i % 20])
                                  for i in range(30)]))
    criterios = {c.codigo: c for c in verificar_mvp()}
    for codigo in ("CA-01", "CA-02", "CA-04", "CA-05", "CA-06", "CA-09", "CA-10"):
        assert criterios[codigo].status == "ok", (codigo, criterios[codigo].detalhe)
    assert criterios["CA-03"].status == "manual"
    assert criterios["CA-08"].status == "pendente"


def test_aceite_acusa_prompt_gerado_sem_autorizacao(dados_em_tmp):
    (dados_em_tmp / "saidas").mkdir()
    (dados_em_tmp / "saidas" / "prompt-clandestino-claude.md").write_text("x", encoding="utf-8")
    criterios = {c.codigo: c for c in verificar_mvp()}
    assert criterios["CA-09"].status == "falhou"
