"""Auditoria do perfil do LinkedIn contra o checklist do Anexo A (RF-LI-01).

O agente verifica automaticamente o que dá para checar a partir do
perfil-mestre (e da exportação de dados do LinkedIn, quando fornecida) e
lista as pendências por impacto; o status de cada item fica salvo e é
atualizado pelo usuário conforme aplica as mudanças.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..arquivos import gravar_modelo, ler_modelo
from ..models import PerfilMestre
from ..storage import diretorio_dados
from .estado import carregar_estado
from .limites import LIMITES

ARQUIVO_AUDITORIA = "linkedin-auditoria.json"

Impacto = Literal["alto", "medio", "baixo"]
Status = Literal["pendente", "feito", "nao_se_aplica"]


class ItemChecklist(BaseModel):
    numero: int
    titulo: str
    descricao: str
    impacto: Impacto


# Anexo A — checklist de alterações padrão no LinkedIn (configuração).
ANEXO_A: list[ItemChecklist] = [
    ItemChecklist(numero=1, titulo='Desligar "Compartilhar atualizações do perfil"', impacto="medio",
                  descricao="Antes da rodada de edições, em Configurações e privacidade > Visibilidade."),
    ItemChecklist(numero=2, titulo="Foto e capa", impacto="medio",
                  descricao="Foto nítida com fundo neutro; capa com área e stack. O agente orienta, não gera fotos."),
    ItemChecklist(numero=3, titulo="Título (até 220 caracteres)", impacto="alto",
                  descricao="Cargo-alvo + stack + diferencial, essencial nos primeiros 60 caracteres."),
    ItemChecklist(numero=4, titulo="Localização", impacto="alto",
                  descricao="Cidade real para aparecer nas buscas por local."),
    ItemChecklist(numero=5, titulo="URL personalizada", impacto="medio",
                  descricao="3 a 100 caracteres, sem espaços nem símbolos; até 5 trocas em 6 meses."),
    ItemChecklist(numero=6, titulo="Open to Work", impacto="alto",
                  descricao="Até 5 cargos, locais, início e visibilidade (só recrutadores ou todos)."),
    ItemChecklist(numero=7, titulo="Sobre (até 2.600 caracteres)", impacto="alto",
                  descricao="Proposta de valor nos primeiros ~300 caracteres; termos verdadeiros das vagas."),
    ItemChecklist(numero=8, titulo="Experiência (até 2.000 caracteres por cargo)", impacto="alto",
                  descricao="Conquistas com verbo de ação, resultado e tecnologia; mesmos cargos e datas do CV."),
    ItemChecklist(numero=9, titulo="Formação", impacto="medio",
                  descricao="Curso e instituição com conclusão prevista e TCC na descrição."),
    ItemChecklist(numero=10, titulo="Licenças e certificados", impacto="medio",
                  descricao="Certificações com ID e link da credencial."),
    ItemChecklist(numero=11, titulo="Projetos", impacto="medio",
                  descricao="TCC e projetos de portfólio com tecnologias, resultado e link."),
    ItemChecklist(numero=12, titulo="Competências", impacto="alto",
                  descricao="Até 100; priorizar as mais pedidas nas vagas-alvo e vincular ao cargo/projeto."),
    ItemChecklist(numero=13, titulo="Em destaque", impacto="medio",
                  descricao="GitHub, portfólio e o trabalho do TCC."),
    ItemChecklist(numero=14, titulo="Idiomas", impacto="medio",
                  descricao="Nível real de cada idioma."),
    ItemChecklist(numero=15, titulo="Informações de contato", impacto="medio",
                  descricao="E-mail, GitHub e portfólio."),
    ItemChecklist(numero=16, titulo="Perfil em inglês", impacto="baixo",
                  descricao="Criado no computador; a tradução é mantida à parte."),
    ItemChecklist(numero=17, titulo="Recomendações", impacto="baixo",
                  descricao="Pedir 2 ou 3: orientador, professores e colegas de projeto."),
    ItemChecklist(numero=18, titulo="Alertas de vagas", impacto="alto",
                  descricao="Até 20 alertas diários por e-mail, espelhando as buscas salvas."),
    ItemChecklist(numero=19, titulo="Religar o compartilhamento (opcional)", impacto="baixo",
                  descricao="Se quiser anunciar a busca, religue e publique um post curto."),
]


class ItemAuditoria(BaseModel):
    numero: int
    titulo: str
    impacto: Impacto
    status: Status = "pendente"
    verificacao: str | None = None  # o que o agente conseguiu checar sozinho


class Auditoria(BaseModel):
    atualizada_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: dict[int, Status] = Field(default_factory=dict)


def caminho_auditoria() -> Path:
    return diretorio_dados() / ARQUIVO_AUDITORIA


def carregar_auditoria() -> Auditoria:
    caminho = caminho_auditoria()
    return ler_modelo(caminho, Auditoria)


def salvar_auditoria(auditoria: Auditoria) -> None:
    auditoria.atualizada_em = datetime.now(timezone.utc)
    caminho = caminho_auditoria()
    gravar_modelo(caminho, auditoria)


def _verificacoes_automaticas(perfil: PerfilMestre) -> dict[int, str]:
    """O que o agente consegue conferir a partir do perfil-mestre."""
    v: dict[int, str] = {}
    if perfil.objetivo and perfil.competencias_tecnicas:
        v[3] = "material pronto: gere as opções com 'agente li titulo'"
    if perfil.contato.cidade:
        v[4] = f"cidade registrada no perfil: {perfil.contato.cidade}"
    v[5] = "sugestão e validação com 'agente li ajustes'"
    if perfil.resumo:
        v[7] = "material pronto: gere o texto com 'agente li sobre'"
    if perfil.experiencias:
        v[8] = "material pronto: gere os textos com 'agente li experiencias'"
    if perfil.formacao:
        f = perfil.formacao[0]
        v[9] = f"formação registrada: {f.curso} — {f.instituicao}"
    if perfil.certificacoes:
        sem_link = [c.nome for c in perfil.certificacoes if not (c.id_credencial or c.url_credencial)]
        v[10] = (
            "todas as certificações têm ID/link"
            if not sem_link
            else f"sem ID/link: {', '.join(sem_link)}"
        )
    if perfil.projetos:
        v[11] = f"{len(perfil.projetos)} projeto(s) registrados no perfil"
    if perfil.competencias_tecnicas:
        qtd = len(perfil.competencias_tecnicas)
        v[12] = f"{qtd} competência(s) no perfil (limite da seção: {LIMITES['competencias']})"
    if perfil.links.github or perfil.links.portfolio:
        v[13] = "links de GitHub/portfólio registrados para a seção Em destaque"
    if perfil.idiomas:
        v[14] = ", ".join(f"{i.idioma} ({i.nivel})" for i in perfil.idiomas)
    contatos = [perfil.contato.email, perfil.links.github, perfil.links.portfolio]
    if all(contatos):
        v[15] = "e-mail, GitHub e portfólio registrados"
    elif any(contatos):
        v[15] = "contato incompleto no perfil (e-mail, GitHub e portfólio)"
    return v


def auditar(perfil: PerfilMestre) -> list[ItemAuditoria]:
    """Checklist completo com status salvo + verificações automáticas, pendências primeiro por impacto."""
    salva = carregar_auditoria()
    automaticas = _verificacoes_automaticas(perfil)
    if any(campo.startswith("en:") for campo in carregar_estado().campos):
        automaticas[16] = "perfil em inglês com campos aplicados (veja 'agente li log')"
    itens = [
        ItemAuditoria(
            numero=item.numero,
            titulo=item.titulo,
            impacto=item.impacto,
            status=salva.status.get(item.numero, "pendente"),
            verificacao=automaticas.get(item.numero),
        )
        for item in ANEXO_A
    ]
    peso = {"alto": 0, "medio": 1, "baixo": 2}
    itens.sort(key=lambda i: (i.status != "pendente", peso[i.impacto], i.numero))
    return itens


def marcar(numero: int, status: Status) -> None:
    if numero not in {i.numero for i in ANEXO_A}:
        raise ValueError(f"Item {numero} não existe no checklist (1 a {len(ANEXO_A)}).")
    auditoria = carregar_auditoria()
    auditoria.status[numero] = status
    salvar_auditoria(auditoria)
