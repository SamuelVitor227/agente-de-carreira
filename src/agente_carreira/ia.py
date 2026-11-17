"""Uso de IA: motor por tarefa, autorização, dados mínimos e registro (RF-IA-01 a RF-IA-05).

Os motores externos são as assinaturas do usuário (Claude Pro, Gemini Pro),
usadas em modo copiloto: o agente gera o prompt e o usuário cola no motor.
O ponto de controle é, portanto, a geração do prompt. Nenhum prompt é escrito
sem autorização registrada (RN-14); um pedido negado não gera nada e fica
pendente na fila (RF-IA-03); todo prompt passa por um filtro que remove dados
que nunca podem ir para uma IA (RF-IA-04); e cada pedido fica no registro de
uso (RF-IA-05).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .configuracao import OPCOES_MOTOR, Configuracao, carregar_configuracao, salvar_configuracao  # noqa: F401
from .models import PerfilMestre
from .storage import diretorio_dados

ARQUIVO_USOS = "uso-ia.json"

MOTORES_EXTERNOS = ("claude", "gemini")

# Tarefas que podem usar IA externa. "perguntar" é o padrão da especificação
# (decisões em aberto: motor padrão por tarefa = perguntar a cada uso).
TAREFAS: dict[str, str] = {
    "reescrita-cv": "reescrever resumo, experiências e projetos do currículo (RF-CV-03)",
    "traducao-linkedin": "traduzir o perfil do LinkedIn para inglês (RF-LI-10)",
    "polimento-post": "melhorar o texto de publicações do LinkedIn (RF-LI-12)",
    "justificativa-vagas": "escrever a justificativa de aderência das vagas do resumo diário (M4)",
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- RF-IA-01 (preferência central, RF-OP-01)

def definir_motor(config: Configuracao, tarefa: str, motor: str) -> None:
    if tarefa not in TAREFAS:
        raise ValueError(f"Tarefa desconhecida: {tarefa!r}. Válidas: {', '.join(TAREFAS)}.")
    if motor not in OPCOES_MOTOR:
        raise ValueError(f"Motor inválido: {motor!r}. Válidos: {', '.join(OPCOES_MOTOR)}.")
    config.motores[tarefa] = motor


def resolver_motor(tarefa: str, motor_cli: str | None, config: Configuracao) -> str:
    """Motor efetivo: o pedido na linha de comando, senão o configurado; 'perguntar' propõe o Claude."""
    if motor_cli:
        if motor_cli not in (*MOTORES_EXTERNOS, "local"):
            raise ValueError(f"Motor inválido: {motor_cli!r}. Use claude, gemini ou local.")
        return motor_cli
    configurado = config.motor_da_tarefa(tarefa)
    return "claude" if configurado == "perguntar" else configurado


def outro_motor(motor: str) -> str:
    return "gemini" if motor == "claude" else "claude"


# ---------------------------------------------------------------- RF-IA-04

# Ordem importa: padrões mais específicos primeiro.
PADROES_SENSIVEIS: list[tuple[str, re.Pattern[str]]] = [
    ("e-mail", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("CPF", re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")),
    ("CEP", re.compile(r"(?<!\d)\d{5}-\d{3}(?!\d)")),
    ("RG", re.compile(r"\bRG\b[\s:.ºn°]*[\w.\-/]*\d[\w.\-/]*", re.IGNORECASE)),
    ("endereço", re.compile(
        r"\b(?:rua|r\.|avenida|av\.|travessa|tv\.|alameda|rodovia|praça)\s+[^\n,;]{2,60}?,?\s*(?:n[º°o.]?\s*)?\d{1,5}\b",
        re.IGNORECASE,
    )),
    # Exige DDD (10 ou 11 dígitos) e não pega números dentro de URLs ou identificadores.
    ("telefone", re.compile(r"(?<![\w/.\-])(?:\+?55[\s-]?)?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}(?!\w)")),
]


def valores_sensiveis(perfil: PerfilMestre | None) -> list[str]:
    """Valores exatos do perfil que nunca vão para a IA (contato)."""
    if perfil is None:
        return []
    valores = [perfil.contato.email]
    if perfil.contato.telefone:
        valores.append(perfil.contato.telefone)
        digitos = re.sub(r"\D", "", perfil.contato.telefone)
        if digitos != perfil.contato.telefone:
            valores.append(digitos)
    return [v for v in valores if v and len(v) >= 4]


def sanitizar(texto: str, valores: list[str] | None = None) -> tuple[str, dict[str, int]]:
    """Remove do prompt dados que nunca podem ir para um motor externo (RF-IA-04)."""
    removidos: Counter[str] = Counter()
    for valor in valores or []:
        if valor in texto:
            removidos["dado de contato"] += texto.count(valor)
            texto = texto.replace(valor, "[removido: dado de contato]")
    for tipo, padrao in PADROES_SENSIVEIS:
        texto, quantidade = padrao.subn(f"[removido: {tipo}]", texto)
        if quantidade:
            removidos[tipo] += quantidade
    return texto, dict(removidos)


# ---------------------------------------------------------------- RF-IA-02, RF-IA-03, RF-IA-05

class UsoIA(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    pedido_em: datetime = Field(default_factory=_agora)
    tarefa: str
    descricao: str
    motor: str
    dados: list[str] = Field(default_factory=list)          # resumo do que vai no prompt
    removidos: dict[str, int] = Field(default_factory=dict)  # o que o filtro tirou (RF-IA-04)
    caracteres: int = 0
    autorizacao: Literal["aprovado", "pendente", "descartado"] = "pendente"
    autorizado_em: datetime | None = None
    nome_arquivo: str                                        # relativo a data/saidas
    arquivo_prompt: str | None = None
    resultado: str | None = None
    prompt_pendente: str | None = None                       # guardado só enquanto pendente
    recusado_por_limite: bool = False                        # RF-IA-07
    substitui: str | None = None                             # uso recusado que este refaz em outro motor


class UsosIA(BaseModel):
    itens: list[UsoIA] = Field(default_factory=list)
    limites: dict[str, datetime] = Field(default_factory=dict)  # motor → quando recusou por limite (RF-IA-07)

    def buscar(self, id_: str) -> UsoIA:
        for uso in self.itens:
            if uso.id == id_:
                return uso
        raise ValueError(f"Uso de IA {id_!r} não existe no registro.")

    def pendentes(self) -> list[UsoIA]:
        return [u for u in self.itens if u.autorizacao == "pendente"]


def carregar_usos() -> UsosIA:
    caminho = diretorio_dados() / ARQUIVO_USOS
    if not caminho.is_file():
        return UsosIA()
    return UsosIA.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_usos(usos: UsosIA) -> Path:
    caminho = diretorio_dados() / ARQUIVO_USOS
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(usos.model_dump_json(indent=2), encoding="utf-8")
    return caminho


def _escrever_prompt(nome_arquivo: str, prompt: str) -> Path:
    destino = diretorio_dados() / "saidas" / nome_arquivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(prompt, encoding="utf-8")
    return destino


def trocar_motor_no_prompt(prompt: str, nome_arquivo: str, antigo: str, novo: str) -> tuple[str, str]:
    """Ajusta o rodapé ('para o motor X') e o nome do arquivo ao trocar de motor."""
    prompt = prompt.replace(f"para o motor {antigo}", f"para o motor {novo}")
    nome_arquivo = nome_arquivo.replace(f"-{antigo}.", f"-{novo}.")
    return prompt, nome_arquivo


def registrar_pedido(
    usos: UsosIA,
    *,
    tarefa: str,
    descricao: str,
    motor: str,
    dados: list[str],
    prompt: str,
    removidos: dict[str, int],
    nome_arquivo: str,
    autorizado: bool,
    substitui: str | None = None,
) -> UsoIA:
    """Registra o pedido; se autorizado, gera o prompt, senão deixa pendente sem gerar nada."""
    uso = UsoIA(
        tarefa=tarefa, descricao=descricao, motor=motor, dados=dados, removidos=removidos,
        caracteres=len(prompt), nome_arquivo=nome_arquivo, substitui=substitui,
    )
    if autorizado:
        uso.autorizacao = "aprovado"
        uso.autorizado_em = _agora()
        uso.arquivo_prompt = str(_escrever_prompt(nome_arquivo, prompt))
        uso.resultado = "prompt gerado"
    else:
        uso.prompt_pendente = prompt
        uso.resultado = "negado no pedido; pendente na fila, nada foi gerado"
    usos.itens.append(uso)
    return uso


def autorizar_pendente(usos: UsosIA, id_: str, motor: str | None = None) -> UsoIA:
    uso = usos.buscar(id_)
    if uso.autorizacao != "pendente" or uso.prompt_pendente is None:
        raise ValueError(f"O uso {id_} não está pendente (status: {uso.autorizacao}).")
    prompt = uso.prompt_pendente
    if motor and motor != uso.motor:
        if motor not in MOTORES_EXTERNOS:
            raise ValueError(f"Motor inválido: {motor!r}. Use claude ou gemini.")
        prompt, uso.nome_arquivo = trocar_motor_no_prompt(prompt, uso.nome_arquivo, uso.motor, motor)
        uso.motor = motor
    uso.autorizacao = "aprovado"
    uso.autorizado_em = _agora()
    uso.arquivo_prompt = str(_escrever_prompt(uso.nome_arquivo, prompt))
    uso.prompt_pendente = None
    uso.resultado = "prompt gerado a partir da fila"
    return uso


def descartar_pendente(usos: UsosIA, id_: str) -> UsoIA:
    uso = usos.buscar(id_)
    if uso.autorizacao != "pendente":
        raise ValueError(f"O uso {id_} não está pendente (status: {uso.autorizacao}).")
    uso.autorizacao = "descartado"
    uso.prompt_pendente = None
    uso.resultado = "descartado na fila; nada foi gerado"
    return uso


# ---------------------------------------------------------------- RF-IA-06

NOMES_AUTORIA = {"claude": "Claude Pro", "gemini": "Gemini Pro", "usuario": "você", "local": "agente (motor local)"}


def autoria(motor: str | None) -> str:
    """Quem escreveu um texto: Claude Pro, Gemini Pro, você ou o motor local do agente (RF-IA-06)."""
    return NOMES_AUTORIA.get(motor or "local", motor or "agente (motor local)")


# ---------------------------------------------------------------- RF-IA-07

HORAS_LIMITE = 5  # por quanto tempo um motor que recusou por limite deixa de ser o proposto
_PADRAO_LIMITE = re.compile(
    r"usage limit|message limit|rate limit|reached (your|the) (daily |usage |message )?limit|out of (free )?messages"
    r"|limite de (uso|mensagens)|atingiu o limite|alcan[cç]ou o limite|quota (exceeded|excedida)|cota (excedida|esgotada)"
    r"|try again (after|later|in)|tente novamente (mais tarde|ap[oó]s|em)",
    re.IGNORECASE,
)
TAMANHO_MAXIMO_RECUSA = 600  # recusas são mensagens curtas; texto longo é resposta de verdade


def resposta_e_recusa_por_limite(texto: str) -> bool:
    texto = (texto or "").strip()
    return 0 < len(texto) <= TAMANHO_MAXIMO_RECUSA and bool(_PADRAO_LIMITE.search(texto))


def registrar_recusa(usos: UsosIA, id_: str) -> UsoIA:
    uso = usos.buscar(id_)
    if uso.autorizacao != "aprovado":
        raise ValueError(f"O uso {id_} não foi enviado (status: {uso.autorizacao}); não há recusa a registrar.")
    uso.recusado_por_limite = True
    uso.resultado = "recusado pelo motor: limite de uso da assinatura"
    usos.limites[uso.motor] = _agora()
    return uso


def motor_em_limite(usos: UsosIA, motor: str, agora: datetime | None = None, horas: int = HORAS_LIMITE) -> datetime | None:
    quando = usos.limites.get(motor)
    agora = agora or _agora()
    if quando and (agora - quando).total_seconds() < horas * 3600:
        return quando
    return None


def sugerir_motor(usos: UsosIA, motor: str, agora: datetime | None = None) -> tuple[str, str | None]:
    """Motor a propor e o aviso: troca para o outro se o pedido bateu no limite há pouco."""
    if motor not in MOTORES_EXTERNOS or not motor_em_limite(usos, motor, agora):
        return motor, None
    outro = outro_motor(motor)
    quando = usos.limites[motor]
    if motor_em_limite(usos, outro, agora):
        return motor, (f"Claude e Gemini recusaram por limite nas últimas {HORAS_LIMITE} h; "
                       "se negar, a tarefa segue no motor local e o pedido fica na fila.")
    return outro, (f"O {motor.capitalize()} recusou por limite de uso em {quando:%d/%m %H:%M} UTC; "
                   f"proponho o {outro.capitalize()} (você pode trocar de volta).")


def prompt_para_outro_motor(usos: UsosIA, id_: str, novo_motor: str) -> tuple[str, str]:
    """Prompt e arquivo de um uso recusado, ajustados para o outro motor (exige nova autorização)."""
    uso = usos.buscar(id_)
    if novo_motor not in MOTORES_EXTERNOS or novo_motor == uso.motor:
        raise ValueError(f"Escolha o outro motor ({outro_motor(uso.motor)}).")
    if not uso.arquivo_prompt or not Path(uso.arquivo_prompt).is_file():
        raise ValueError(f"O prompt do uso {id_} não está mais em disco; gere o pedido de novo pelo comando da tarefa.")
    prompt = Path(uso.arquivo_prompt).read_text(encoding="utf-8")
    return trocar_motor_no_prompt(prompt, uso.nome_arquivo, uso.motor, novo_motor)


def ultimo_aprovado(usos: UsosIA, tarefa: str, motor: str) -> UsoIA | None:
    return next((u for u in reversed(usos.itens)
                 if u.tarefa == tarefa and u.motor == motor and u.autorizacao == "aprovado"), None)


def registrar_resultado(usos: UsosIA, tarefa: str, motor: str, resultado: str) -> UsoIA | None:
    """Anota o resultado no uso aprovado mais recente daquela tarefa e motor (RF-IA-05)."""
    for uso in reversed(usos.itens):
        if uso.tarefa == tarefa and uso.motor == motor and uso.autorizacao == "aprovado":
            uso.resultado = resultado
            return uso
    return None
