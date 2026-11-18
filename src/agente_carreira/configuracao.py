"""Preferências centralizadas (RF-OP-01) e modo somente sugestão (RF-OP-02).

Um só arquivo, data/configuracao.json, reúne buscas, limites diários,
limiares, horários, canais de notificação, modo por plataforma e motor de IA
por tarefa. Credenciais nunca ficam aqui: só em variáveis de ambiente (RNF-01).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator

from .radar.modelos import ConfigVagas
from .storage import diretorio_dados

ARQUIVO = "configuracao.json"
ARQUIVO_VAGAS_ANTIGO = "vagas-config.json"

MODOS_PLATAFORMA = ("copiloto", "assistido", "leitura", "desligado")
OPCOES_MOTOR = ("claude", "gemini", "local", "perguntar")
EVENTOS = ("resumo_diario", "vaga_acima_limiar", "pedido_aprovacao", "falha_adaptador", "lembrete_funil", "relatorio_semanal")

# Modo padrão por plataforma (Anexo B da especificação).
MODOS_PADRAO = {
    "linkedin": "copiloto", "gupy": "assistido", "indeed": "copiloto", "vagas.com.br": "assistido",
    "programathor": "assistido", "geekhunter": "assistido", "ciee": "assistido", "nube": "assistido",
    "cia-de-talentos": "copiloto", "companhia-de-estagios": "copiloto", "eureca": "copiloto",
    "paginas-de-carreira": "leitura", "catho": "copiloto", "infojobs": "copiloto", "remotar": "copiloto",
    "wellfound": "copiloto", "glassdoor": "leitura", "github": "leitura",
}

# Domínio → plataforma do catálogo; domínio desconhecido conta como página de carreira.
DOMINIOS_PLATAFORMA = {
    "linkedin.com": "linkedin", "gupy.io": "gupy", "indeed.com": "indeed", "vagas.com.br": "vagas.com.br",
    "programathor.com.br": "programathor", "geekhunter.com.br": "geekhunter", "ciee.org.br": "ciee",
    "nube.com.br": "nube", "ciadetalentos.com.br": "cia-de-talentos", "catho.com.br": "catho",
    "infojobs.com.br": "infojobs", "remotar.com.br": "remotar", "wellfound.com": "wellfound",
    "glassdoor.com": "glassdoor", "glassdoor.com.br": "glassdoor", "github.com": "github",
}

# Editados por comandos próprios, não por 'agente config definir'.
CAMINHOS_COM_COMANDO = {
    "vagas.buscas": "agente busca ...",
    "vagas.preferencias": "agente vagas feedback ...",
    # Ligar exige aceitar o risco de forma explícita (RN-04).
    "linkedin_automatico.ativo": "agente li automatico ligar --aceito-o-risco",
    "linkedin_automatico.aceito_risco_em": "agente li automatico ligar --aceito-o-risco",
}


class Limites(BaseModel):
    candidaturas_por_dia: int = 10          # RF-CA-05
    aderencia_minima_candidatura: int = 60  # RF-CA-05
    mensagens_por_dia: int = 5              # RN-11
    acoes_por_sessao: int = 20              # RN-05
    intervalo_entre_acoes_segundos: int = 30
    reaplicar_mesma_empresa_dias: int = 90  # RF-CA-04
    followup_dias: int = 7                  # RF-AC-03


class Horarios(BaseModel):
    resumo_ate: str = "08:00"               # RF-VG-09, RNF-11
    relatorio_semanal: str = "domingo 20:00"  # UC-11


class Notificacao(BaseModel):
    """RF-OP-04. O padrão da especificação é o e-mail; sem configuração, cai para arquivo."""

    canal: Literal["arquivo", "email", "push"] = "email"
    email_para: str | None = None
    eventos: dict[str, bool] = Field(default_factory=lambda: {e: True for e in EVENTOS})


class LinkedInAutomatico(BaseModel):
    """Navegador automático no LinkedIn (RN-04: só por opção do usuário, ciente do risco). Desligado por padrão.

    Limites e seletores ficam aqui, não no código (RNF-14): o LinkedIn muda de layout sem aviso.
    """

    ativo: bool = False
    aceito_risco_em: datetime | None = None
    consultas_por_rodada: int = 4            # páginas de busca abertas por rodada (RN-05)
    vagas_por_consulta: int = 25
    detalhes_por_rodada: int = 12            # vagas novas abertas para ler a descrição
    intervalo_min_s: float = 4.0             # pausa aleatória entre páginas e ações
    intervalo_max_s: float = 11.0
    ultimas_horas: int = 24                  # só vagas publicadas nesse período
    max_etapas_candidatura: int = 8
    local_padrao: str = "Belo Horizonte, Minas Gerais, Brasil"
    seletores_descricao: list[str] = Field(default_factory=lambda: [
        "#job-details", ".jobs-description__content", ".jobs-box__html-content", ".description__text",
    ])
    botoes_candidatura: list[str] = Field(default_factory=lambda: ["Candidatura simplificada", "Easy Apply"])
    botoes_avancar: list[str] = Field(default_factory=lambda: [
        "Avançar", "Próximo", "Próxima", "Next", "Continuar", "Continue", "Revisar", "Review",
    ])
    botoes_enviar: list[str] = Field(default_factory=lambda: [
        "Enviar candidatura", "Submit application", "Enviar", "Submit",
    ])

    @field_validator("intervalo_max_s")
    @classmethod
    def _intervalo(cls, valor: float, info) -> float:
        minimo = info.data.get("intervalo_min_s", 0)
        if valor < minimo:
            raise ValueError("intervalo_max_s precisa ser maior ou igual a intervalo_min_s")
        return valor


class Configuracao(BaseModel):
    somente_sugestao: bool = False          # RF-OP-02
    linkedin_automatico: LinkedInAutomatico = Field(default_factory=LinkedInAutomatico)
    motores: dict[str, str] = Field(default_factory=dict)  # RF-IA-01
    limites: Limites = Field(default_factory=Limites)
    horarios: Horarios = Field(default_factory=Horarios)
    notificacao: Notificacao = Field(default_factory=Notificacao)
    modos_plataforma: dict[str, str] = Field(default_factory=lambda: dict(MODOS_PADRAO))
    vagas: ConfigVagas = Field(default_factory=ConfigVagas)

    @field_validator("modos_plataforma")
    @classmethod
    def _modos_validos(cls, valor: dict[str, str]) -> dict[str, str]:
        invalidos = {p: m for p, m in valor.items() if m not in MODOS_PLATAFORMA}
        if invalidos:
            raise ValueError(f"modo inválido {invalidos}; use: {', '.join(MODOS_PLATAFORMA)}")
        return valor

    @field_validator("motores")
    @classmethod
    def _motores_validos(cls, valor: dict[str, str]) -> dict[str, str]:
        invalidos = {t: m for t, m in valor.items() if m not in OPCOES_MOTOR}
        if invalidos:
            raise ValueError(f"motor inválido {invalidos}; use: {', '.join(OPCOES_MOTOR)}")
        return valor

    def motor_da_tarefa(self, tarefa: str) -> str:
        return self.motores.get(tarefa, "perguntar")


# ---------------------------------------------------------------- persistência

def carregar_configuracao() -> Configuracao:
    caminho = diretorio_dados() / ARQUIVO
    config = Configuracao.model_validate_json(caminho.read_text(encoding="utf-8")) if caminho.is_file() else Configuracao()
    antigo = diretorio_dados() / ARQUIVO_VAGAS_ANTIGO
    if antigo.is_file():
        # Migração única: as preferências de vagas passam a morar no arquivo central.
        if not config.vagas.buscas:
            config.vagas = ConfigVagas.model_validate_json(antigo.read_text(encoding="utf-8"))
        salvar_configuracao(config)
        antigo.replace(antigo.with_name(antigo.name + ".migrado"))
    return config


def salvar_configuracao(config: Configuracao) -> Path:
    caminho = diretorio_dados() / ARQUIVO
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return caminho


# ---------------------------------------------------------------- edição por caminho

def _interpretar(texto: str) -> object:
    t = texto.strip()
    minusculo = t.lower()
    if minusculo in {"true", "sim", "s", "yes", "ligado", "on"}:
        return True
    if minusculo in {"false", "nao", "não", "n", "no", "desligado", "off"}:
        return False
    if minusculo in {"null", "nenhum", "none", ""}:
        return None
    for conversor in (int, float):
        try:
            return conversor(t)
        except ValueError:
            pass
    return t


def definir(config: Configuracao, caminho: str, valor: str) -> Configuracao:
    """Altera uma preferência pelo caminho (ex.: limites.candidaturas_por_dia) com validação."""
    for prefixo, comando in CAMINHOS_COM_COMANDO.items():
        if caminho == prefixo or caminho.startswith(prefixo + "."):
            raise ValueError(f"'{caminho}' é editado com '{comando}'.")
    dados = config.model_dump(mode="json")
    partes = caminho.split(".")
    alvo: object = dados
    for parte in partes[:-1]:
        if not isinstance(alvo, dict) or parte not in alvo:
            raise ValueError(f"Preferência desconhecida: {caminho}")
        alvo = alvo[parte]
    chave = partes[-1]
    dicionario_livre = len(partes) >= 2 and partes[-2] in {"motores", "modos_plataforma", "eventos"}
    if not isinstance(alvo, dict) or (chave not in alvo and not dicionario_livre):
        raise ValueError(f"Preferência desconhecida: {caminho}")
    if isinstance(alvo.get(chave), dict):
        raise ValueError(f"'{caminho}' é um grupo; defina um item dele (ex.: {caminho}.<nome>).")
    if isinstance(alvo.get(chave), list):
        alvo[chave] = [p.strip() for p in valor.split(",") if p.strip()]
    else:
        alvo[chave] = _interpretar(valor)
    try:
        return Configuracao.model_validate(dados)
    except ValidationError as erro:
        primeiro = erro.errors()[0]
        raise ValueError(f"Valor inválido para {caminho}: {primeiro['msg']}") from erro


# ---------------------------------------------------------------- RF-OP-02 e modo por plataforma

class ModoSomenteSugestao(Exception):
    """Modo global ligado: nenhuma plataforma é tocada."""


def plataforma_da_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    for dominio, plataforma in DOMINIOS_PLATAFORMA.items():
        if host == dominio or host.endswith("." + dominio):
            return plataforma
    return "paginas-de-carreira"


def plataforma_permite_leitura(config: Configuracao, url: str) -> bool:
    """Falso no modo somente sugestão ou com a plataforma desligada."""
    if config.somente_sugestao:
        return False
    return config.modos_plataforma.get(plataforma_da_url(url), "leitura") != "desligado"


def exigir_plataforma(config: Configuracao, acao: str) -> None:
    if config.somente_sugestao:
        raise ModoSomenteSugestao(
            f"Modo somente sugestão ligado: {acao} não foi feito, porque nenhuma plataforma é tocada. "
            "Para desligar: agente config sugestao --desligar"
        )
