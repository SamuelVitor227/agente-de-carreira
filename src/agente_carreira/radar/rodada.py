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
from .aderencia import IndiceTFIDF, calcular_aderencia, documento_perfil, documento_vaga
from .coleta import (
    INTERVALO_SEGUNDOS,
    Baixador,
    ColetaErro,
    baixar,
    dominio_em,
    ler_eml,
    ler_imap,
    robots_permite,
    vaga_de_html,
    vagas_de_email,
    vagas_de_pagina,
)
from .dedup import incorporar, mesclar
from .extracao import analisar_html, extrair_campos
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

def coletar(
    config: ConfigVagas, base: BaseVagas, hoje: date, *, pasta_emails: Path | None, imap: dict[str, str] | None,
    imap_factory=imaplib.IMAP4_SSL, baixar_fn: Baixador = baixar, dormir: Dormir = time.sleep, usar_paginas: bool = True,
) -> tuple[list[VagaBruta], list[str]]:
    brutas: list[VagaBruta] = []
    erros: list[str] = []

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
                brutas.extend(vagas_de_email(msg))
                base.lembrar_email(msgid)
            processados.mkdir(exist_ok=True)
            caminho.replace(processados / caminho.name)

    if imap:
        desde = base.ultima_rodada.date() - timedelta(days=1) if base.ultima_rodada else hoje - timedelta(days=DIAS_IMAP_PRIMEIRA_VEZ)
        try:
            for msgid, msg in ler_imap(imap, desde, imap_factory):
                if msgid in base.emails_processados:
                    continue
                brutas.extend(vagas_de_email(msg))
                base.lembrar_email(msgid)
        except (ColetaErro, OSError, imaplib.IMAP4.error) as erro:
            erros.append(f"e-mail (IMAP): {erro}")

    if usar_paginas:
        cargos = config.todos_cargos()
        for empresa in config.empresas_alvo():
            url = empresa.pagina_carreira
            if not url:
                continue
            try:
                if not robots_permite(url, baixar_fn):
                    erros.append(f"{empresa.nome}: o robots.txt não permite ler a página de carreira")
                    continue
                status, html = baixar_fn(url)
                if status >= 400:
                    erros.append(f"{empresa.nome}: a página de carreira respondeu HTTP {status}")
                    continue
                brutas.extend(vagas_de_pagina(url, html, cargos, empresa.nome))
            except ColetaErro as erro:
                erros.append(f"{empresa.nome}: {erro}")
            finally:
                dormir(INTERVALO_SEGUNDOS)
    return brutas, erros


def enriquecer(vagas: list[VagaEncontrada], config: ConfigVagas, baixar_fn: Baixador, dormir: Dormir) -> int:
    """Abre a página das vagas sem descrição, só em domínios permitidos e com robots.txt respeitado."""
    abertas = 0
    for vaga in vagas:
        if vaga.descricao or not vaga.link or not dominio_em(vaga.link, config.dominios_permitidos):
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
    dormir: Dormir = time.sleep, verificar_links: bool = False,
) -> list[VagaEncontrada]:
    """Marca vagas expiradas e as tira do resumo (RF-VG-12)."""
    expiradas: list[VagaEncontrada] = []
    for vaga in base.itens:
        if vaga.status not in ("nova", "no_resumo", "salva"):
            continue
        if (verificar_links and baixar_fn and vaga.status != "nova" and vaga.link
                and dominio_em(vaga.link, config.dominios_permitidos)):
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
    verificar_links: bool = False,
) -> Processamento:
    adicionadas, por_mescla, destinos = incorporar(base, [de_bruta(b) for b in brutas])
    for vaga in por_mescla:
        reextrair(vaga)
    abertas = enriquecer(adicionadas, config, baixar_fn, dormir) if enriquecer_links else 0

    a_avaliar = adicionadas + [v for v in por_mescla if v.status in ("nova", "eliminada") and v not in adicionadas]
    ativas = [v for v in base.itens if v.status != "expirada"]
    indice = IndiceTFIDF([documento_perfil(perfil)] + [documento_vaga(v) for v in ativas])
    vetor_perfil = indice.vetor(documento_perfil(perfil))
    for vaga in a_avaliar:
        avaliar(vaga, perfil, config, indice, vetor_perfil, hoje)

    expiradas = expirar(base, hoje, config, baixar_fn=baixar_fn, dormir=dormir, verificar_links=verificar_links)
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


def executar_rodada(
    perfil: PerfilMestre, config: ConfigVagas, base: BaseVagas, hoje: date, *,
    pasta_emails: Path | None, imap: dict[str, str] | None, imap_factory=imaplib.IMAP4_SSL,
    baixar_fn: Baixador = baixar, dormir: Dormir = time.sleep, usar_paginas: bool = True,
    enriquecer_links: bool = True, verificar_links: bool = False, motor_justificativa: str = "perguntar",
) -> ResultadoRodada:
    brutas, erros = coletar(
        config, base, hoje, pasta_emails=pasta_emails, imap=imap, imap_factory=imap_factory,
        baixar_fn=baixar_fn, dormir=dormir, usar_paginas=usar_paginas,
    )
    proc = processar(
        brutas, base, perfil, config, hoje, baixar_fn=baixar_fn, dormir=dormir,
        enriquecer_links=enriquecer_links, verificar_links=verificar_links,
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
        erros=erros, pedido_ia=pedido,
    )
