"""Rodada de vagas (RF-VG-03): coleta → extração → deduplicação → triagem → aderência → resumo.

Roda em agenda (padrão 7h) ou sob demanda, sem interação: o que precisa de
autorização (justificativa escrita por IA) fica pendente na fila (RF-IA-03).
Falha numa fonte não interrompe as outras (RNF-07).
"""

from __future__ import annotations

import imaplib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..ia import TAREFAS, carregar_usos, registrar_pedido, salvar_usos, sanitizar, valores_sensiveis
from ..models import PerfilMestre
from ..operacao.saude import RegistroSaude, problema_no_email
from .aderencia import IndiceTFIDF, calcular_aderencia, documento_perfil, documento_vaga
from .coleta import (
    INTERVALO_SEGUNDOS,
    Baixador,
    ColetaErro,
    baixar,
    diagnostico_email,
    dominio_em,
    ler_eml,
    ler_imap,
    robots_permite,
    vaga_de_html,
    vagas_de_email,
    vagas_de_pagina,
)
from .dedup import incorporar, mesclar
from .extracao import analisar_html, extrair_campos, jobpostings
from .filtros import PADRAO_ENCERRADA, avaliar_filtros, motivo_expiracao, sinais_estagio, sinais_risco
from .modelos import BaseVagas, ConfigVagas, Fonte, VagaBruta, VagaEncontrada
from .resumo import (
    Resumo,
    dados_enviados_justificativa,
    marcar_no_resumo,
    montar_resumo,
    prompt_justificativas,
    salvar_alerta,
    salvar_resumo,
    selecionar_alertas,
)

DIAS_IMAP_PRIMEIRA_VEZ = 7
CAMPOS_SEMPRE_DO_TEXTO = (
    "requisitos_obrigatorios", "requisitos_desejaveis", "idiomas_exigidos", "anos_experiencia",
    "horas_dia", "horas_semana", "idioma",
)

Dormir = Callable[[float], None]
PodeLer = Callable[[str], bool]  # modo somente sugestão e modo por plataforma (RF-OP-01, RF-OP-02)


def de_bruta(bruta: VagaBruta) -> VagaEncontrada:
    """Converte o que a fonte entregou numa vaga com todos os campos extraídos (RF-VG-04)."""
    campos = extrair_campos(bruta.titulo, bruta.descricao, bruta.local)
    vaga = VagaEncontrada(
        titulo=bruta.titulo.strip(), empresa=bruta.empresa or None, local=bruta.local, link=bruta.link,
        descricao=bruta.descricao.strip(), publicada_em=bruta.publicada_em, valida_ate=bruta.valida_ate,
        fontes=[Fonte(tipo=bruta.fonte_tipo, origem=bruta.fonte_origem, url=bruta.link)],
        **campos,
    )
    # Dados estruturados da fonte (JSON-LD) valem mais que a leitura do texto.
    vaga.modelo = bruta.modelo or vaga.modelo
    vaga.contrato = bruta.contrato or vaga.contrato
    if bruta.salario_min is not None:
        vaga.salario_min, vaga.salario_max = bruta.salario_min, bruta.salario_max or bruta.salario_min
    return vaga


def reextrair(vaga: VagaEncontrada) -> None:
    """Recalcula os campos depois que a descrição ficou mais completa."""
    for chave, valor in extrair_campos(vaga.titulo, vaga.descricao, vaga.local).items():
        if chave in CAMPOS_SEMPRE_DO_TEXTO or getattr(vaga, chave) in (None, ""):
            setattr(vaga, chave, valor)


# ---------------------------------------------------------------- coleta

def _sempre(url: str) -> bool:
    return True


def coletar(
    config: ConfigVagas, base: BaseVagas, hoje: date, *, pasta_emails: Path | None, imap: dict[str, str] | None,
    imap_factory=imaplib.IMAP4_SSL, baixar_fn: Baixador = baixar, dormir: Dormir = time.sleep, usar_paginas: bool = True,
    saude: RegistroSaude | None = None, pode_ler: PodeLer = _sempre,
) -> tuple[list[VagaBruta], list[str], list[str]]:
    """Devolve (vagas brutas, avisos da coleta, adaptadores que pararam nesta rodada)."""
    saude = saude if saude is not None else RegistroSaude()
    brutas: list[VagaBruta] = []
    erros: list[str] = []
    falhas: list[str] = []

    def ler_mensagem(msg) -> bool:
        """Lê um alerta; False = deixar o e-mail guardado para reprocessar (adaptador parado)."""
        plataforma, links, conhecido = diagnostico_email(msg)
        nome = f"email:{plataforma}"
        if plataforma and not saude.pode_usar(nome):
            erros.append(f"{nome}: adaptador parado; o e-mail ficou guardado (agente saude reativar {nome})")
            return False
        vagas = vagas_de_email(msg)
        if problema := problema_no_email(plataforma, links, len(vagas), conhecido):
            if saude.falha(nome, problema, parar=True):
                falhas.append(f"{nome}: {problema}")
            erros.append(f"{nome}: {problema}; o e-mail ficou guardado para reprocessar")
            return False
        if plataforma:
            saude.sucesso(nome)
        brutas.extend(vagas)
        return True

    if pasta_emails and pasta_emails.is_dir():
        processados = pasta_emails / "processados"
        for caminho in sorted(pasta_emails.glob("*.eml")):
            try:
                msg = ler_eml(caminho)
            except (OSError, ValueError) as erro:
                erros.append(f"e-mail {caminho.name}: {erro}")
                continue
            msgid = (msg.get("Message-ID") or caminho.name).strip()
            if msgid not in base.emails_processados:
                if not ler_mensagem(msg):
                    continue
                base.lembrar_email(msgid)
            processados.mkdir(exist_ok=True)
            caminho.replace(processados / caminho.name)

    if imap:
        if not saude.pode_usar("imap"):
            erros.append("imap: adaptador parado após falhas seguidas (agente saude reativar imap)")
        else:
            desde = base.ultima_rodada.date() - timedelta(days=1) if base.ultima_rodada else hoje - timedelta(days=DIAS_IMAP_PRIMEIRA_VEZ)
            mensagens = []
            try:
                mensagens = ler_imap(imap, desde, imap_factory)
                saude.sucesso("imap")
            except (ColetaErro, OSError, imaplib.IMAP4.error) as erro:
                if saude.falha("imap", str(erro)):
                    falhas.append(f"imap: {erro}")
                erros.append(f"e-mail (IMAP): {erro}")
            for msgid, msg in mensagens:
                if msgid not in base.emails_processados and ler_mensagem(msg):
                    base.lembrar_email(msgid)

    if usar_paginas:
        cargos = config.todos_cargos()
        for empresa in config.empresas_alvo():
            url = empresa.pagina_carreira
            if not url:
                continue
            if not pode_ler(url):
                erros.append(f"{empresa.nome}: página não lida (modo somente sugestão ou plataforma desligada)")
                continue
            nome = f"pagina:{empresa.nome}"
            if not saude.pode_usar(nome):
                erros.append(f"{nome}: adaptador parado (agente saude reativar \"{nome}\")")
                continue
            try:
                if not robots_permite(url, baixar_fn):
                    erros.append(f"{empresa.nome}: o robots.txt não permite ler a página de carreira")
                    continue
                status, html = baixar_fn(url)
                if status >= 400:
                    raise ColetaErro(f"a página de carreira respondeu HTTP {status}")
                pagina = analisar_html(html)
                if not pagina.links and not jobpostings(pagina.jsonld):
                    raise ColetaErro("a página não tem links nem dados de vagas: o layout mudou")
                brutas.extend(vagas_de_pagina(url, html, cargos, empresa.nome))
                saude.sucesso(nome)
            except ColetaErro as erro:
                if saude.falha(nome, str(erro)):
                    falhas.append(f"{nome}: {erro}")
                erros.append(f"{empresa.nome}: {erro}")
            finally:
                dormir(INTERVALO_SEGUNDOS)
    return brutas, erros, falhas


def enriquecer(vagas: list[VagaEncontrada], config: ConfigVagas, baixar_fn: Baixador, dormir: Dormir,
               pode_ler: PodeLer = _sempre) -> int:
    """Abre a página das vagas sem descrição, só em domínios permitidos e com robots.txt respeitado."""
    abertas = 0
    for vaga in vagas:
        if vaga.descricao or not vaga.link or not dominio_em(vaga.link, config.dominios_permitidos):
            continue
        if not pode_ler(vaga.link):
            continue
        try:
            if not robots_permite(vaga.link, baixar_fn):
                continue
            status, html = baixar_fn(vaga.link)
            if status in (404, 410):
                vaga.motivo_expiracao = f"o anúncio saiu do ar (HTTP {status})"
                continue
            if status >= 400:
                continue
            pagina = de_bruta(vaga_de_html(vaga.link, html, "pagina"))
            if pagina.descricao:
                mesclar(vaga, pagina)
                reextrair(vaga)
                abertas += 1
        except ColetaErro:
            continue
        finally:
            dormir(INTERVALO_SEGUNDOS)
    return abertas


# ---------------------------------------------------------------- triagem

def avaliar(
    vaga: VagaEncontrada, perfil: PerfilMestre, config: ConfigVagas, indice: IndiceTFIDF,
    vetor_perfil: dict[str, float], hoje: date,
) -> None:
    vaga.sinais = sinais_risco(vaga) + sinais_estagio(vaga)
    busca, motivos = avaliar_filtros(vaga, config, perfil, hoje)
    vaga.busca = busca
    vaga.motivos_eliminacao = motivos
    if motivos and vaga.status == "nova":
        vaga.status = "eliminada"
    elif not motivos and vaga.status == "eliminada":
        vaga.status = "nova"
    vaga.aderencia = calcular_aderencia(perfil, vaga, indice, config, vetor_perfil)


def expirar(
    base: BaseVagas, hoje: date, config: ConfigVagas, *, baixar_fn: Baixador | None = None,
    dormir: Dormir = time.sleep, verificar_links: bool = False, pode_ler: PodeLer = _sempre,
) -> list[VagaEncontrada]:
    """Marca vagas expiradas e as tira do resumo (RF-VG-12)."""
    expiradas: list[VagaEncontrada] = []
    for vaga in base.itens:
        if vaga.status not in ("nova", "no_resumo", "salva"):
            continue
        if (verificar_links and baixar_fn and vaga.status != "nova" and vaga.link
                and dominio_em(vaga.link, config.dominios_permitidos) and pode_ler(vaga.link)):
            try:
                if robots_permite(vaga.link, baixar_fn):
                    status, html = baixar_fn(vaga.link)
                    if status in (404, 410):
                        vaga.motivo_expiracao = f"o anúncio saiu do ar (HTTP {status})"
                    elif html and PADRAO_ENCERRADA.search(analisar_html(html).texto):
                        vaga.motivo_expiracao = "a página diz que a vaga foi encerrada"
            except ColetaErro:
                pass
            finally:
                dormir(INTERVALO_SEGUNDOS)
        if motivo := motivo_expiracao(vaga, hoje, config.dias_validade):
            vaga.status = "expirada"
            vaga.motivo_expiracao = motivo
            expiradas.append(vaga)
    return expiradas


@dataclass
class Processamento:
    adicionadas: list[VagaEncontrada] = field(default_factory=list)
    mescladas: list[VagaEncontrada] = field(default_factory=list)
    destinos: list[VagaEncontrada] = field(default_factory=list)
    abertas: int = 0
    eliminadas: list[VagaEncontrada] = field(default_factory=list)
    expiradas: list[VagaEncontrada] = field(default_factory=list)
    alertas: list[VagaEncontrada] = field(default_factory=list)
    arquivo_alerta: Path | None = None


def processar(
    brutas: list[VagaBruta], base: BaseVagas, perfil: PerfilMestre, config: ConfigVagas, hoje: date, *,
    baixar_fn: Baixador = baixar, dormir: Dormir = time.sleep, enriquecer_links: bool = True,
    verificar_links: bool = False, pode_ler: PodeLer = _sempre,
) -> Processamento:
    adicionadas, por_mescla, destinos = incorporar(base, [de_bruta(b) for b in brutas])
    for vaga in por_mescla:
        reextrair(vaga)
    abertas = enriquecer(adicionadas, config, baixar_fn, dormir, pode_ler) if enriquecer_links else 0

    a_avaliar = adicionadas + [v for v in por_mescla if v.status in ("nova", "eliminada") and v not in adicionadas]
    ativas = [v for v in base.itens if v.status != "expirada"]
    indice = IndiceTFIDF([documento_perfil(perfil)] + [documento_vaga(v) for v in ativas])
    vetor_perfil = indice.vetor(documento_perfil(perfil))
    for vaga in a_avaliar:
        avaliar(vaga, perfil, config, indice, vetor_perfil, hoje)

    expiradas = expirar(base, hoje, config, baixar_fn=baixar_fn, dormir=dormir, verificar_links=verificar_links,
                        pode_ler=pode_ler)
    alertas = selecionar_alertas(base, config)
    return Processamento(
        adicionadas=adicionadas, mescladas=por_mescla, destinos=destinos, abertas=abertas,
        eliminadas=[v for v in a_avaliar if v.status == "eliminada"], expiradas=expiradas, alertas=alertas,
        arquivo_alerta=salvar_alerta(alertas) if alertas else None,
    )


# ---------------------------------------------------------------- rodada completa

def pedir_justificativa(vagas: list[VagaEncontrada], perfil: PerfilMestre, motor_configurado: str, hoje: date) -> str | None:
    """A justificativa escrita fica pendente na fila de IA até o usuário autorizar (RF-IA-03)."""
    if not vagas or motor_configurado == "local":
        return None
    motor = "claude" if motor_configurado == "perguntar" else motor_configurado
    prompt, removidos = sanitizar(prompt_justificativas(vagas, perfil, motor), valores_sensiveis(perfil))
    usos = carregar_usos()
    # Um pedido de justificativa por vez na fila: o de hoje substitui o que ainda não foi decidido.
    for antigo in usos.pendentes():
        if antigo.tarefa == "justificativa-vagas":
            antigo.autorizacao = "descartado"
            antigo.prompt_pendente = None
            antigo.resultado = f"substituído pelo pedido da rodada de {hoje:%d/%m/%Y}"
    uso = registrar_pedido(
        usos, tarefa="justificativa-vagas", descricao=TAREFAS["justificativa-vagas"], motor=motor,
        dados=dados_enviados_justificativa(vagas), prompt=prompt, removidos=removidos,
        nome_arquivo=f"prompt-justificativas-{hoje:%Y-%m-%d}-{motor}.md", autorizado=False,
    )
    salvar_usos(usos)
    return uso.id


@dataclass
class ResultadoRodada:
    coletadas: int
    processamento: Processamento
    resumo: Resumo
    arquivo_resumo: Path
    erros: list[str]
    pedido_ia: str | None
    falhas_adaptadores: list[str] = field(default_factory=list)


def executar_rodada(
    perfil: PerfilMestre, config: ConfigVagas, base: BaseVagas, hoje: date, *,
    pasta_emails: Path | None, imap: dict[str, str] | None, imap_factory=imaplib.IMAP4_SSL,
    baixar_fn: Baixador = baixar, dormir: Dormir = time.sleep, usar_paginas: bool = True,
    enriquecer_links: bool = True, verificar_links: bool = False, motor_justificativa: str = "perguntar",
    saude: RegistroSaude | None = None, pode_ler: PodeLer = _sempre,
) -> ResultadoRodada:
    brutas, erros, falhas = coletar(
        config, base, hoje, pasta_emails=pasta_emails, imap=imap, imap_factory=imap_factory,
        baixar_fn=baixar_fn, dormir=dormir, usar_paginas=usar_paginas, saude=saude, pode_ler=pode_ler,
    )
    proc = processar(
        brutas, base, perfil, config, hoje, baixar_fn=baixar_fn, dormir=dormir,
        enriquecer_links=enriquecer_links, verificar_links=verificar_links, pode_ler=pode_ler,
    )
    resumo = montar_resumo(
        base, config, hoje, eliminadas=proc.eliminadas, expiradas=len(proc.expiradas),
        coletadas=len(brutas), erros=erros,
    )
    arquivo = salvar_resumo(resumo, config)
    vagas_do_resumo = [base.buscar(i.id) for i in resumo.itens]
    marcar_no_resumo(base, resumo)
    base.ultima_rodada = datetime.now(timezone.utc)
    pedido = pedir_justificativa(vagas_do_resumo, perfil, motor_justificativa, hoje)
    return ResultadoRodada(
        coletadas=len(brutas), processamento=proc, resumo=resumo, arquivo_resumo=arquivo,
        erros=erros, pedido_ia=pedido, falhas_adaptadores=falhas,
    )
