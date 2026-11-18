"""Banco de respostas-padrão aprovadas (RF-CA-02, Anexo C).

O usuário preenche cada resposta uma vez; o agente reutiliza nas candidaturas
e cadastros e nunca inventa uma resposta que falte (RN-09): sem resposta
aprovada, a pergunta fica para o usuário.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .arquivos import gravar_modelo, ler_modelo
from .storage import diretorio_dados

ARQUIVO = "respostas-padrao.json"

# Perguntas do Anexo C: chave → (pergunta, como o agente usa).
PERGUNTAS: dict[str, tuple[str, str]] = {
    "pretensao_estagio": ("Pretensão salarial (estágio)", "Só informa valores desta faixa (RN-09)"),
    "pretensao_clt": ("Pretensão salarial (CLT)", "Só informa valores desta faixa (RN-09)"),
    "pretensao_pj": ("Pretensão salarial (PJ)", "Só informa valores desta faixa (RN-09)"),
    "disponibilidade_inicio": ("Disponibilidade para início", "Preenche datas de início"),
    "modelos_aceitos": ("Modelos de trabalho aceitos", "Filtra vagas e responde triagens"),
    "mudar_cidade": ("Aceita mudar de cidade? Para onde?", "Filtro eliminatório (RF-VG-07)"),
    "viagens": ("Disponibilidade para viagens", "Responde triagens"),
    "carga_horaria": ("Carga horária possível", "Em estágio, respeita 6 h/dia e 30 h/semana (RN-07)"),
    "conclusao_curso": ("Data prevista de conclusão do curso", "Elegibilidade para estágio (RN-07)"),
    "ingles": ("Nível de inglês (leitura, escrita, conversação)", "Filtro e campo Idiomas"),
    "cnh": ("CNH e categoria", "Responde triagens"),
    "diversidade": ("Perguntas de diversidade (opcionais)", "Preenche só o que você autorizar"),
    "apresentacao_60s": ("Apresentação de 60 segundos", "Base do campo 'Apresente-se' e das mensagens"),
    "por_que_empresa": ("Por que esta empresa? (modelo)", "Adaptada por vaga, com aprovação"),
    "maior_desafio": ("Maior desafio técnico e como resolveu", "Respostas abertas e preparação de entrevistas"),
    "links": ("Links: GitHub, portfólio, LinkedIn", "Todos os cadastros"),
    "referencias": ("Referências (com autorização delas)", "Só quando a vaga pedir"),
}

# Reconhecimento de perguntas de formulários (texto livre → chave do Anexo C).
PADROES: list[tuple[str, str]] = [
    ("pretensao", r"pretens[aã]o|sal[aá]rio|remunera[cç][aã]o|bolsa.*(valor|quanto)|expectativa salarial"),
    ("disponibilidade_inicio", r"quando (pode|poderia) (come[cç]ar|iniciar)|disponibilidade (para|de) in[ií]cio|data de in[ií]cio"),
    ("mudar_cidade", r"mudar de cidade|mudan[cç]a|reloca|outra cidade|relocation"),
    ("viagens", r"viage[mn]|viajar"),
    ("carga_horaria", r"carga hor[aá]ria|horas (por|semanais|di[aá]rias)|turno|hor[aá]rio dispon"),
    ("conclusao_curso", r"conclus[aã]o|formatura|previs[aã]o de t[eé]rmino|semestre|per[ií]odo (do curso|atual)"),
    ("ingles", r"ingl[eê]s|english"),
    ("cnh", r"\bcnh\b|habilita[cç][aã]o|carteira de motorista"),
    ("diversidade", r"g[eê]nero|ra[cç]a|\bcor\b|etnia|pcd|defici[eê]ncia|orienta[cç][aã]o sexual|identidade"),
    ("por_que_empresa", r"por ?que.*(quer|deseja|gostaria|escolheu).*(empresa|trabalhar|n[oó]s|aqui)|por ?que esta|motiva[cç][aã]o"),
    ("maior_desafio", r"desafio|problema dif[ií]cil|situa[cç][aã]o dif[ií]cil"),
    ("apresentacao_60s", r"apresente-se|fale (um pouco )?sobre (voc[eê]|si)|conte sobre voc[eê]|quem [eé] voc[eê]"),
    ("links", r"linkedin|github|portf[oó]lio"),
    ("referencias", r"refer[eê]ncia"),
    ("modelos_aceitos", r"presencial|h[ií]brido|remoto|home office|modelo de trabalho"),
]


class RespostaPadrao(BaseModel):
    chave: str
    resposta: str
    aprovada_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valida_ate: date | None = None


class BancoRespostas(BaseModel):
    itens: dict[str, RespostaPadrao] = Field(default_factory=dict)

    def resposta(self, chave: str, hoje: date | None = None) -> str | None:
        item = self.itens.get(chave)
        if item is None or (item.valida_ate and item.valida_ate < (hoje or date.today())):
            return None
        return item.resposta


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def chave_da_pergunta(texto: str, tipo_contrato: str | None = None) -> str | None:
    """Reconhece de que pergunta do Anexo C se trata (pretensão vira a da modalidade da vaga)."""
    t = _norm(texto)
    for chave, padrao in PADROES:
        if re.search(_norm(padrao), t):
            if chave == "pretensao":
                return {"estagio": "pretensao_estagio", "pj": "pretensao_pj"}.get(tipo_contrato or "", "pretensao_clt")
            return chave
    return None


def definir_resposta(banco: BancoRespostas, chave: str, resposta: str, valida_ate: date | None = None) -> None:
    if chave not in PERGUNTAS:
        raise ValueError(f"Pergunta desconhecida: {chave!r}. Use: {', '.join(PERGUNTAS)}.")
    if not resposta.strip():
        raise ValueError("A resposta não pode ficar vazia; para apagar, use 'agente respostas remover'.")
    banco.itens[chave] = RespostaPadrao(chave=chave, resposta=resposta.strip(), valida_ate=valida_ate)


def carregar_respostas() -> BancoRespostas:
    caminho = diretorio_dados() / ARQUIVO
    return ler_modelo(caminho, BancoRespostas)


def salvar_respostas(banco: BancoRespostas) -> Path:
    caminho = diretorio_dados() / ARQUIVO
    gravar_modelo(caminho, banco)
    return caminho
