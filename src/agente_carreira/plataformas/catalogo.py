"""Catálogo de plataformas (RF-PL-01, Anexo B).

Para cada plataforma: URL, foco, prioridade, modo de integração, campos
exigidos, limites de caracteres, formatos e tamanho de upload, data da revisão
dos termos e regras específicas (cobra do candidato, testes técnicos, só
estágio). Limites e datas são configuração (RNF-14): o usuário ajusta em
data/plataformas-ajustes.json, sem mexer no código. Limites que não foram
conferidos ficam vazios — o agente não inventa números.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..arquivos import gravar_modelo, ler_modelo
from ..storage import diretorio_dados

ARQUIVO_AJUSTES = "plataformas-ajustes.json"
DIAS_REVISAO_TERMOS = 180  # RNF-06: revisão dos termos a cada 6 meses


class CampoPlataforma(BaseModel):
    id: str
    rotulo: str
    origem: str                    # de onde vem o valor no perfil-mestre (ou "manual")
    obrigatorio: bool = False
    limite: int | None = None      # caracteres; None = não conferido
    instrucao: str | None = None


class VarianteAlvo(BaseModel):
    """RF-PL-06: variante de CV adequada ao foco da plataforma."""

    foco: str = "backend-dotnet"
    idioma: str = "pt"
    nivel: str = "estagio"


class Plataforma(BaseModel):
    id: str
    nome: str
    url: str
    foco: str
    prioridade: Literal["P1", "P2", "P3", "Apoio"]
    modo_padrao: str
    observacao: str = ""
    campos: list[CampoPlataforma] = Field(default_factory=list)
    formatos_cv: list[str] = Field(default_factory=lambda: ["pdf"])
    tamanho_max_mb: float | None = None
    termos_revisados_em: date | None = None
    variante: VarianteAlvo = Field(default_factory=VarianteAlvo)
    cobra_candidato: bool = False          # RF-PL-10
    etapas_pagas: str | None = None
    testes_tecnicos: bool = False          # RF-PL-11
    so_estagio: bool = False               # RN-07
    cadastravel: bool = True

    def campo(self, id_: str) -> CampoPlataforma:
        for campo in self.campos:
            if campo.id == id_:
                return campo
        raise ValueError(f"A plataforma {self.id} não tem o campo {id_!r}.")


def _campos(*extras: CampoPlataforma, sem: tuple[str, ...] = ()) -> list[CampoPlataforma]:
    base = [
        CampoPlataforma(id="nome", rotulo="Nome completo", origem="contato.nome", obrigatorio=True),
        CampoPlataforma(id="email", rotulo="E-mail", origem="contato.email", obrigatorio=True),
        CampoPlataforma(id="telefone", rotulo="Telefone", origem="contato.telefone", obrigatorio=True),
        CampoPlataforma(id="cidade", rotulo="Cidade", origem="contato.cidade", obrigatorio=True),
        CampoPlataforma(id="uf", rotulo="Estado", origem="contato.uf"),
        CampoPlataforma(id="linkedin", rotulo="LinkedIn", origem="links.linkedin"),
        CampoPlataforma(id="github", rotulo="GitHub", origem="links.github"),
        CampoPlataforma(id="portfolio", rotulo="Portfólio", origem="links.portfolio"),
        CampoPlataforma(id="resumo", rotulo="Resumo profissional", origem="resumo"),
        CampoPlataforma(id="formacao", rotulo="Formação", origem="formacao", obrigatorio=True),
        CampoPlataforma(id="experiencias", rotulo="Experiências", origem="experiencias", obrigatorio=True),
        CampoPlataforma(id="habilidades", rotulo="Habilidades", origem="habilidades", obrigatorio=True),
        CampoPlataforma(id="idiomas", rotulo="Idiomas", origem="idiomas"),
        CampoPlataforma(id="certificacoes", rotulo="Certificações", origem="certificacoes"),
        CampoPlataforma(id="cv", rotulo="Currículo (arquivo)", origem="cv", obrigatorio=True),
    ]
    return [c for c in base if c.id not in sem] + list(extras)


CPF = CampoPlataforma(id="cpf", rotulo="CPF", origem="manual", obrigatorio=True,
                      instrucao="Digite você: o agente nunca guarda CPF (RN-08).")
PRETENSAO = CampoPlataforma(id="pretensao", rotulo="Pretensão salarial", origem="resposta:pretensao",
                            instrucao="Só a faixa que você cadastrou ('agente respostas'); sem faixa, deixe para você (RN-09).")
CARGA = CampoPlataforma(id="carga_horaria", rotulo="Carga horária disponível", origem="resposta:carga_horaria",
                        instrucao="Estágio: no máximo 6 h/dia e 30 h/semana (RN-07).")
APRESENTACAO = CampoPlataforma(id="apresentacao", rotulo="Apresente-se", origem="apresentacao",
                               instrucao="Texto geral; em cada candidatura o kit traz uma versão para a vaga (RF-PL-05).")
PAIS = CampoPlataforma(id="pais", rotulo="País", origem="contato.pais", obrigatorio=True)

CATALOGO_PADRAO: list[Plataforma] = [
    Plataforma(id="linkedin", nome="LinkedIn", url="https://www.linkedin.com", foco="Rede profissional e vagas",
               prioridade="P1", modo_padrao="copiloto", cadastravel=False,
               observacao="Termos proíbem bots (seção 2.3). O perfil é cuidado pelo M2: 'agente li'."),
    Plataforma(id="gupy", nome="Gupy", url="https://portal.gupy.io", prioridade="P1", modo_padrao="assistido",
               foco="Processos seletivos de empresas médias e grandes",
               observacao="Uma conta serve para centenas de vagas; a ordenação lê só Experiência e Habilidades "
                          "(RF-PL-05). O CV enviado preenche os campos e precisa ser revisado (RF-PL-04).",
               campos=_campos(PAIS, CPF, APRESENTACAO), formatos_cv=["pdf", "doc", "docx"]),
    Plataforma(id="indeed", nome="Indeed", url="https://br.indeed.com", prioridade="P2", modo_padrao="copiloto",
               foco="Agregador geral", observacao="Reúne vagas de várias fontes; vagas entram pelos alertas por e-mail.",
               campos=_campos()),
    Plataforma(id="vagas.com.br", nome="Vagas.com.br", url="https://www.vagas.com.br", prioridade="P2",
               modo_padrao="assistido", foco="Geral e corporativo, com estágio e trainee",
               observacao="Forte em empresas maiores.", campos=_campos(PRETENSAO)),
    Plataforma(id="programathor", nome="Programathor", url="https://programathor.com.br", prioridade="P2",
               modo_padrao="assistido", foco="Plataforma para desenvolvedores", testes_tecnicos=True,
               observacao="Testes técnicos são seus (RN-13); o agente prepara material de estudo.",
               campos=_campos(PRETENSAO)),
    Plataforma(id="geekhunter", nome="GeekHunter", url="https://www.geekhunter.com.br", prioridade="P2",
               modo_padrao="assistido", foco="Plataforma para desenvolvedores", testes_tecnicos=True,
               observacao="Testes técnicos são seus (RN-13); o agente prepara material de estudo.",
               campos=_campos(PRETENSAO)),
    Plataforma(id="ciee", nome="CIEE", url="https://portal.ciee.org.br", prioridade="P2", modo_padrao="assistido",
               foco="Agente de integração de estágio", so_estagio=True,
               observacao="Só enquanto houver matrícula (RN-07); sai do resumo com a formatura.",
               campos=_campos(CARGA), variante=VarianteAlvo(nivel="estagio")),
    Plataforma(id="nube", nome="Nube", url="https://www.nube.com.br", prioridade="P2", modo_padrao="assistido",
               foco="Agente de integração de estágio", so_estagio=True,
               observacao="Só enquanto houver matrícula (RN-07).", campos=_campos(CARGA), variante=VarianteAlvo(nivel="estagio")),
    Plataforma(id="cia-de-talentos", nome="Cia de Talentos", url="https://www.ciadetalentos.com.br", prioridade="P2",
               modo_padrao="copiloto", foco="Programas de estágio e trainee", observacao="Inscrições com prazo.",
               campos=_campos()),
    Plataforma(id="companhia-de-estagios", nome="Companhia de Estágios", url="https://www.ciadeestagios.com.br",
               prioridade="P2", modo_padrao="copiloto", foco="Programas de estágio e trainee",
               observacao="Inscrições com prazo.", campos=_campos()),
    Plataforma(id="eureca", nome="Eureca", url="https://eureca.me", prioridade="P2", modo_padrao="copiloto",
               foco="Programas de estágio e trainee", observacao="Inscrições com prazo.", campos=_campos()),
    Plataforma(id="catho", nome="Catho", url="https://www.catho.com.br", prioridade="P3", modo_padrao="copiloto",
               foco="Geral", cobra_candidato=True, etapas_pagas="planos pagos para destacar o currículo e ver mais vagas",
               observacao="Pode cobrar do candidato (RF-PL-10): o agente não contrata nada.", campos=_campos(PRETENSAO)),
    Plataforma(id="infojobs", nome="InfoJobs", url="https://www.infojobs.com.br", prioridade="P3",
               modo_padrao="copiloto", foco="Volume em vagas operacionais e administrativas",
               observacao="Pouca aderência ao foco em TI.", campos=_campos(PRETENSAO)),
    Plataforma(id="remotar", nome="Remotar", url="https://remotar.com.br", prioridade="P3", modo_padrao="copiloto",
               foco="Vagas em home office", observacao="Vagas de tecnologia mostram o salário.", campos=_campos()),
    Plataforma(id="wellfound", nome="Wellfound", url="https://wellfound.com", prioridade="P3", modo_padrao="copiloto",
               foco="Startups e tecnologia, com vagas remotas", observacao="Vagas internacionais: CV em inglês.",
               campos=_campos(sem=("uf",)), variante=VarianteAlvo(idioma="en", nivel="junior")),
    Plataforma(id="glassdoor", nome="Glassdoor", url="https://www.glassdoor.com.br", prioridade="Apoio",
               modo_padrao="leitura", foco="Avaliações de empresas, entrevistas e salários; não é site de vagas",
               observacao="Usado na preparação de entrevistas (RF-AC-04), por leitura manual.", cadastravel=False),
]


class Ajustes(BaseModel):
    """Configuração editável pelo usuário (RNF-14)."""

    termos_revisados_em: dict[str, date] = Field(default_factory=dict)
    limites: dict[str, dict[str, int]] = Field(default_factory=dict)
    tamanho_max_mb: dict[str, float] = Field(default_factory=dict)


def carregar_ajustes() -> Ajustes:
    caminho = diretorio_dados() / ARQUIVO_AJUSTES
    return ler_modelo(caminho, Ajustes)


def salvar_ajustes(ajustes: Ajustes) -> Path:
    caminho = diretorio_dados() / ARQUIVO_AJUSTES
    gravar_modelo(caminho, ajustes)
    return caminho


def catalogo() -> list[Plataforma]:
    """Catálogo padrão com os ajustes do usuário aplicados."""
    ajustes = carregar_ajustes()
    plataformas = []
    for padrao in CATALOGO_PADRAO:
        p = padrao.model_copy(deep=True)
        p.termos_revisados_em = ajustes.termos_revisados_em.get(p.id, p.termos_revisados_em)
        p.tamanho_max_mb = ajustes.tamanho_max_mb.get(p.id, p.tamanho_max_mb)
        for campo in p.campos:
            campo.limite = ajustes.limites.get(p.id, {}).get(campo.id, campo.limite)
        plataformas.append(p)
    return plataformas


def buscar_plataforma(id_: str) -> Plataforma:
    for p in catalogo():
        if p.id == id_:
            return p
    raise ValueError(f"Plataforma {id_!r} não está no catálogo. Veja 'agente plataformas'.")


def termos_vencidos(plataforma: Plataforma, hoje: date | None = None) -> bool:
    """RNF-06: termos nunca revisados ou revisados há mais de 6 meses."""
    hoje = hoje or date.today()
    return plataforma.termos_revisados_em is None or (hoje - plataforma.termos_revisados_em).days > DIAS_REVISAO_TERMOS
