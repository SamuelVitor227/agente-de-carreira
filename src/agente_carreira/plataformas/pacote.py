"""Pacote de cadastro por plataforma (RF-PL-02, RF-PL-05) e conferência (RF-PL-04, RF-PL-07).

Cada campo da plataforma é mapeado para o perfil-mestre e ajustado ao limite
dela. Campos que o agente não pode preencher (CPF, pretensão sem faixa) ficam
marcados como manuais. A conferência compara o que a plataforma gravou com o
pacote e mede a completude.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from ..models import PerfilMestre
from ..respostas import BancoRespostas
from .catalogo import CampoPlataforma, Plataforma

PREFIXO_CAMPO = "### CAMPO:"


class CampoPreenchido(BaseModel):
    id: str
    rotulo: str
    valor: str | None = None
    obrigatorio: bool = False
    limite: int | None = None
    cortado: bool = False
    manual: bool = False
    instrucao: str | None = None


class PacoteCadastro(BaseModel):
    plataforma: str
    gerado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    variante: str
    cv_arquivo: str | None = None
    campos: list[CampoPreenchido] = Field(default_factory=list)

    @property
    def assinatura(self) -> str:
        """Muda quando algum valor muda — base da propagação (RF-PL-08)."""
        valores = {c.id: c.valor for c in self.campos if c.id != "cv"}
        valores["variante"] = self.variante
        return hashlib.sha1(json.dumps(valores, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

    def campo(self, id_: str) -> CampoPreenchido:
        for campo in self.campos:
            if campo.id == id_:
                return campo
        raise ValueError(f"O pacote não tem o campo {id_!r}.")


def _norm(texto: str | None) -> str:
    sem = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", sem).strip()


def _mes_ano(d) -> str:
    return f"{d.month:02d}/{d.year}"


def ajustar_ao_limite(texto: str, limite: int | None) -> tuple[str, bool]:
    """Corta no último fim de frase (ou palavra) que caiba no limite."""
    if limite is None or len(texto) <= limite:
        return texto, False
    trecho = texto[:limite]
    corte = max(trecho.rfind(". "), trecho.rfind("\n"))
    if corte < limite * 0.5:
        corte = trecho.rfind(" ")
    return trecho[: corte + 1 if corte > 0 else limite].rstrip(), True


def _experiencias(perfil: PerfilMestre) -> str:
    conquistas = {c.id: c for c in perfil.banco_conquistas}
    blocos = []
    for exp in sorted(perfil.experiencias, key=lambda e: e.periodo.inicio, reverse=True):
        fim = _mes_ano(exp.periodo.fim) if exp.periodo.fim else "atual"
        linhas = [f"{exp.cargo} — {exp.empresa} ({_mes_ano(exp.periodo.inicio)} - {fim})"]
        linhas += [f"• {r}" for r in exp.responsabilidades]
        for cid in exp.conquista_ids:
            if c := conquistas.get(cid):
                frase = f"• {c.verbo_acao} {c.descricao}" + (f" — {c.resultado}" if c.resultado else "")
                linhas.append(frase + (f" ({c.numero})" if c.numero else ""))
        if exp.tecnologias:
            linhas.append(f"Tecnologias: {', '.join(exp.tecnologias)}")
        blocos.append("\n".join(linhas))
    return "\n\n".join(blocos)


def _habilidades(perfil: PerfilMestre, ordem: list[str] | None) -> str:
    """RF-PL-05: as mais pedidas nas vagas-alvo primeiro (é o que a Gupy usa para ordenar)."""
    todas = list(dict.fromkeys(perfil.competencias_tecnicas + perfil.competencias_comportamentais))
    if ordem:
        posicao = {nome.lower(): i for i, nome in enumerate(ordem)}
        todas.sort(key=lambda c: posicao.get(c.lower(), len(posicao)))
    return ", ".join(todas)


def apresentacao_geral(perfil: PerfilMestre, banco: BancoRespostas | None = None) -> str | None:
    if banco and (pronta := banco.resposta("apresentacao_60s")):
        return pronta
    base = perfil.resumo or perfil.objetivo
    if not base:
        return None
    frases = re.split(r"(?<=[.!?])\s+", base.strip())
    return " ".join(frases[:2])


def valor_do_campo(
    perfil: PerfilMestre, campo: CampoPlataforma, banco: BancoRespostas | None, ordem_habilidades: list[str] | None,
    cv_arquivo: str | None, tipo_contrato: str | None = None,
) -> tuple[str | None, bool, str | None]:
    """(valor, é manual, instrução) — nada que não esteja no perfil ou no banco de respostas (RN-02, RN-09)."""
    origem = campo.origem
    if origem == "manual":
        return None, True, campo.instrucao
    if origem.startswith("resposta:"):
        chave = origem.split(":", 1)[1]
        if chave == "pretensao":
            chave = {"estagio": "pretensao_estagio", "pj": "pretensao_pj"}.get(tipo_contrato or "estagio", "pretensao_clt")
        resposta = banco.resposta(chave) if banco else None
        return (resposta, False, None) if resposta else (None, True, campo.instrucao)
    if origem.startswith(("contato.", "links.")):
        grupo, atributo = origem.split(".", 1)
        return getattr(getattr(perfil, grupo), atributo, None), False, None
    if origem == "resumo":
        return perfil.resumo or perfil.objetivo, False, None
    if origem == "formacao":
        linhas = [
            f"{f.curso} — {f.instituicao}" + "".join([
                f" ({f.status})" if f.status else "",
                f", conclusão prevista {f.conclusao_prevista}" if f.conclusao_prevista else "",
            ])
            for f in perfil.formacao
        ]
        return "\n".join(linhas) or None, False, None
    if origem == "experiencias":
        return _experiencias(perfil) or None, False, None
    if origem == "habilidades":
        return _habilidades(perfil, ordem_habilidades) or None, False, None
    if origem == "idiomas":
        return ", ".join(f"{i.idioma}: {i.nivel}" for i in perfil.idiomas) or None, False, None
    if origem == "certificacoes":
        linhas = [
            c.nome + (f" — {c.emissor}" if c.emissor else "") + (f" (ID {c.id_credencial})" if c.id_credencial else "")
            + (f" {c.url_credencial}" if c.url_credencial else "")
            for c in perfil.certificacoes
        ]
        return "\n".join(linhas) or None, False, None
    if origem == "apresentacao":
        return apresentacao_geral(perfil, banco), False, campo.instrucao
    if origem == "cv":
        return cv_arquivo, cv_arquivo is None, None if cv_arquivo else "Exporte o CV da variante da plataforma."
    raise ValueError(f"Origem de campo desconhecida: {origem}")


def gerar_pacote(
    perfil: PerfilMestre, plataforma: Plataforma, *, banco: BancoRespostas | None = None,
    ordem_habilidades: list[str] | None = None, cv_arquivo: str | None = None,
) -> PacoteCadastro:
    variante = f"cv-{plataforma.variante.foco}-{plataforma.variante.idioma}-{plataforma.variante.nivel}"
    pacote = PacoteCadastro(plataforma=plataforma.id, variante=variante, cv_arquivo=cv_arquivo)
    for campo in plataforma.campos:
        valor, manual, instrucao = valor_do_campo(perfil, campo, banco, ordem_habilidades, cv_arquivo,
                                                  "estagio" if plataforma.variante.nivel == "estagio" else None)
        cortado = False
        if valor and campo.id != "cv":
            valor, cortado = ajustar_ao_limite(valor, campo.limite)
        pacote.campos.append(CampoPreenchido(
            id=campo.id, rotulo=campo.rotulo, valor=valor, obrigatorio=campo.obrigatorio, limite=campo.limite,
            cortado=cortado, manual=manual, instrucao=instrucao,
        ))
    return pacote


def pacote_markdown(pacote: PacoteCadastro, plataforma: Plataforma) -> str:
    linhas = [f"# Pacote de cadastro — {plataforma.nome}", "", f"Variante de CV: {pacote.variante}", ""]
    for c in pacote.campos:
        marca = " (obrigatório)" if c.obrigatorio else ""
        linhas.append(f"{PREFIXO_CAMPO} {c.id} — {c.rotulo}{marca}")
        if c.manual:
            linhas.append(f"[preencha você] {c.instrucao or ''}".strip())
        else:
            linhas.append(c.valor or "(vazio no perfil-mestre)")
        if c.cortado:
            linhas.append(f"[ajustado ao limite de {c.limite} caracteres]")
        linhas.append("")
    return "\n".join(linhas)


# ---------------------------------------------------------------- RF-PL-04 / RF-PL-07

class Comparacao(BaseModel):
    campo: str
    rotulo: str
    status: Literal["ok", "diferente", "faltando", "manual", "nao_conferido"]
    esperado: str | None = None
    encontrado: str | None = None


def ler_campos(texto: str, pacote: PacoteCadastro) -> dict[str, str]:
    """Aceita blocos '### CAMPO: id' ou linhas 'Rótulo: valor' com o que a plataforma mostra."""
    por_rotulo = {_norm(c.rotulo): c.id for c in pacote.campos} | {_norm(c.id): c.id for c in pacote.campos}
    lidos: dict[str, str] = {}
    atual: str | None = None
    for linha in texto.splitlines():
        limpa = linha.strip()
        if limpa.startswith(PREFIXO_CAMPO):
            atual = limpa[len(PREFIXO_CAMPO):].strip().split(" ")[0]
            lidos[atual] = ""
            continue
        if atual is not None:
            lidos[atual] = (lidos[atual] + "\n" + linha).strip()
            continue
        rotulo, sep, valor = limpa.partition(":")
        if sep and _norm(rotulo) in por_rotulo:
            lidos[por_rotulo[_norm(rotulo)]] = valor.strip()
    return lidos


def comparar(pacote: PacoteCadastro, lidos: dict[str, str]) -> list[Comparacao]:
    resultado = []
    for c in pacote.campos:
        if c.id == "cv":
            continue
        encontrado = lidos.get(c.id)
        if c.manual:
            status = "manual" if not encontrado else "ok"
        elif c.id not in lidos:
            status = "nao_conferido"
        elif not (encontrado or "").strip():
            status = "faltando" if c.valor else "ok"
        elif _norm(encontrado) == _norm(c.valor) or (c.valor and _norm(c.valor) in _norm(encontrado)):
            status = "ok"
        else:
            status = "diferente"
        resultado.append(Comparacao(campo=c.id, rotulo=c.rotulo, status=status, esperado=c.valor, encontrado=encontrado))
    return resultado


def completude(comparacoes: list[Comparacao]) -> int:
    conferidas = [c for c in comparacoes if c.status != "nao_conferido"]
    if not conferidas:
        return 0
    return round(100 * sum(1 for c in conferidas if c.status in ("ok", "manual")) / len(conferidas))


def campos_alterados(antigo: PacoteCadastro, novo: PacoteCadastro) -> list[str]:
    """RF-PL-08: campos cujo valor mudou desde o último cadastro."""
    anteriores = {c.id: c.valor for c in antigo.campos}
    return [c.id for c in novo.campos if c.id != "cv" and anteriores.get(c.id) != c.valor]
