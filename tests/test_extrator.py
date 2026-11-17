"""Testes das heurísticas de extração de texto de CV (RF-PM-02)."""

from agente_carreira.importadores.extrator import extrair_de_texto

CV_EXEMPLO = """
Samuel Vitor
Belo Horizonte, MG
samuelvitor@example.com | +55 (31) 99876-5432
github.com/SamuelVitor227 | linkedin.com/in/samuel-vitor
Portfólio: https://samuel.dev/projetos

Resumo
Estudante de Sistemas de Informação na PUC Minas, foco em backend com C# e .NET.
Experiência com SQL Server, Docker e Git. Projetos com Python e AWS.
"""


def test_extrai_email():
    r = extrair_de_texto(CV_EXEMPLO, origem="teste")
    assert r.email == "samuelvitor@example.com"


def test_extrai_telefone():
    r = extrair_de_texto(CV_EXEMPLO, origem="teste")
    assert r.telefone is not None
    assert "99876" in r.telefone


def test_extrai_github_e_linkedin_normalizados():
    r = extrair_de_texto(CV_EXEMPLO, origem="teste")
    assert r.github == "https://github.com/SamuelVitor227"
    assert r.linkedin == "https://linkedin.com/in/samuel-vitor"


def test_extrai_outros_links_sem_duplicar_redes():
    r = extrair_de_texto(CV_EXEMPLO, origem="teste")
    assert "https://samuel.dev/projetos" in r.outros_links
    assert all("github.com" not in l for l in r.outros_links)


def test_detecta_tecnologias_citadas():
    r = extrair_de_texto(CV_EXEMPLO, origem="teste")
    for esperada in ["C#", ".NET", "SQL Server", "Docker", "Git", "Python", "AWS"]:
        assert esperada in r.competencias, esperada


def test_nao_inventa_tecnologia_ausente():
    r = extrair_de_texto(CV_EXEMPLO, origem="teste")
    assert "Kubernetes" not in r.competencias


def test_texto_vazio_resulta_em_importacao_vazia():
    r = extrair_de_texto("   ", origem="teste")
    assert r.vazio()


def test_guarda_texto_bruto_para_conferencia():
    r = extrair_de_texto(CV_EXEMPLO, origem="teste")
    assert r.texto_bruto is not None
    assert "PUC Minas" in r.texto_bruto
