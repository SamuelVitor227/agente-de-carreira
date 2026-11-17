"""M7: painel (RF-RL-01, RNF-15), relatório semanal (RF-RL-02, UC-11) e exportação (RF-RL-03).

Tudo no motor local, só com os dados que o agente já guarda em data/.
As funções de cálculo recebem os dados prontos; `Dados.carregar()` lê do disco.
"""

from __future__ import annotations

import csv
import html
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .candidaturas import (
    NOMES_ETAPA,
    SAIDAS,
    STATUS_DE_RETORNO,
    Candidatura,
    Candidaturas,
    Etapa,
)
from .radar.modelos import BaseVagas, VagaEncontrada

ENTREVISTAS = {Etapa.ENTREVISTA_RH, Etapa.ENTREVISTA_TECNICA}
PROPOSTAS = {Etapa.PROPOSTA, Etapa.CONTRATADO}
APLICADAS = {Etapa.APLICADA} | STATUS_DE_RETORNO
AMOSTRA_MINIMA = 3          # abaixo disso, "o que funcionou" não tira conclusão
DIAS_SEMANA = 7


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- etapas alcançadas

def alcancou(c: Candidatura, etapas: set[Etapa]) -> bool:
    return c.status in etapas or any(m.para in etapas for m in c.historico)


def foi_aplicada(c: Candidatura) -> bool:
    return c.enviada_em is not None or alcancou(c, APLICADAS)


def teve_retorno(c: Candidatura) -> bool:
    """Qualquer resposta da empresa conta, inclusive a reprovação (menos a por falta de retorno)."""
    if alcancou(c, STATUS_DE_RETORNO):
        return True
    return c.status == Etapa.REPROVADO and c.motivo_saida != "sem retorno"


def _quando_aplicada(c: Candidatura) -> datetime:
    if c.enviada_em:
        return _utc(c.enviada_em)
    mudanca = next((m for m in c.historico if m.para in APLICADAS), None)
    return _utc(mudanca.quando) if mudanca else _utc(c.criada_em)


# ---------------------------------------------------------------- RF-RL-01: painel

@dataclass
class Linha:
    grupo: str
    vagas: int = 0
    candidaturas: int = 0
    retornos: int = 0
    entrevistas: int = 0
    propostas: int = 0

    @property
    def taxa_retorno(self) -> int:
        return round(100 * self.retornos / self.candidaturas) if self.candidaturas else 0

    def somar(self, c: Candidatura) -> None:
        self.candidaturas += 1
        self.retornos += teve_retorno(c)
        self.entrevistas += alcancou(c, ENTREVISTAS)
        self.propostas += alcancou(c, PROPOSTAS)


@dataclass
class Execucao:
    """RNF-15: métricas por rodada e uso de cada motor de IA."""

    rodadas: int = 0
    ultima: datetime | None = None
    coletadas: int = 0
    novas: int = 0
    recomendadas: int = 0
    erros: int = 0
    duracao_media_s: float = 0.0
    uso_ia: dict[str, int] = field(default_factory=dict)
    adaptadores_parados: list[str] = field(default_factory=list)


@dataclass
class Painel:
    desde: datetime | None
    total: Linha
    por_fonte: list[Linha]
    por_foco: list[Linha]
    por_variante: list[Linha]
    funil: dict[str, int]
    motivos_saida: list[tuple[str, int]]
    execucao: Execucao


def fonte_da_vaga(vaga: VagaEncontrada | None) -> str:
    if vaga is None or not vaga.fontes:
        return "manual"
    return vaga.fontes[0].origem


def _fonte_da_candidatura(c: Candidatura, vagas: dict[str, VagaEncontrada]) -> str:
    vaga = vagas.get(c.vaga_id or "")
    if vaga and vaga.fontes:
        return fonte_da_vaga(vaga)
    return c.plataforma or "manual"


def _ordenar(linhas: dict[str, Linha]) -> list[Linha]:
    return sorted(linhas.values(), key=lambda l: (-l.candidaturas, -l.vagas, l.grupo))


def montar_painel(base: BaseVagas, candidaturas: Candidaturas, *, usos_ia=None, saude=None,
                  desde: datetime | None = None) -> Painel:
    desde = _utc(desde) if desde else None
    vagas = {v.id: v for v in base.itens}
    no_periodo = [v for v in base.itens if desde is None or _utc(v.primeira_coleta) >= desde]
    aplicadas = [c for c in candidaturas.itens if foi_aplicada(c) and (desde is None or _quando_aplicada(c) >= desde)]

    total = Linha("total", vagas=len(no_periodo))
    por_fonte: dict[str, Linha] = {}
    por_foco: dict[str, Linha] = {}
    por_variante: dict[str, Linha] = {}
    for v in no_periodo:
        for origem in dict.fromkeys(f.origem for f in v.fontes) or ["manual"]:
            por_fonte.setdefault(origem, Linha(origem)).vagas += 1
        foco = v.busca or "sem busca"
        por_foco.setdefault(foco, Linha(foco)).vagas += 1
    for c in aplicadas:
        total.somar(c)
        fonte = _fonte_da_candidatura(c, vagas)
        por_fonte.setdefault(fonte, Linha(fonte)).somar(c)
        por_foco.setdefault(c.foco, Linha(c.foco)).somar(c)
        por_variante.setdefault(c.variante, Linha(c.variante)).somar(c)

    funil = Counter(NOMES_ETAPA[c.status] for c in candidaturas.itens)
    motivos = Counter(f"{NOMES_ETAPA[c.status]}: {c.motivo_saida}" for c in candidaturas.itens
                      if c.status in SAIDAS and c.motivo_saida and (desde is None or _quando_aplicada(c) >= desde))

    execucao = Execucao()
    rodadas = [r for r in base.rodadas if desde is None or _utc(r.inicio) >= desde]
    if rodadas:
        execucao.rodadas = len(rodadas)
        execucao.ultima = max(_utc(r.fim) for r in rodadas)
        execucao.coletadas = sum(r.coletadas for r in rodadas)
        execucao.novas = sum(r.novas for r in rodadas)
        execucao.recomendadas = sum(r.recomendadas for r in rodadas)
        execucao.erros = sum(r.erros for r in rodadas)
        execucao.duracao_media_s = round(sum(r.duracao_segundos for r in rodadas) / len(rodadas), 1)
    if usos_ia is not None:
        execucao.uso_ia = dict(Counter(u.motor for u in usos_ia.itens if u.autorizacao == "aprovado"
                                       and (desde is None or _utc(u.pedido_em) >= desde)))
    if saude is not None:
        execucao.adaptadores_parados = sorted(n for n, a in saude.adaptadores.items() if a.status == "parado")

    return Painel(desde=desde, total=total, por_fonte=_ordenar(por_fonte), por_foco=_ordenar(por_foco),
                  por_variante=_ordenar(por_variante), funil=dict(funil), motivos_saida=motivos.most_common(),
                  execucao=execucao)


# ---------------------------------------------------------------- RF-RL-02: relatório semanal

@dataclass
class RelatorioSemanal:
    inicio: datetime
    fim: datetime
    semana: Painel
    geral: Painel
    funcionou: list[str]
    lacunas: list[tuple[str, int, int]]          # (competência, vagas que pedem, total de vagas analisadas)
    acoes: list[str]


def _conhecidas(perfil) -> set[str]:
    if perfil is None:
        return set()
    termos = list(perfil.competencias_tecnicas)
    termos += [t for e in perfil.experiencias for t in e.tecnologias]
    termos += [t for p in perfil.projetos for t in p.tecnologias]
    termos += [c.nome for c in perfil.certificacoes]
    return {t.strip().lower() for t in termos}


def competencias_que_faltam(vagas: list[VagaEncontrada], limite: int = 8, perfil=None) -> tuple[list[tuple[str, int]], int]:
    """As lacunas de aderência mais frequentes entre as vagas (pedidas e sem lastro no perfil).

    A lacuna guardada na vaga é de quando ela foi pontuada; o que o perfil atual já tem sai da lista.
    """
    conhecidas = _conhecidas(perfil)
    analisadas = [v for v in vagas if v.aderencia and v.status != "eliminada"]
    contagem = Counter(l for v in analisadas for l in dict.fromkeys(v.aderencia.lacunas) if l.strip().lower() not in conhecidas)
    return contagem.most_common(limite), len(analisadas)


def _o_que_funcionou(geral: Painel) -> list[str]:
    achados = []
    for nome, linhas in (("fonte", geral.por_fonte), ("foco", geral.por_foco), ("variante de CV", geral.por_variante)):
        com_amostra = [l for l in linhas if l.candidaturas >= AMOSTRA_MINIMA]
        if len(com_amostra) < 1:
            continue
        melhor = max(com_amostra, key=lambda l: (l.taxa_retorno, l.candidaturas))
        texto = f"Melhor {nome}: {melhor.grupo} — {melhor.taxa_retorno}% de retorno em {melhor.candidaturas} candidatura(s)"
        if len(com_amostra) > 1:
            pior = min(com_amostra, key=lambda l: (l.taxa_retorno, -l.candidaturas))
            if pior.grupo != melhor.grupo:
                texto += f"; a menor é {pior.grupo} ({pior.taxa_retorno}%)"
        achados.append(texto + ".")
    if not achados:
        achados.append(f"Ainda não há dados para comparar: é preciso pelo menos {AMOSTRA_MINIMA} candidaturas "
                       "enviadas por fonte, foco ou variante.")
    if geral.motivos_saida:
        motivo, vezes = geral.motivos_saida[0]
        achados.append(f"Motivo de saída mais comum: {motivo} ({vezes}x).")
    return achados


def proximas_acoes(*, base: BaseVagas, candidaturas: Candidaturas, lacunas: list[tuple[str, int, int]],
                   lembretes=None, contas=None, fila: list | None = None, parados: list[str] | None = None,
                   followup_dias: int = 7, limiar: int = 80, agora: datetime | None = None) -> list[str]:
    from .funil import vencidos

    agora = agora or _agora()
    acoes: list[str] = []
    if lembretes is not None and (pendentes := vencidos(lembretes, agora)):
        acoes.append(f"Resolver {len(pendentes)} lembrete(s) do funil (follow-ups e etapas): 'agente funil lembretes'.")
    agendadas = [c for c in candidaturas.itens if c.proxima_etapa_em and not c.encerrada
                 and agora <= _utc(c.proxima_etapa_em) <= agora + timedelta(days=DIAS_SEMANA)]
    for c in agendadas:
        acoes.append(f"Preparar {NOMES_ETAPA[c.status].lower()} de {c.vaga_titulo} ({c.empresa or '?'}) em "
                     f"{_utc(c.proxima_etapa_em).astimezone():%d/%m %H:%M}: 'agente funil preparar {c.id}'.")
    paradas = [c for c in candidaturas.itens if c.status == Etapa.APLICADA
               and _quando_aplicada(c) <= agora - timedelta(days=followup_dias * 3)]
    if paradas:
        acoes.append(f"{len(paradas)} candidatura(s) sem retorno há mais de {followup_dias * 3} dias: "
                     "mova para 'reprovado' com motivo 'sem retorno' se não houver mais chance ('agente funil mover').")
    ja_aplicadas = {c.vaga_id for c in candidaturas.itens if foi_aplicada(c)}
    boas = [v for v in base.itens if v.status in ("no_resumo", "salva") and v.nota >= limiar
            and not v.risco and v.id not in ja_aplicadas]
    if boas:
        exemplos = ", ".join(f"{v.id} ({v.titulo})" for v in sorted(boas, key=lambda v: -v.nota)[:3])
        acoes.append(f"{len(boas)} vaga(s) com nota ≥ {limiar} ainda sem candidatura, ex.: {exemplos}: 'agente candidatar ID'.")
    if lacunas:
        termo, n, total = lacunas[0]
        acoes.append(f"Fechar a lacuna mais pedida, {termo} ({n} de {total} vagas): 'agente cv fechar-lacunas'.")
    if contas is not None and (desatualizadas := [p for p, c in contas.itens.items() if c.status == "desatualizado"]):
        acoes.append(f"Atualizar o cadastro em {', '.join(desatualizadas)}: 'agente plataformas propagar'.")
    if fila:
        acoes.append(f"Decidir {len(fila)} item(ns) na fila de aprovações: 'agente fila revisar'.")
    if parados:
        acoes.append(f"Conferir os adaptadores parados ({', '.join(parados)}): 'agente saude'.")
    if not acoes:
        acoes.append("Nada pendente: siga com a rodada diária e o resumo das 8h.")
    return acoes


def relatorio_semanal(base: BaseVagas, candidaturas: Candidaturas, *, agora: datetime | None = None,
                      usos_ia=None, saude=None, lembretes=None, contas=None, fila: list | None = None,
                      followup_dias: int = 7, limiar: int = 80, perfil=None) -> RelatorioSemanal:
    fim = agora or _agora()
    inicio = fim - timedelta(days=DIAS_SEMANA)
    semana = montar_painel(base, candidaturas, usos_ia=usos_ia, saude=saude, desde=inicio)
    geral = montar_painel(base, candidaturas, usos_ia=usos_ia, saude=saude)
    da_semana = [v for v in base.itens if _utc(v.primeira_coleta) >= inicio]
    contagem, total = competencias_que_faltam(da_semana, perfil=perfil)
    if total < 5:  # semana fraca: usa as vagas dos últimos 30 dias para a lista de lacunas
        contagem, total = competencias_que_faltam(
            [v for v in base.itens if _utc(v.primeira_coleta) >= fim - timedelta(days=30)], perfil=perfil)
    lacunas = [(t, n, total) for t, n in contagem]
    acoes = proximas_acoes(base=base, candidaturas=candidaturas, lacunas=lacunas, lembretes=lembretes, contas=contas,
                           fila=fila, parados=geral.execucao.adaptadores_parados, followup_dias=followup_dias,
                           limiar=limiar, agora=fim)
    return RelatorioSemanal(inicio=inicio, fim=fim, semana=semana, geral=geral, funcionou=_o_que_funcionou(geral),
                            lacunas=lacunas, acoes=acoes)


def _tabela_md(titulo: str, linhas: list[Linha]) -> list[str]:
    if not linhas:
        return []
    saida = [f"### {titulo}", "", "| | Vagas | Candidaturas | Retornos | Taxa | Entrevistas | Propostas |",
             "|---|---|---|---|---|---|---|"]
    saida += [f"| {l.grupo} | {l.vagas} | {l.candidaturas} | {l.retornos} | {l.taxa_retorno}% | {l.entrevistas} | {l.propostas} |"
              for l in linhas]
    return saida + [""]


def relatorio_markdown(r: RelatorioSemanal) -> str:
    s, e = r.semana.total, r.semana.execucao
    linhas = [f"# Relatório semanal — {r.inicio.astimezone():%d/%m} a {r.fim.astimezone():%d/%m/%Y}", "",
              "## A semana em números", "",
              f"- Vagas novas: {s.vagas} · recomendadas nas rodadas: {e.recomendadas} · rodadas: {e.rodadas}"
              + (f" ({e.erros} erro(s))" if e.erros else ""),
              f"- Candidaturas enviadas: {s.candidaturas} · retornos: {s.retornos} ({s.taxa_retorno}%) · "
              f"entrevistas: {s.entrevistas} · propostas: {s.propostas}",
              ]
    if e.uso_ia:
        linhas.append("- Uso de IA: " + ", ".join(f"{m} {n}x" for m, n in sorted(e.uso_ia.items())))
    linhas += ["", "## O que funcionou", ""] + [f"- {t}" for t in r.funcionou]
    linhas += ["", "## Competências mais pedidas que faltam no perfil", ""]
    if r.lacunas:
        linhas += [f"- {t}: {n} de {total} vaga(s)" for t, n, total in r.lacunas]
        linhas.append("")
        linhas.append("Só entra no CV o que você tiver de verdade (RN-02): curso, certificação ou projeto primeiro.")
    else:
        linhas.append("- Nenhuma lacuna nas vagas analisadas (ou ainda não há vagas com aderência calculada).")
    linhas += ["", "## Próximas ações sugeridas", ""] + [f"{i}. {a}" for i, a in enumerate(r.acoes, 1)]
    linhas += ["", "## Desde o início", ""]
    linhas += _tabela_md("Por fonte", r.geral.por_fonte)
    linhas += _tabela_md("Por foco", r.geral.por_foco)
    linhas += _tabela_md("Por variante de CV", r.geral.por_variante)
    return "\n".join(linhas).rstrip() + "\n"


# ---------------------------------------------------------------- painel em HTML (RNF-15)

def painel_html(p: Painel, gerado_em: datetime | None = None) -> str:
    """Página estática e autocontida (sem scripts nem recursos externos) em data/painel.html."""
    gerado_em = gerado_em or _agora()
    t, e = p.total, p.execucao
    esc = html.escape

    def tabela(titulo: str, linhas: list[Linha]) -> str:
        if not linhas:
            return ""
        corpo = "".join(
            f"<tr><td>{esc(l.grupo)}</td><td>{l.vagas}</td><td>{l.candidaturas}</td><td>{l.retornos}</td>"
            f"<td>{l.taxa_retorno}%</td><td>{l.entrevistas}</td><td>{l.propostas}</td></tr>" for l in linhas)
        return (f"<h2>{esc(titulo)}</h2><div class='rolagem'><table><thead><tr><th></th><th>Vagas</th><th>Candidaturas</th>"
                f"<th>Retornos</th><th>Taxa</th><th>Entrevistas</th><th>Propostas</th></tr></thead><tbody>{corpo}</tbody></table></div>")

    cartoes = "".join(f"<div class='cartao'><span>{esc(rotulo)}</span><strong>{valor}</strong></div>" for rotulo, valor in (
        ("Vagas encontradas", t.vagas), ("Candidaturas", t.candidaturas), ("Taxa de retorno", f"{t.taxa_retorno}%"),
        ("Entrevistas", t.entrevistas), ("Propostas", t.propostas)))
    funil = "".join(f"<li>{esc(nome)}: <strong>{n}</strong></li>" for nome, n in p.funil.items()) or "<li>Nenhuma candidatura.</li>"
    motivos = "".join(f"<li>{esc(m)}: {n}</li>" for m, n in p.motivos_saida) or "<li>Nenhuma saída registrada.</li>"
    ia = ", ".join(f"{esc(m)} {n}x" for m, n in sorted(e.uso_ia.items())) or "nenhum"
    ultima = e.ultima.astimezone().strftime("%d/%m %H:%M") if e.ultima else "nunca"
    parados = esc(", ".join(e.adaptadores_parados)) if e.adaptadores_parados else "nenhum"
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel do agente</title>
<style>
:root {{ --fundo:#f7f7f5; --texto:#1d1d1b; --suave:#6b6b66; --cartao:#fff; --borda:#e2e2dc; --destaque:#2f6f4f; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fundo:#161615; --texto:#ececea; --suave:#a3a39d; --cartao:#21211f; --borda:#34342f; --destaque:#7cc4a0; }} }}
body {{ margin:0; padding:24px 16px; background:var(--fundo); color:var(--texto); font:15px/1.5 system-ui, sans-serif; }}
main {{ max-width:960px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:28px 0 8px; }}
.suave {{ color:var(--suave); font-size:13px; }}
.cartoes {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-top:16px; }}
.cartao {{ background:var(--cartao); border:1px solid var(--borda); border-radius:8px; padding:12px; }}
.cartao span {{ display:block; color:var(--suave); font-size:13px; }} .cartao strong {{ font-size:24px; color:var(--destaque); }}
.rolagem {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; background:var(--cartao); border:1px solid var(--borda); }}
th, td {{ padding:6px 10px; border-bottom:1px solid var(--borda); text-align:right; white-space:nowrap; }}
th:first-child, td:first-child {{ text-align:left; }} th {{ font-size:13px; color:var(--suave); font-weight:600; }}
ul {{ margin:0; padding-left:20px; }}
</style></head><body><main>
<h1>Painel do agente de carreira</h1>
<p class="suave">Atualizado em {gerado_em.astimezone():%d/%m/%Y %H:%M}{f" · desde {p.desde.astimezone():%d/%m/%Y}" if p.desde else ""}. Gerado pelo agente; só leitura.</p>
<div class="cartoes">{cartoes}</div>
{tabela("Por fonte", p.por_fonte)}{tabela("Por foco", p.por_foco)}{tabela("Por variante de CV", p.por_variante)}
<h2>Funil agora</h2><ul>{funil}</ul>
<h2>Motivos de saída</h2><ul>{motivos}</ul>
<h2>Execução</h2>
<ul><li>Rodadas: {e.rodadas} · última: {ultima} · duração média: {e.duracao_media_s}s</li>
<li>Vagas coletadas: {e.coletadas} · novas: {e.novas} · recomendadas: {e.recomendadas} · erros: {e.erros}</li>
<li>Uso de IA autorizado: {ia}</li><li>Adaptadores parados: {parados}</li></ul>
</main></body></html>
"""


# ---------------------------------------------------------------- RF-RL-03: exportação

def _escrever_csv(caminho: Path, cabecalho: list[str], linhas: list[list[object]]) -> Path:
    # ';' e BOM: o Excel em português abre direto, com acentos e colunas certas.
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(cabecalho)
        escritor.writerows(["" if v is None else v for v in linha] for linha in linhas)
    return caminho


def _data(momento: datetime | None) -> str:
    return _utc(momento).astimezone().strftime("%Y-%m-%d %H:%M") if momento else ""


def exportar(pasta: Path, *, base: BaseVagas, candidaturas: Candidaturas, acoes: list, usos_ia=None,
             contatos=None) -> list[Path]:
    """Gera CSVs (vagas, candidaturas, histórico do funil, log de ações, uso de IA, contatos)."""
    pasta.mkdir(parents=True, exist_ok=True)
    gerados = [
        _escrever_csv(pasta / "vagas.csv",
                      ["id", "titulo", "empresa", "local", "nivel", "contrato", "status", "nota", "busca", "fontes",
                       "primeira_coleta", "link", "sinais", "motivos_eliminacao"],
                      [[v.id, v.titulo, v.empresa, v.local, v.nivel, v.contrato, v.status, v.nota, v.busca,
                        ", ".join(dict.fromkeys(f.origem for f in v.fontes)), _data(v.primeira_coleta), v.link,
                        ", ".join(s.mensagem for s in v.sinais), ", ".join(v.motivos_eliminacao)] for v in base.itens]),
        _escrever_csv(pasta / "candidaturas.csv",
                      ["id", "vaga_id", "vaga", "empresa", "plataforma", "foco", "variante", "idioma", "etapa",
                       "nota_aderencia", "enviada_em", "retorno", "motivo_saida", "detalhe_saida", "proxima_etapa_em", "link"],
                      [[c.id, c.vaga_id, c.vaga_titulo, c.empresa, c.plataforma, c.foco, c.variante, c.idioma,
                        NOMES_ETAPA[c.status], c.nota_aderencia, _data(c.enviada_em), "sim" if teve_retorno(c) else "não",
                        c.motivo_saida, c.detalhe_saida, _data(c.proxima_etapa_em), c.vaga_link] for c in candidaturas.itens]),
        _escrever_csv(pasta / "funil-historico.csv", ["candidatura", "vaga", "quando", "de", "para"],
                      [[c.id, c.vaga_titulo, _data(m.quando), NOMES_ETAPA[m.de] if m.de else "", NOMES_ETAPA[m.para]]
                       for c in candidaturas.itens for m in c.historico]),
        _escrever_csv(pasta / "log-acoes.csv",
                      ["id", "quando", "plataforma", "acao", "alvo", "modo", "resultado", "aprovado_em", "origem_aprovacao",
                       "autoria", "antes", "depois", "captura"],
                      [[a.id, _data(a.quando), a.plataforma, a.acao, a.alvo, a.modo, a.resultado, _data(a.aprovado_em),
                        a.origem_aprovacao, a.autoria, a.antes, a.depois, a.captura] for a in acoes]),
    ]
    if usos_ia is not None:
        gerados.append(_escrever_csv(pasta / "uso-ia.csv",
                                     ["id", "pedido_em", "tarefa", "motor", "autorizacao", "autorizado_em", "caracteres", "lote"],
                                     [[u.id, _data(u.pedido_em), u.tarefa, u.motor, u.autorizacao, _data(u.autorizado_em),
                                       u.caracteres, u.lote] for u in usos_ia.itens]))
    if contatos is not None:
        gerados.append(_escrever_csv(pasta / "contatos.csv", ["id", "nome", "empresa", "cargo", "canal", "candidaturas", "interacoes"],
                                     [[c.id, c.nome, c.empresa, c.cargo, c.canal, ", ".join(c.candidaturas), len(c.interacoes)]
                                      for c in contatos.itens]))
    return gerados


# ---------------------------------------------------------------- leitura do disco

@dataclass
class Dados:
    base: BaseVagas
    candidaturas: Candidaturas
    usos_ia: object
    saude: object
    lembretes: object
    contas: object
    contatos: object
    acoes: list
    fila: list
    perfil: object = None

    @classmethod
    def carregar(cls) -> "Dados":
        from .candidaturas import carregar_candidaturas
        from .funil import carregar_contatos, carregar_lembretes
        from .ia import carregar_usos
        from .operacao.auditoria import listar_acoes
        from .operacao.fila import listar_fila
        from .operacao.saude import carregar_saude
        from .plataformas.contas import carregar_contas
        from .radar.modelos import carregar_base
        from .storage import carregar_perfil, perfil_existe

        return cls(base=carregar_base(), candidaturas=carregar_candidaturas(), usos_ia=carregar_usos(),
                   saude=carregar_saude(), lembretes=carregar_lembretes(), contas=carregar_contas(),
                   contatos=carregar_contatos(), acoes=listar_acoes(), fila=listar_fila(),
                   perfil=carregar_perfil() if perfil_existe() else None)


def salvar_painel_html(destino: Path | None = None) -> Path:
    """Regrava data/painel.html; chamado ao fim de cada rodada (RNF-15)."""
    from .storage import diretorio_dados

    dados = Dados.carregar()
    destino = destino or diretorio_dados() / "painel.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(painel_html(montar_painel(dados.base, dados.candidaturas, usos_ia=dados.usos_ia, saude=dados.saude)),
                       encoding="utf-8")
    return destino
