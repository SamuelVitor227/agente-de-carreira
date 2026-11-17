"""Modelos do radar de vagas: buscas salvas, configuração e vagas encontradas."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from ..storage import diretorio_dados
from .texto import slug

ARQUIVO_CONFIG = "vagas-config.json"
ARQUIVO_VAGAS = "vagas-encontradas.json"
MAX_EMAILS_LEMBRADOS = 5000

NIVEIS = ("estagio", "trainee", "junior", "pleno", "senior")
MODELOS = ("presencial", "hibrido", "remoto")
CONTRATOS = ("estagio", "clt", "pj")

# Perfil-alvo inicial da especificação: Belo Horizonte e região metropolitana.
REGIAO_BH = [
    "Belo Horizonte", "Contagem", "Betim", "Nova Lima", "Sabará", "Santa Luzia", "Ribeirão das Neves",
    "Ibirité", "Vespasiano", "Lagoa Santa", "Sarzedo", "Brumadinho", "Pedro Leopoldo", "Confins",
    "Raposos", "Caeté",
]

# Cargos e sinônimos por foco (configuração; cresce com o uso).
SINONIMOS_POR_FOCO: dict[str, list[str]] = {
    "backend-dotnet": [
        "desenvolvedor .net", "desenvolvedor c#", "desenvolvedor backend", "desenvolvedor back-end",
        "programador .net", "programador c#", "backend developer", ".net developer", "c# developer",
        "estágio desenvolvimento", "estágio programação", "estágio .net", "desenvolvedor júnior",
        "desenvolvedor de software", "engenheiro de software",
    ],
    "cloud-aws": [
        "cloud", "aws", "devops", "sre", "infraestrutura cloud", "estágio cloud", "estágio infraestrutura",
    ],
    "mobile": [
        "desenvolvedor mobile", "react native", "desenvolvedor android", "desenvolvedor ios",
        "mobile developer", "estágio mobile",
    ],
    "dados": [
        "analista de dados", "engenheiro de dados", "cientista de dados", "data analyst", "data engineer",
        "estágio dados", "estágio bi", "business intelligence",
    ],
    "suporte": [
        "suporte", "analista de suporte", "help desk", "service desk", "suporte técnico", "sustentação",
        "estágio ti", "estágio suporte",
    ],
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- RF-VG-01

class EmpresaAlvo(BaseModel):
    nome: str
    pagina_carreira: str | None = None


class BuscaSalva(BaseModel):
    nome: str
    cargos: list[str]
    niveis: list[str] = Field(default_factory=lambda: ["estagio", "trainee", "junior"])
    modelos: list[str] = Field(default_factory=lambda: list(MODELOS))
    localidades: list[str] = Field(default_factory=lambda: list(REGIAO_BH))
    raio_km: int = 30
    remoto_brasil: bool = True
    contratos: list[str] = Field(default_factory=lambda: list(CONTRATOS))
    salario_minimo: float | None = None
    idiomas: list[str] = Field(default_factory=lambda: ["pt", "en"])
    empresas_alvo: list[EmpresaAlvo] = Field(default_factory=list)
    empresas_bloqueadas: list[str] = Field(default_factory=list)
    limite_anos_experiencia: int = 2


class ConfigVagas(BaseModel):
    buscas: list[BuscaSalva] = Field(default_factory=list)
    limiar_alerta: int = 80        # RF-VG-10
    limiar_candidatar: int = 70
    limiar_salvar: int = 50
    dias_validade: int = 30        # RF-VG-12
    hora_rodada: str = "07:00"     # RF-VG-03
    peso_cobertura: float = 0.7
    peso_similaridade: float = 0.3
    preferencias: dict[str, float] = Field(default_factory=dict)  # RF-VG-11
    # Domínios cujas páginas de vaga podem ser lidas (com robots.txt respeitado).
    dominios_permitidos: list[str] = Field(default_factory=lambda: ["gupy.io"])
    # Plataformas cujos termos proíbem leitura automatizada: o usuário cola a descrição.
    dominios_copiloto: list[str] = Field(default_factory=lambda: [
        "linkedin.com", "indeed.com", "glassdoor.com", "catho.com.br", "infojobs.com.br",
    ])

    def bloqueadas(self) -> set[str]:
        return {slug(e) for b in self.buscas for e in b.empresas_bloqueadas if slug(e)}

    def empresas_alvo(self) -> list[EmpresaAlvo]:
        vistas: dict[str, EmpresaAlvo] = {}
        for busca in self.buscas:
            for empresa in busca.empresas_alvo:
                vistas.setdefault(slug(empresa.nome), empresa)
        return list(vistas.values())

    def todos_cargos(self) -> list[str]:
        return [c for b in self.buscas for c in b.cargos]

    def buscar(self, nome: str) -> BuscaSalva:
        for busca in self.buscas:
            if busca.nome == nome:
                return busca
        raise ValueError(f"Busca {nome!r} não existe.")


# ---------------------------------------------------------------- vagas

class Fonte(BaseModel):
    tipo: Literal["email", "pagina", "link", "manual"]
    origem: str  # ex.: linkedin-alerta, pagina:empresa.gupy.io
    url: str | None = None
    coletada_em: datetime = Field(default_factory=_agora)


class Sinal(BaseModel):
    tipo: str
    mensagem: str
    gravidade: Literal["forte", "atencao"] = "forte"


class Aderencia(BaseModel):
    nota: int
    atendidos: list[str] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)
    faltam_no_cv: list[str] = Field(default_factory=list)
    similaridade: float = 0.0
    cobertura: float | None = None
    ajuste_feedback: float = 0.0
    justificativa: str = ""


class Feedback(BaseModel):
    interessa: bool
    motivo: str | None = None
    quando: datetime = Field(default_factory=_agora)


class VagaBruta(BaseModel):
    """O que uma fonte entregou, antes da extração e da triagem."""

    titulo: str
    empresa: str | None = None
    local: str | None = None
    link: str | None = None
    descricao: str = ""
    fonte_tipo: Literal["email", "pagina", "link", "manual"]
    fonte_origem: str
    publicada_em: date | None = None
    valida_ate: date | None = None
    modelo: str | None = None
    contrato: str | None = None
    salario_min: float | None = None
    salario_max: float | None = None


StatusVaga = Literal["nova", "no_resumo", "salva", "descartada", "expirada", "eliminada"]


class VagaEncontrada(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:6])
    titulo: str
    empresa: str | None = None
    local: str | None = None
    modelo: str | None = None
    contrato: str | None = None
    nivel: str | None = None
    salario_min: float | None = None
    salario_max: float | None = None
    publicada_em: date | None = None
    valida_ate: date | None = None
    link: str | None = None
    descricao: str = ""
    requisitos_obrigatorios: list[str] = Field(default_factory=list)
    requisitos_desejaveis: list[str] = Field(default_factory=list)
    horas_dia: int | None = None
    horas_semana: int | None = None
    anos_experiencia: int | None = None
    idiomas_exigidos: dict[str, int] = Field(default_factory=dict)
    idioma: str | None = None
    fontes: list[Fonte] = Field(default_factory=list)
    primeira_coleta: datetime = Field(default_factory=_agora)
    ultima_coleta: datetime = Field(default_factory=_agora)
    status: StatusVaga = "nova"
    busca: str | None = None
    motivos_eliminacao: list[str] = Field(default_factory=list)
    motivo_expiracao: str | None = None
    sinais: list[Sinal] = Field(default_factory=list)
    aderencia: Aderencia | None = None
    feedback: Feedback | None = None
    alertada: bool = False
    justificativa_ia: str | None = None
    motor_justificativa: str | None = None  # RF-IA-06

    @property
    def risco(self) -> bool:
        """Indício forte de golpe ou instrução embutida: não entra como recomendada (RN-12)."""
        return any(s.gravidade == "forte" for s in self.sinais)

    @property
    def nota(self) -> int:
        return self.aderencia.nota if self.aderencia else 0


class BaseVagas(BaseModel):
    itens: list[VagaEncontrada] = Field(default_factory=list)
    emails_processados: list[str] = Field(default_factory=list)
    ultima_rodada: datetime | None = None
    ultimo_resumo_ids: list[str] = Field(default_factory=list)
    ultimo_resumo_data: date | None = None

    def buscar(self, id_: str) -> VagaEncontrada:
        for vaga in self.itens:
            if vaga.id == id_:
                return vaga
        raise ValueError(f"Vaga {id_!r} não existe.")

    def lembrar_email(self, msgid: str) -> None:
        self.emails_processados.append(msgid)
        if len(self.emails_processados) > MAX_EMAILS_LEMBRADOS:
            self.emails_processados = self.emails_processados[-MAX_EMAILS_LEMBRADOS:]


# ---------------------------------------------------------------- persistência

def _caminho(arquivo: str) -> Path:
    return diretorio_dados() / arquivo


def carregar_config() -> ConfigVagas:
    caminho = _caminho(ARQUIVO_CONFIG)
    if not caminho.is_file():
        return ConfigVagas()
    return ConfigVagas.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_config(config: ConfigVagas) -> Path:
    caminho = _caminho(ARQUIVO_CONFIG)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return caminho


def carregar_base() -> BaseVagas:
    caminho = _caminho(ARQUIVO_VAGAS)
    if not caminho.is_file():
        return BaseVagas()
    return BaseVagas.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_base(base: BaseVagas) -> Path:
    caminho = _caminho(ARQUIVO_VAGAS)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(base.model_dump_json(indent=2), encoding="utf-8")
    return caminho
