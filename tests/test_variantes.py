"""Testes de variantes por foco/idioma e exportação ATS (RF-CV-07, RF-CV-08)."""

from datetime import date

import docx
import pytest
from pypdf import PdfReader

from agente_carreira.analise.exportar import (
    aviso_de_tamanho,
    estimar_paginas_docx,
    exportar_docx,
    exportar_pdf,
    paginas_alvo_padrao,
)
from agente_carreira.analise.variantes import gerar_variante
from agente_carreira.models import (
    Area,
    Conquista,
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


def _perfil() -> PerfilMestre:
    conquista = Conquista(verbo_acao="Reduzi", descricao="fila de chamados", numero="20%")
    return PerfilMestre(
        contato=Contato(nome="Samuel Vitor", email="s@example.com", telefone="31999990000", cidade="Belo Horizonte", uf="MG"),
        links=Links(github="https://github.com/exemplo"),
        resumo="Estudante de SI com foco em backend.",
        formacao=[Formacao(curso="Sistemas de Informação", instituicao="PUC Minas", status="cursando", conclusao_prevista="2026/2")],
        projetos=[
            Projeto(nome="App de treinos", tipo="pessoal", tecnologias=["React Native"]),
            Projeto(nome="API de tarefas", tipo="pessoal", tecnologias=["C#", ".NET", "SQL Server"]),
        ],
        experiencias=[
            Experiencia(
                cargo="Atendente", empresa="Loja", vinculo=Vinculo.CLT,
                periodo=Periodo(inicio=date(2022, 1, 1), fim=date(2023, 6, 1)),
                area=Area.FORA_DE_TI, responsabilidades=["Atendimento ao cliente"],
                competencias_transferiveis=["atendimento"],
                conquista_ids=[conquista.id],
            ),
            Experiencia(
                cargo="Estagiário de desenvolvimento", empresa="Empresa Z", vinculo=Vinculo.ESTAGIO,
                periodo=Periodo(inicio=date(2024, 1, 1)),
                area=Area.TI, responsabilidades=["Manutenção de APIs REST em C#"],
                tecnologias=["C#", ".NET"],
            ),
        ],
        competencias_tecnicas=["Python", "C#", ".NET"],
        idiomas=[Idioma(idioma="Inglês", nivel="intermediário")],
        banco_conquistas=[conquista],
    )


# ---------------------------------------------------------------- RF-CV-07

def test_variante_prioriza_itens_do_foco():
    variante = gerar_variante(_perfil(), foco="backend-dotnet")
    projetos = next(s for s in variante.secoes if s.titulo == "Projetos")
    assert projetos.itens[0].titulo == "API de tarefas"  # C#/.NET antes do app mobile
    competencias = next(s for s in variante.secoes if s.titulo == "Competências")
    assert competencias.paragrafo.startswith(("C#", ".NET"))  # foco primeiro, Python depois


def test_variante_mobile_muda_a_prioridade():
    variante = gerar_variante(_perfil(), foco="mobile")
    projetos = next(s for s in variante.secoes if s.titulo == "Projetos")
    assert projetos.itens[0].titulo == "App de treinos"


def test_variante_em_ingles_traduz_titulos_e_rotulos():
    variante = gerar_variante(_perfil(), foco="backend-dotnet", idioma="en")
    titulos = [s.titulo for s in variante.secoes]
    assert "Education" in titulos and "Professional Experience" in titulos
    exp = next(s for s in variante.secoes if s.titulo == "Professional Experience")
    assert exp.itens[0].periodo.endswith("Present")
    # Conteúdo registrado permanece como está (RN-02): tradução é via reescrita.
    assert exp.itens[0].marcadores[0] == "Manutenção de APIs REST em C#"


def test_formato_unico_de_data():
    variante = gerar_variante(_perfil(), foco="backend-dotnet")
    outras = next(s for s in variante.secoes if s.titulo == "Outras Experiências")
    assert outras.itens[0].periodo == "01/2022 – 06/2023"


def test_nivel_inicial_formacao_antes_de_fora_da_area():
    variante = gerar_variante(_perfil(), foco="backend-dotnet", nivel="estagio")
    titulos = [s.titulo for s in variante.secoes]
    assert titulos.index("Formação Acadêmica") < titulos.index("Outras Experiências")


def test_conquista_vinculada_entra_na_variante():
    variante = gerar_variante(_perfil(), foco="suporte")
    outras = next(s for s in variante.secoes if s.titulo == "Outras Experiências")
    assert any("Reduzi fila de chamados" in m and "20%" in m for m in outras.itens[0].marcadores)


def test_foco_ou_idioma_invalidos():
    with pytest.raises(ValueError, match="Foco desconhecido"):
        gerar_variante(_perfil(), foco="games")
    with pytest.raises(ValueError, match="Idioma não suportado"):
        gerar_variante(_perfil(), foco="dados", idioma="es")


# ---------------------------------------------------------------- RF-CV-08

def test_exportar_docx_ats(tmp_path):
    variante = gerar_variante(_perfil(), foco="backend-dotnet")
    caminho = exportar_docx(variante, tmp_path / "cv.docx")
    doc = docx.Document(str(caminho))
    assert doc.tables == []  # sem tabelas (RF-CV-08)
    assert doc.inline_shapes == [] or len(doc.inline_shapes) == 0  # sem imagens
    assert doc.styles["Normal"].font.name == "Calibri"  # fonte padrão
    textos = "\n".join(p.text for p in doc.paragraphs)
    assert "Samuel Vitor" in textos
    assert "FORMAÇÃO ACADÊMICA" in textos
    assert "01/2022 – 06/2023" in textos


def test_exportar_pdf_ats(tmp_path):
    variante = gerar_variante(_perfil(), foco="backend-dotnet")
    caminho, paginas = exportar_pdf(variante, tmp_path / "cv.pdf")
    assert caminho.is_file()
    reader = PdfReader(str(caminho))
    assert len(reader.pages) == paginas
    texto = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert "Samuel Vitor" in texto
    assert "PROJETOS" in texto


def test_tamanho_alvo_padrao_por_nivel():
    assert paginas_alvo_padrao("estagio") == 1
    assert paginas_alvo_padrao("junior") == 1
    assert paginas_alvo_padrao("pleno") == 2


def test_aviso_quando_passa_do_alvo():
    assert aviso_de_tamanho(2, 1, "PDF") is not None
    assert aviso_de_tamanho(1, 1, "PDF") is None


def test_estimativa_de_paginas_docx_cresce_com_conteudo():
    perfil = _perfil()
    pequena = estimar_paginas_docx(gerar_variante(perfil, foco="backend-dotnet"))
    for i in range(40):
        perfil.experiencias.append(
            Experiencia(
                cargo=f"Cargo {i}", empresa="X", vinculo=Vinculo.OUTRO,
                periodo=Periodo(inicio=date(2020, 1, 1), fim=date(2020, 6, 1)),
                responsabilidades=["Atividade registrada para ocupar espaço no documento gerado"] * 3,
            )
        )
    grande = estimar_paginas_docx(gerar_variante(perfil, foco="backend-dotnet"))
    assert grande > pequena >= 1
