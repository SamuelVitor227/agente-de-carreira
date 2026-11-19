"""Filtros eliminatórios, regras de estágio, indícios de golpe e expiração.

RF-VG-07 (filtros), RF-VG-08 (golpe), RF-VG-12 (expiradas), RF-VG-13 e RN-07
(estágio), RN-12 (vaga com indício de golpe não é recomendada) e RNF-04 (texto
da vaga é dado: instruções embutidas são ignoradas e registradas).
"""

from __future__ import annotations

import calendar
import re
from datetime import date

from ..models import PerfilMestre
from .extracao import NOMES_NIVEL_IDIOMA, nivel_idioma
from .modelos import BuscaSalva, ConfigVagas, Sinal, VagaEncontrada
from .texto import casa_cargo, norm, slug

LIMITE_ESTAGIO_DIA = 6       # Lei 11.788/2008, art. 10, II
LIMITE_ESTAGIO_SEMANA = 30
TETO_SALARIO = {"estagio": 6000.0, "trainee": 15000.0, "junior": 15000.0}
TETO_SALARIO_PADRAO = 60000.0
EMPRESAS_SEM_ID = {
    "confidencial", "empresaconfidencial", "sigilosa", "sigiloso", "empresasigilosa", "naoinformado",
    "naoinformada", "naodivulgado", "naodivulgada",
}
CIDADES_GENERICAS = {"brasil", "brazil", "remoto", "remote", ""}

PADROES_GOLPE: list[tuple[str, str, re.Pattern[str]]] = [
    ("golpe:taxa", "cobra taxa do candidato", re.compile(
        r"taxa\s+(de\s+)?(inscri[cç][aã]o|cadastro|matr[ií]cula|treinamento|uniforme|ades[aã]o|administrativa)"
        r"|pag(ar|amento\s+de|ue)\s+(uma\s+)?taxa|investimento\s+inicial|dep[oó]sito\s+(antecipado|inicial|de\s+garantia)"
        r"|compra\s+(obrigat[oó]ria\s+)?do\s+kit|kit\s+inicial", re.I)),
    # Só o pedido conta: "experiência com APIs de Pix" numa vaga de fintech não é golpe.
    ("golpe:pix", "pede Pix ou dados bancários", re.compile(
        r"(envi[ea]r?|fa[cç]a|fazer|pague|pagar|transfir[ae]|transferir|deposite|depositar)\s+(um\s+|o\s+|seu\s+|sua\s+|via\s+)?pix"
        r"|chave\s+pix|pix\s+(para|de)\s+(garantir|reservar|confirmar)|dados\s+banc[aá]rios"
        r"|n[uú]mero\s+da\s+(sua\s+)?conta|ag[eê]ncia\s+e\s+conta|senha\s+do\s+(banco|cart[aã]o)", re.I)),
    ("golpe:renda", "promete ganho fácil", re.compile(
        r"renda\s+extra|ganhe\s+(at[eé]\s+)?r\$\s*[\d.,]+\s*(por\s+dia|/\s*dia|di[aá]ri[oa]s?|por\s+hora)"
        r"|ganhos?\s+ilimitados?|trabalhe\s+de\s+casa\s+e\s+ganhe", re.I)),
    ("golpe:app", "contato só por aplicativo de mensagem", re.compile(
        r"(somente|apenas|s[oó]|exclusivamente)\s+(pelo|por|via|no)\s+(whats\s?app|zap|telegram)"
        r"|curr[ií]culo\s+(pelo|via|no)\s+(whats\s?app|telegram)|chame\s+no\s+(whats|zap|telegram)", re.I)),
]

PADRAO_INJECAO = re.compile(
    r"ignor(e|ar|em|ando)\s+(todas\s+)?(as\s+|suas\s+|os\s+|the\s+|all\s+|any\s+|previous\s+|prior\s+|your\s+)*"
    r"(instru[cç][oõ]es|regras|comandos|instructions|rules|prompts?)"
    r"|disregard\s+(all|any|previous|prior|the|your)|system\s+prompt|novas?\s+instru[cç][oõ]es\s*:|new\s+instructions\s*:"
    r"|voc[eê]\s+(agora\s+)?[eé]\s+(um|uma)\s+(assistente|ia|modelo|bot)|you\s+are\s+now\s+"
    r"|envi[ea]\s+(seus|os|todos\s+os)\s+dados|send\s+(me\s+)?(your|the|all)\s+(data|credentials|passwords?|personal)",
    re.I,
)

PADRAO_ENCERRADA = re.compile(
    r"vaga\s+(foi\s+|est[aá]\s+)?(encerrada|fechada|preenchida|expirada)|n[aã]o\s+(est[aá]\s+mais|se\s+encontra)\s+dispon[ií]vel"
    r"|inscri[cç][oõ]es\s+encerradas|processo\s+(seletivo\s+)?encerrado|no\s+longer\s+(accepting|available)"
    r"|this\s+job\s+(is\s+)?closed|n[aã]o\s+aceita\s+mais\s+candidaturas|candidaturas\s+encerradas"
    r"|(esta\s+)?vaga\s+expirou|this\s+job\s+has\s+expired|job\s+(posting\s+)?(has\s+)?expired",
    re.I,
)


# ---------------------------------------------------------------- RF-VG-08 e RNF-04

def sinais_risco(vaga: VagaEncontrada) -> list[Sinal]:
    texto = f"{vaga.titulo}\n{vaga.descricao}"
    sinais = [Sinal(tipo=tipo, mensagem=mensagem) for tipo, mensagem, padrao in PADROES_GOLPE if padrao.search(texto)]
    teto = TETO_SALARIO.get(vaga.nivel or "", TETO_SALARIO_PADRAO)
    if vaga.salario_max and vaga.salario_max > teto:
        valor = f"{vaga.salario_max:,.0f}".replace(",", ".")
        sinais.append(Sinal(tipo="golpe:salario", mensagem=f"salário de R$ {valor} fora da realidade para {vaga.nivel or 'a vaga'}"))
    if not vaga.empresa or slug(vaga.empresa) in EMPRESAS_SEM_ID:
        sinais.append(Sinal(tipo="golpe:empresa", mensagem="empresa sem identificação", gravidade="atencao"))
    if PADRAO_INJECAO.search(texto):
        sinais.append(Sinal(
            tipo="injecao",
            mensagem="o texto da vaga traz instruções embutidas; foi tratado só como dado e registrado (RNF-04)",
        ))
    return sinais


# ---------------------------------------------------------------- RF-VG-13 e RN-07

def fim_previsto(texto: str | None) -> date | None:
    """Data de conclusão a partir de '2026/2', '12/2026' ou '2026'."""
    t = (texto or "").strip()
    if m := re.fullmatch(r"(\d{4})\s*[/.-]\s*([12])", t):
        ano, semestre = int(m.group(1)), int(m.group(2))
        return date(ano, 7, 31) if semestre == 1 else date(ano, 12, 31)
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", t):
        mes, ano = int(m.group(1)), int(m.group(2))
        if 1 <= mes <= 12:
            return date(ano, mes, calendar.monthrange(ano, mes)[1])
    if m := re.fullmatch(r"(\d{4})", t):
        return date(int(m.group(1)), 12, 31)
    return None


def matricula_ativa(perfil: PerfilMestre, hoje: date) -> bool:
    """Há formação em andamento cuja conclusão prevista ainda não passou (RN-07)."""
    for formacao in perfil.formacao:
        status = norm(formacao.status)
        if not any(s in status for s in ("cursando", "andamento", "matriculad")):
            continue
        fim = fim_previsto(formacao.conclusao_prevista) or formacao.conclusao
        if fim and hoje > fim:
            continue
        return True
    return False


def eh_estagio(vaga: VagaEncontrada) -> bool:
    return vaga.nivel == "estagio" or vaga.contrato == "estagio"


# ---------------------------------------------------------------- vagas exclusivas ou afirmativas

# O texto chega sem acentos e em minúsculas (norm): "às" vira "as".
_EXCLUSIVA = r"(?:exclusiv[ao]s?|afirmativ[ao]s?|somente|apenas|destinad[ao]s?|reservad[ao]s?)\s+(?:para|a|as|aos)\s+"
PUBLICOS_EXCLUSIVOS = [
    ("pcd", "pessoas com deficiência (PcD)",
     re.compile(_EXCLUSIVA + r"(?:pessoas?\s+com\s+deficiencia|pcds?)\b|\bvagas?\s+(?:para\s+)?pcds?\b")),
    ("mulheres", "mulheres", re.compile(_EXCLUSIVA + r"(?:pessoas\s+que\s+se\s+identificam\s+como\s+)?mulheres\b")),
    ("pessoas-negras", "pessoas negras", re.compile(_EXCLUSIVA + r"(?:pessoas\s+)?(?:negras|pretas)\b")),
    ("50-mais", "pessoas com 50 anos ou mais", re.compile(_EXCLUSIVA + r"(?:pessoas\s+)?(?:50\s*\+|acima\s+de\s+50)")),
    ("lgbt", "pessoas LGBTQIAPN+", re.compile(_EXCLUSIVA + r"(?:pessoas\s+)?(?:lgbt\w*|trans)\b")),
]


def sinais_exclusiva(vaga: VagaEncontrada) -> list[Sinal]:
    """Anúncio exclusivo ou afirmativo (ex.: "Desenvolvedor .NET - PcD"): só um aviso, para você decidir.

    O agente não guarda nada sobre você a esse respeito: ele só mostra o que o anúncio diz.
    """
    titulo, descricao = norm(vaga.titulo), norm(vaga.descricao)
    sinais = []
    for tipo, publico, padrao in PUBLICOS_EXCLUSIVOS:
        no_titulo = tipo == "pcd" and re.search(r"\bpcds?\b", titulo)
        if no_titulo or padrao.search(titulo) or padrao.search(descricao):
            sinais.append(Sinal(tipo=f"exclusiva:{tipo}", gravidade="atencao",
                                mensagem=f"anúncio exclusivo ou afirmativo para {publico}: confira se a vaga é para você"))
    return sinais


def sinais_estagio(vaga: VagaEncontrada) -> list[Sinal]:
    if not eh_estagio(vaga):
        return []
    excessos = []
    if vaga.horas_dia and vaga.horas_dia > LIMITE_ESTAGIO_DIA:
        excessos.append(f"{vaga.horas_dia}h por dia")
    if vaga.horas_semana and vaga.horas_semana > LIMITE_ESTAGIO_SEMANA:
        excessos.append(f"{vaga.horas_semana}h por semana")
    if not excessos:
        return []
    return [Sinal(
        tipo="estagio:jornada",
        mensagem=f"jornada de {' e '.join(excessos)} acima do limite do estágio "
                 "(6h/dia e 30h/semana — Lei 11.788, art. 10)",
        gravidade="atencao",
    )]


# ---------------------------------------------------------------- RF-VG-07

_REGIAO_BH_TEXTO = ("regiao metropolitana de belo horizonte", "grande belo horizonte", "grande bh", "rmbh")


def na_regiao(local: str, localidades: list[str]) -> bool:
    texto = norm(local)
    if any(r in texto for r in _REGIAO_BH_TEXTO) and any(slug(l) == "belohorizonte" for l in localidades):
        return True
    cidade = local.split(",")[0].split(" - ")[0].split("(")[0]
    cidade = re.sub(r"\s+e\s+regi[aã]o\b.*$", "", cidade, flags=re.I)  # "Belo Horizonte e Região"
    cidade = slug(cidade)
    if cidade in CIDADES_GENERICAS:
        return True
    if cidade == "bh":
        cidade = "belohorizonte"
    return any(slug(l) == cidade for l in localidades)


def nivel_no_perfil(perfil: PerfilMestre, idioma: str) -> int:
    for registro in perfil.idiomas:
        nome = norm(registro.idioma)
        if (idioma == "ingles" and ("ingl" in nome or "english" in nome)) or (
            idioma == "espanhol" and ("espanh" in nome or "spanish" in nome)
        ):
            return nivel_idioma(registro.nivel) or 1
    return 0


def _motivos_da_busca(vaga: VagaEncontrada, busca: BuscaSalva, perfil: PerfilMestre) -> list[str]:
    motivos: list[str] = []
    if vaga.nivel and vaga.nivel not in busca.niveis:
        motivos.append(f"nível {vaga.nivel} fora da busca")
    if vaga.modelo and vaga.modelo not in busca.modelos:
        motivos.append(f"modelo {vaga.modelo} fora da busca")
    if vaga.contrato and vaga.contrato not in busca.contratos:
        motivos.append(f"contrato {vaga.contrato} fora da busca")
    if busca.salario_minimo and vaga.salario_max and vaga.salario_max < busca.salario_minimo:
        motivos.append(f"salário abaixo do mínimo de R$ {busca.salario_minimo:,.0f}".replace(",", "."))
    if vaga.idioma and vaga.idioma not in busca.idiomas:
        motivos.append(f"anúncio em {vaga.idioma}, fora dos idiomas da busca")
    if vaga.anos_experiencia and vaga.anos_experiencia > busca.limite_anos_experiencia:
        motivos.append(f"exige {vaga.anos_experiencia} anos de experiência (limite: {busca.limite_anos_experiencia})")
    # Sem modelo informado, a vaga conta como presencial (o caso mais comum).
    if vaga.modelo != "remoto" and vaga.local and not na_regiao(vaga.local, busca.localidades):
        motivos.append(f"{vaga.modelo or 'presencial'} em {vaga.local}, fora da região")
    if vaga.modelo in ("presencial", "hibrido") and not vaga.local:
        motivos.append(f"{vaga.modelo} sem local informado (confira na vaga)")
    if vaga.modelo == "remoto" and not busca.remoto_brasil:
        motivos.append("remoto fora da busca")
    for idioma, exigido in vaga.idiomas_exigidos.items():
        dominado = nivel_no_perfil(perfil, idioma)
        if dominado < exigido:
            motivos.append(
                f"exige {idioma} {NOMES_NIVEL_IDIOMA[exigido]}; no seu perfil: {NOMES_NIVEL_IDIOMA[dominado]}"
            )
    return motivos


def avaliar_filtros(
    vaga: VagaEncontrada, config: ConfigVagas, perfil: PerfilMestre, hoje: date
) -> tuple[str | None, list[str]]:
    """Busca que a vaga atende e motivos de eliminação (lista vazia = elegível)."""
    gerais: list[str] = []
    if vaga.empresa and slug(vaga.empresa) in config.bloqueadas():
        gerais.append("empresa bloqueada")
    if eh_estagio(vaga) and not matricula_ativa(perfil, hoje):
        gerais.append("estágio sem matrícula ativa — registre a formação como 'cursando' com a conclusão prevista (RN-07)")
    if not config.buscas:
        return None, gerais

    candidatas = [b for b in config.buscas if casa_cargo(vaga.titulo, b.cargos_efetivos())]
    if not candidatas:
        return None, gerais + ["fora dos cargos das buscas salvas"]
    escolhida, menor = candidatas[0].nome, None
    for busca in candidatas:
        motivos = _motivos_da_busca(vaga, busca, perfil)
        if not motivos:
            return busca.nome, gerais
        if menor is None or len(motivos) < len(menor):
            escolhida, menor = busca.nome, motivos
    return escolhida, gerais + (menor or [])


# ---------------------------------------------------------------- RF-VG-12

def motivo_expiracao(vaga: VagaEncontrada, hoje: date, dias_validade: int) -> str | None:
    if vaga.motivo_expiracao:
        return vaga.motivo_expiracao
    if vaga.valida_ate and vaga.valida_ate < hoje:
        return f"prazo de inscrição encerrado em {vaga.valida_ate:%d/%m/%Y}"
    referencia = vaga.publicada_em or vaga.primeira_coleta.date()
    idade = (hoje - referencia).days
    if idade > dias_validade:
        return f"anunciada há {idade} dias (limite: {dias_validade})"
    if PADRAO_ENCERRADA.search(vaga.descricao):
        return "o anúncio diz que a vaga foi encerrada"
    return None
