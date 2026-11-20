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
    busca_automatica: object | None = None  # operacao.agendada.Situacao: texto e se há problema
    fontes_paradas: list[tuple[str, str, str]] = field(default_factory=list)  # (nome do adaptador, nome amigável, erro)
    lembrete_linkedin: str | None = None    # RF-EV-22: faz tempo que o perfil não vem do LinkedIn
    respostas_faltando: list[str] = field(default_factory=list)  # RF-EV-06: perguntas principais sem resposta


NOMES_FONTES = {
    "navegador:linkedin": "LinkedIn (automação)", "email:outlook-web": "Outlook (e-mail pelo navegador)",
    "pagina:gupy-portal": "Portal da Gupy", "navegador:glassdoor": "Glassdoor",
    "assistido:linkedin": "Candidatura simplificada do LinkedIn",
}
DIAS_LEMBRETE_LINKEDIN = 30


def fontes_paradas(saude) -> list[tuple[str, str, str]]:
    """Fontes de vagas paradas por erro ou por mudança no site (RF-EV-17), em linguagem simples."""
    saida = []
    for nome, adaptador in sorted(saude.adaptadores.items()):
        if adaptador.status == "parado":
            amigavel = NOMES_FONTES.get(nome) or (f"Alertas de e-mail: {nome.split(':', 1)[1]}" if nome.startswith("email:")
                                                  else nome)
            saida.append((nome, amigavel, (adaptador.ultimo_erro or "parou depois de falhas seguidas")[:160]))
    return saida


def lembrete_linkedin(sincronizado_em: datetime | None, agora: datetime | None = None) -> str | None:
    if sincronizado_em is None:
        return None
    dias = ((agora or datetime.now(timezone.utc)) - _utc(sincronizado_em)).days
    if dias < DIAS_LEMBRETE_LINKEDIN:
        return None
    return (f"Faz {dias} dias que o seu perfil não é atualizado com os dados do LinkedIn. Baixe o arquivo de novo "
            "(o LinkedIn manda por e-mail) e o agente mostra o que mudou antes de guardar.")


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def primeiros_passos(*, tem_perfil: bool, tem_linkedin: bool, tem_busca: bool, tem_vagas: bool,
                     tem_email: bool = True, tem_agendamento: bool = True) -> list[Passo]:
    return [
        Passo("Trazer seu currículo", "O agente lê seu currículo (PDF ou Word) e monta seu perfil. Você confere tudo.",
              tem_perfil, "importar_cv"),
        Passo("Conectar seu LinkedIn", "Com o arquivo que o próprio LinkedIn gera, sem passar sua senha para o agente.",
              tem_linkedin, "conectar_linkedin"),
        Passo("Dizer que vagas você procura", "Área, cidade e tipo de contrato. Dá para mudar quando quiser.",
              tem_busca, "criar_busca"),
        Passo("Receber vagas do seu e-mail", "O LinkedIn e outros sites mandam alertas de vaga; o agente lê sozinho, "
              "só para ler (nunca apaga nem responde).", tem_email, "email_alertas"),
        Passo("Fazer a primeira busca de vagas", "O agente procura, dá uma nota para cada vaga e separa as melhores.",
              tem_vagas, "buscar_vagas"),
        Passo("Ligar a busca automática todo dia", "Toda manhã o agente busca sozinho e deixa o resumo pronto até as 8h.",
              tem_agendamento, "agendar_busca"),
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
    # "Boas" = valem a candidatura (o limiar de alerta, 80, é para avisar na hora e quase nunca é atingido).
    boas = [v for v in dados.base.itens if v.status in ("nova", "no_resumo", "salva")
            and v.nota >= config.limiar_candidatar and not v.risco and v.id not in aplicadas]
    numeros = {
        "vagas_boas": len(boas),
        "em_andamento": sum(1 for c in dados.candidaturas.itens if foi_aplicada(c) and not c.encerrada),
        "lembretes": len(vencidos(dados.lembretes)),
        "aprovacoes": len(dados.fila),
        "parados": sum(1 for a in dados.saude.adaptadores.values() if a.status == "parado"),
    }
    from ..configuracao import carregar_configuracao
    from ..operacao.credenciais import email_configurado
    from ..radar.agenda import tarefa_agendada

    agendada = tarefa_agendada()
    # O e-mail pode ser lido por IMAP ou pelo Outlook na web, no navegador do agente: os dois contam.
    tem_email = bool(email_configurado()) or carregar_configuracao().email_navegador.ativo
    passos = primeiros_passos(tem_perfil=tem_perfil, tem_linkedin=bool(carregar_estado().campos),
                              tem_busca=bool(config.buscas),
                              tem_vagas=bool(dados.base.itens) or dados.base.ultima_rodada is not None,
                              tem_email=tem_email, tem_agendamento=agendada is not False)
    nome = dados.perfil.contato.nome.split()[0] if dados.perfil and dados.perfil.contato.nome else None
    from ..operacao.agendada import situacao

    estado_linkedin = carregar_estado()
    from ..respostas import ESSENCIAIS, PERGUNTAS, carregar_respostas

    banco = carregar_respostas()
    respostas_faltando = [PERGUNTAS[c][0] for c in ESSENCIAIS if not banco.resposta(c)] if tem_perfil else []
    return Inicio(respostas_faltando=respostas_faltando,nome=nome, passos=passos, proximo=proximo_passo(passos, numeros, dados.base.ultima_rodada),
                  numeros=numeros, ultima_busca=dados.base.ultima_rodada,
                  busca_automatica=situacao(agendada, config.hora_rodada), fontes_paradas=fontes_paradas(dados.saude),
                  lembrete_linkedin=lembrete_linkedin(estado_linkedin.sincronizado_em))


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
    estimada: bool = False           # sem descrição: nota só pelo título
    modelo: str = ""                 # remoto, hibrido, presencial
    nivel: str = ""                  # estagio, trainee, junior...
    encontrada: datetime | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def nota_texto(self) -> str:
        return f"≈{self.nota}" if self.estimada else str(self.nota)


ABAS_VAGAS = (("recomendadas", "Recomendadas"), ("outras", "Outras"), ("salvas", "Salvas"), ("todas", "Todas"))
MODELOS_VAGA = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}
NIVEIS_VAGA = {"estagio": "Estágio", "trainee": "Trainee", "junior": "Júnior"}


def linhas_vagas(base, candidaturas, filtro: str = "recomendadas", limiar: int = 50) -> list[LinhaVaga]:
    """As vagas de cada aba. "Recomendadas" tem nota a partir de `limiar` (o de salvar); "Outras", as abaixo."""
    from ..relatorios import foi_aplicada

    aplicadas = {c.vaga_id for c in candidaturas.itens if foi_aplicada(c)}
    linhas = []
    for v in base.itens:
        ativa = v.status in ("nova", "no_resumo", "salva") and not v.risco and v.id not in aplicadas
        if filtro == "recomendadas" and not (ativa and v.nota >= limiar):
            continue
        if filtro == "outras" and not (ativa and v.nota < limiar):
            continue
        if filtro == "salvas" and v.status != "salva":
            continue
        situacao = "Já me candidatei" if v.id in aplicadas else SITUACAO_VAGA.get(v.status, v.status)
        if v.risco:
            situacao = "Suspeita de golpe"
        linhas.append(LinhaVaga(
            v.id, v.nota, v.titulo, v.empresa or "—", v.local or "—", situacao, v.risco,
            estimada=bool(v.aderencia and v.aderencia.estimada), modelo=v.modelo or "", nivel=v.nivel or "",
            encontrada=v.primeira_coleta, avisos=[s.mensagem for s in v.sinais if s.gravidade != "forte"],
        ))
    return sorted(linhas, key=lambda l: (-l.nota, l.titulo))


CONTRATOS_VAGA = {"clt": "CLT", "pj": "PJ", "estagio": "Estágio"}


def _dinheiro(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


def resumo_da_vaga(vaga) -> str:
    """'Empresa · Local · Presencial · Estágio · R$ 1.297 · encontrada hoje' (sem repetir nível e contrato)."""
    nivel = NIVEIS_VAGA.get(vaga.nivel or "", vaga.nivel)
    contrato = CONTRATOS_VAGA.get(vaga.contrato or "", vaga.contrato)
    salario = None
    if vaga.salario_min:
        salario = _dinheiro(vaga.salario_min)
        if vaga.salario_max and vaga.salario_max != vaga.salario_min:
            salario += f" a {_dinheiro(vaga.salario_max)}"
    partes = [vaga.empresa, vaga.local, MODELOS_VAGA.get(vaga.modelo or ""), nivel,
              contrato if contrato != nivel else None, salario, f"encontrada {quando_encontrada(vaga.primeira_coleta)}"]
    return " · ".join(p for p in partes if p)


def frase_da_nota(nota: int, estimada: bool, limiar_candidatar: int, limiar_salvar: int) -> str:
    if estimada:
        return "estimada só pelo título: o agente ainda não leu a descrição"
    if nota >= limiar_candidatar:
        return "combina bem: vale a candidatura"
    if nota >= limiar_salvar:
        return "combina em parte: vale olhar"
    return "combina pouco com o seu perfil"


def explicar_nota(aderencia) -> list[str]:
    """A nota em linguagem simples: o que você tem, o que falta e se o cargo combina."""
    if aderencia is None:
        return ["O agente ainda não deu nota a esta vaga."]
    linhas = []
    if aderencia.atendidos:
        linhas.append("Você tem: " + ", ".join(aderencia.atendidos[:8]) + ("…" if len(aderencia.atendidos) > 8 else ""))
    if aderencia.lacunas:
        linhas.append("Pede e não está no seu perfil: " + ", ".join(aderencia.lacunas[:8])
                      + ("…" if len(aderencia.lacunas) > 8 else ""))
    if aderencia.faltam_no_cv:
        linhas.append("Você tem, mas não aparece no currículo: " + ", ".join(aderencia.faltam_no_cv[:6]))
    if not aderencia.atendidos and not aderencia.lacunas and not aderencia.estimada:
        linhas.append("O anúncio não cita tecnologias que o agente conheça.")
    if aderencia.encaixe_cargo is not None:
        linhas.append("O cargo e o nível combinam com as suas buscas." if aderencia.encaixe_cargo >= 0.8 else
                      "O cargo e o nível combinam em parte com as suas buscas." if aderencia.encaixe_cargo >= 0.5 else
                      "O cargo e o nível são pouco parecidos com as suas buscas.")
    if "inglês" in (aderencia.justificativa or ""):
        linhas.append("O anúncio é em inglês e o seu inglês está como básico.")
    if aderencia.ajuste_feedback:
        linhas.append(f"Ajuste pelo que você já disse de outras vagas: {aderencia.ajuste_feedback * 100:+.0f} pontos.")
    return linhas


def quando_encontrada(momento: datetime | None, agora: datetime | None = None) -> str:
    if momento is None:
        return "—"
    agora = agora or datetime.now(timezone.utc)
    dias = (_utc(agora).astimezone().date() - _utc(momento).astimezone().date()).days
    return "hoje" if dias <= 0 else "ontem" if dias == 1 else f"há {dias} dias"


def filtrar_linhas(linhas: list[LinhaVaga], texto: str = "", modelo: str = "", nivel: str = "") -> list[LinhaVaga]:
    """Campo "Procurar" (todas as palavras em título, empresa ou local) e os filtros de modelo e nível."""
    from ..radar.texto import norm

    palavras = norm(texto).split()
    saida = []
    for l in linhas:
        alvo = norm(f"{l.titulo} {l.empresa} {l.local}")
        if all(p in alvo for p in palavras) and (not modelo or l.modelo == modelo) and (not nivel or l.nivel == nivel):
            saida.append(l)
    return saida


def ordenar_linhas(linhas: list[LinhaVaga], coluna: str = "nota", decrescente: bool = True) -> list[LinhaVaga]:
    from ..radar.texto import norm

    chaves = {
        "nota": lambda l: l.nota,
        "encontrada": lambda l: _utc(l.encontrada) if l.encontrada else datetime.min.replace(tzinfo=timezone.utc),
    }
    chave = chaves.get(coluna, lambda l: norm(str(getattr(l, coluna, ""))))
    return sorted(linhas, key=chave, reverse=decrescente)


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


# ---------------------------------------------------------------- "Candidatar às melhores"

LOTE_MAXIMO = 5  # candidaturas por vez: cada uma tem revisão e envio feitos por você


def vagas_restantes_hoje(candidaturas, limite_diario: int, hoje=None) -> int:
    """Quantas candidaturas ainda cabem hoje no limite diário (RF-CA-05)."""
    hoje = hoje or datetime.now().astimezone().date()
    enviadas = sum(1 for c in candidaturas.itens if c.enviada_em and _utc(c.enviada_em).astimezone().date() == hoje)
    return max(0, limite_diario - enviadas)


def melhores_para_candidatar(base, candidaturas, nota_minima: int, restantes: int) -> list[LinhaVaga]:
    """As vagas recomendadas de maior nota, sem golpe e sem candidatura enviada, até o que cabe hoje."""
    boas = [l for l in linhas_vagas(base, candidaturas, "recomendadas") if l.nota >= nota_minima and not l.alerta]
    return boas[:max(0, min(restantes, LOTE_MAXIMO))]
