"""O que a tela inicial mostra: primeiros passos, próximo passo e números do dia.

Só leitura dos dados locais, em linguagem de quem não é de TI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..candidaturas import ETAPAS_COM_DATA, MOTIVOS_SAIDA, NOMES_ETAPA, ORDEM, SAIDAS, Candidatura, Etapa

FOCOS = {
    "backend-dotnet": "Desenvolvimento back-end (.NET / C#)",
    "cloud-aws": "Nuvem (AWS)",
    "mobile": "Aplicativos (mobile)",
    "dados": "Dados e análise",
    "suporte": "Suporte de TI",
}

SITUACAO_VAGA = {
    "nova": "Nova", "no_resumo": "Recomendada", "salva": "Salva", "descartada": "Descartada",
    "expirada": "Encerrada", "eliminada": "Não combina",
}

# Como a pessoa descreve cada mudança de etapa.
FRASES_ETAPA = {
    Etapa.EM_ANALISE: "Estão analisando meu currículo",
    Etapa.TESTE_TECNICO: "Recebi um teste técnico",
    Etapa.ENTREVISTA_RH: "Marquei entrevista com o RH",
    Etapa.ENTREVISTA_TECNICA: "Marquei entrevista técnica",
    Etapa.PROPOSTA: "Recebi uma proposta",
    Etapa.CONTRATADO: "Fui contratado(a)!",
    Etapa.REPROVADO: "Não passei",
    Etapa.DESISTENCIA: "Desisti do processo",
    Etapa.VAGA_ENCERRADA: "A vaga foi encerrada",
}


@dataclass
class Passo:
    titulo: str
    explicacao: str
    feito: bool
    acao: str


@dataclass
class Proximo:
    titulo: str
    explicacao: str
    acao: str | None
    botao: str | None


@dataclass
class Inicio:
    nome: str | None
    passos: list[Passo]
    proximo: Proximo
    numeros: dict[str, int] = field(default_factory=dict)
    ultima_busca: datetime | None = None


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def primeiros_passos(*, tem_perfil: bool, tem_linkedin: bool, tem_busca: bool, tem_vagas: bool) -> list[Passo]:
    return [
        Passo("Trazer seu currículo", "O agente lê seu currículo (PDF ou Word) e monta seu perfil. Você confere tudo.",
              tem_perfil, "importar_cv"),
        Passo("Conectar seu LinkedIn", "Com o arquivo que o próprio LinkedIn gera. O agente nunca entra na sua conta.",
              tem_linkedin, "conectar_linkedin"),
        Passo("Dizer que vagas você procura", "Área, cidade e tipo de contrato. Dá para mudar quando quiser.",
              tem_busca, "criar_busca"),
        Passo("Fazer a primeira busca de vagas", "O agente procura, dá uma nota para cada vaga e separa as melhores.",
              tem_vagas, "buscar_vagas"),
    ]


def proximo_passo(passos: list[Passo], numeros: dict[str, int], ultima_busca: datetime | None,
                  agora: datetime | None = None) -> Proximo:
    agora = agora or datetime.now(timezone.utc)
    for passo in passos:
        if not passo.feito:
            return Proximo(passo.titulo, passo.explicacao, passo.acao, "Começar")
    if numeros.get("parados"):
        return Proximo("Uma fonte de vagas parou", "Um site mudou ou deu erro. Veja o que aconteceu antes da próxima busca.",
                       "saude", "Ver o problema")
    if numeros.get("lembretes"):
        return Proximo(f"{numeros['lembretes']} lembrete(s) para hoje",
                       "Follow-ups e entrevistas que estão chegando.", "candidaturas", "Ver lembretes")
    if numeros.get("aprovacoes"):
        return Proximo(f"{numeros['aprovacoes']} item(ns) esperando sua aprovação",
                       "Nada é feito sem o seu sim. Leia e aprove ou recuse.", "aprovacoes", "Revisar agora")
    if numeros.get("vagas_boas"):
        return Proximo(f"{numeros['vagas_boas']} vaga(s) boa(s) para você",
                       "Vagas com nota alta em que você ainda não se candidatou.", "vagas", "Ver vagas")
    if ultima_busca is None or agora - _utc(ultima_busca) > timedelta(hours=20):
        return Proximo("Buscar vagas novas", "A última busca já tem mais de um dia.", "buscar_vagas", "Buscar agora")
    return Proximo("Tudo em dia", "Nada pendente agora. Volte amanhã ou acompanhe suas candidaturas.", None, None)


def montar_inicio(dados=None) -> Inicio:
    """Lê tudo do disco (ou de um `relatorios.Dados` já carregado)."""
    from ..funil import vencidos
    from ..linkedin.estado import carregar_estado
    from ..radar.modelos import carregar_config
    from ..relatorios import Dados, foi_aplicada
    from ..storage import perfil_existe

    dados = dados or Dados.carregar()
    tem_perfil = perfil_existe()
    config = carregar_config()
    aplicadas = {c.vaga_id for c in dados.candidaturas.itens if foi_aplicada(c)}
    boas = [v for v in dados.base.itens if v.status in ("nova", "no_resumo", "salva") and v.nota >= config.limiar_alerta
            and not v.risco and v.id not in aplicadas]
    numeros = {
        "vagas_boas": len(boas),
        "em_andamento": sum(1 for c in dados.candidaturas.itens if foi_aplicada(c) and not c.encerrada),
        "lembretes": len(vencidos(dados.lembretes)),
        "aprovacoes": len(dados.fila),
        "parados": sum(1 for a in dados.saude.adaptadores.values() if a.status == "parado"),
    }
    passos = primeiros_passos(tem_perfil=tem_perfil, tem_linkedin=bool(carregar_estado().campos),
                              tem_busca=bool(config.buscas),
                              tem_vagas=bool(dados.base.itens) or dados.base.ultima_rodada is not None)
    nome = dados.perfil.contato.nome.split()[0] if dados.perfil and dados.perfil.contato.nome else None
    return Inicio(nome=nome, passos=passos, proximo=proximo_passo(passos, numeros, dados.base.ultima_rodada),
                  numeros=numeros, ultima_busca=dados.base.ultima_rodada)


# ---------------------------------------------------------------- listas

@dataclass
class LinhaVaga:
    id: str
    nota: int
    titulo: str
    empresa: str
    local: str
    situacao: str
    alerta: bool


def linhas_vagas(base, candidaturas, filtro: str = "recomendadas") -> list[LinhaVaga]:
    from ..relatorios import foi_aplicada

    aplicadas = {c.vaga_id for c in candidaturas.itens if foi_aplicada(c)}
    linhas = []
    for v in base.itens:
        if filtro == "recomendadas" and (v.status not in ("nova", "no_resumo", "salva") or v.risco or v.id in aplicadas):
            continue
        if filtro == "salvas" and v.status != "salva":
            continue
        situacao = "Já me candidatei" if v.id in aplicadas else SITUACAO_VAGA.get(v.status, v.status)
        if v.risco:
            situacao = "Suspeita de golpe"
        linhas.append(LinhaVaga(v.id, v.nota, v.titulo, v.empresa or "—", v.local or "—", situacao, v.risco))
    return sorted(linhas, key=lambda l: (-l.nota, l.titulo))


@dataclass
class LinhaCandidatura:
    id: str
    vaga: str
    empresa: str
    etapa: str
    desde: str
    proximo: str
    encerrada: bool


def linhas_candidaturas(candidaturas, mostrar_encerradas: bool = False) -> list[LinhaCandidatura]:
    linhas = []
    for c in candidaturas.itens:
        if c.encerrada and not mostrar_encerradas:
            continue
        desde = _utc(c.historico[-1].quando if c.historico else c.criada_em).astimezone()
        if c.proxima_etapa_em and not c.encerrada:
            proximo = f"{NOMES_ETAPA[c.status]} em {_utc(c.proxima_etapa_em).astimezone():%d/%m às %H:%M}"
        elif c.motivo_saida:
            proximo = f"Motivo: {c.motivo_saida}"
        else:
            proximo = ""
        avanco = ORDEM.index(c.status) if c.status in ORDEM else -1
        linhas.append((c.encerrada, -avanco, -desde.timestamp(),
                       LinhaCandidatura(c.id, c.vaga_titulo, c.empresa or "—", NOMES_ETAPA[c.status],
                                        f"{desde:%d/%m/%Y}", proximo, c.encerrada)))
    # Em andamento primeiro; dentro delas, as mais avançadas no funil e as mais recentes.
    return [linha for *_, linha in sorted(linhas, key=lambda t: t[:3])]


def proximas_etapas(c: Candidatura) -> list[tuple[Etapa, str]]:
    """O que a pessoa pode dizer que aconteceu, a partir da etapa atual (o funil não volta)."""
    if c.encerrada:
        return []
    atual = ORDEM.index(c.status) if c.status in ORDEM else 0
    avancos = [e for e in ORDEM[max(atual + 1, ORDEM.index(Etapa.EM_ANALISE)):] if e in FRASES_ETAPA]
    if c.status in (Etapa.ENCONTRADA, Etapa.SELECIONADA):
        avancos = []  # antes do envio, o caminho é 'candidatar' ou 'já enviei'
    return [(e, FRASES_ETAPA[e]) for e in avancos] + [(e, FRASES_ETAPA[e]) for e in sorted(SAIDAS, key=lambda e: e.value)]


def pede_data(etapa: Etapa) -> bool:
    return etapa in ETAPAS_COM_DATA


def motivos(etapa: Etapa) -> list[str]:
    return list(MOTIVOS_SAIDA.get(etapa, []))


def data_para_cli(texto: str) -> str | None:
    """'25/11/2026 14:30' (ou '25/11 14h') → '2026-11-25 14:30'; vazio → None; inválido → ValueError."""
    texto = texto.strip().lower().replace("h", ":").replace(" às ", " ").replace(" as ", " ")
    if not texto:
        return None
    partes = texto.split()
    data = partes[0]
    hora = partes[1] if len(partes) > 1 else "09:00"
    if hora.endswith(":"):
        hora += "00"
    dia_mes = data.split("/")
    if len(dia_mes) == 2:
        dia_mes.append(str(datetime.now().year))
    if len(dia_mes) != 3:
        raise ValueError("Use dia/mês/ano, ex.: 25/11/2026 14:30")
    dia, mes, ano = dia_mes
    ano = ano if len(ano) == 4 else f"20{ano}"
    momento = datetime.strptime(f"{ano}-{int(mes):02d}-{int(dia):02d} {hora}", "%Y-%m-%d %H:%M")
    return momento.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- formulário "Que vagas você procura?"

def comandos_busca(respostas: dict, existentes: set[str]) -> tuple[list[list[str]], list[str]]:
    """Uma busca por área marcada, com o nome da área (o agente usa esse nome para escolher o currículo).

    Devolve (comandos 'busca criar', áreas puladas porque já têm busca). ValueError = resposta a corrigir.
    """
    focos = [f for f in respostas.get("focos", []) if f in FOCOS]
    if not focos:
        raise ValueError("Marque pelo menos uma área.")
    if not respostas.get("niveis") or not respostas.get("contratos"):
        raise ValueError("Marque pelo menos um nível e um tipo de contrato.")
    salario = str(respostas.get("salario", "")).replace("R$", "").replace(" ", "").strip()
    if salario:
        salario = salario.replace(".", "").replace(",", ".")
        try:
            float(salario)
        except ValueError:
            raise ValueError("O salário precisa ser só número, ex.: 1500.") from None
    comuns = ["--niveis", ",".join(respostas["niveis"]), "--contratos", ",".join(respostas["contratos"])]
    if str(respostas.get("cidades", "")).strip():
        comuns += ["--localidades", str(respostas["cidades"]).strip()]
    if not respostas.get("remoto", True):
        comuns.append("--sem-remoto")
    if salario:
        comuns += ["--salario-minimo", salario]
    comandos = [["busca", "criar", "--nome", foco, "--foco", foco, *comuns] for foco in focos if foco not in existentes]
    puladas = [FOCOS[f] for f in focos if f in existentes]
    return comandos, puladas
