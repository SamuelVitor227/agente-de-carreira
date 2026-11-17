"""Leitura dos repositórios do usuário no GitHub, via gh CLI já autenticado.

Usado como fonte de pauta para publicações no LinkedIn (RF-LI-12). Somente
leitura; repositórios privados ficam de fora por padrão, para que nenhum
rascunho exponha código que não é público.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field

CAMPOS_GH = "name,description,url,primaryLanguage,repositoryTopics,updatedAt,isFork,isPrivate"
LIMITE_README = 1500

Executor = Callable[..., subprocess.CompletedProcess]


class GitHubIndisponivel(Exception):
    """gh ausente, sem login ou com erro — a pauta segue só com o perfil-mestre."""


class RepoGitHub(BaseModel):
    nome: str
    descricao: str | None = None
    url: str
    linguagem: str | None = None
    topicos: list[str] = Field(default_factory=list)
    atualizado_em: datetime | None = None
    fork: bool = False
    privado: bool = False


def _executar(executar: Executor, args: list[str]) -> subprocess.CompletedProcess:
    try:
        return executar(args, capture_output=True, text=True, encoding="utf-8", check=False)
    except FileNotFoundError as erro:
        raise GitHubIndisponivel("gh CLI não encontrado — instale em https://cli.github.com e rode 'gh auth login'") from erro


def _topicos(bruto: object) -> list[str]:
    if not bruto:
        return []
    if isinstance(bruto, dict):
        bruto = bruto.get("nodes") or []
    nomes: list[str] = []
    for item in bruto if isinstance(bruto, list) else []:
        if isinstance(item, str):
            nomes.append(item)
        elif isinstance(item, dict):
            nome = item.get("name") or (item.get("topic") or {}).get("name")
            if nome:
                nomes.append(nome)
    return nomes


def listar_repositorios(
    executar: Executor = subprocess.run, incluir_forks: bool = False, limite: int = 100
) -> list[RepoGitHub]:
    """Repositórios públicos do usuário autenticado, do mais recente para o mais antigo."""
    resultado = _executar(executar, ["gh", "repo", "list", "--limit", str(limite), "--json", CAMPOS_GH])
    if resultado.returncode != 0:
        raise GitHubIndisponivel((resultado.stderr or "erro ao listar repositórios").strip())
    try:
        dados = json.loads(resultado.stdout or "[]")
    except json.JSONDecodeError as erro:
        raise GitHubIndisponivel("resposta inesperada do gh") from erro

    repos: list[RepoGitHub] = []
    for item in dados:
        atualizado = item.get("updatedAt")
        repo = RepoGitHub(
            nome=item.get("name", ""),
            descricao=item.get("description") or None,
            url=item.get("url", ""),
            linguagem=(item.get("primaryLanguage") or {}).get("name"),
            topicos=_topicos(item.get("repositoryTopics")),
            atualizado_em=datetime.fromisoformat(atualizado) if atualizado else None,
            fork=bool(item.get("isFork")),
            privado=bool(item.get("isPrivate")),
        )
        if repo.privado or (repo.fork and not incluir_forks) or not repo.nome:
            continue
        repos.append(repo)
    repos.sort(key=lambda r: r.atualizado_em.timestamp() if r.atualizado_em else 0, reverse=True)
    return repos


def ler_readme(url: str, executar: Executor = subprocess.run, limite: int = LIMITE_README) -> str | None:
    """Trecho inicial do README do repositório, ou None se não houver."""
    partes = [p for p in urlparse(url).path.split("/") if p]
    if "github.com" not in url or len(partes) < 2:
        return None
    dono, repo = partes[0], partes[1]
    try:
        resultado = _executar(
            executar,
            ["gh", "api", f"repos/{dono}/{repo}/readme", "-H", "Accept: application/vnd.github.raw"],
        )
    except GitHubIndisponivel:
        return None
    if resultado.returncode != 0 or not resultado.stdout:
        return None
    return resultado.stdout.strip()[:limite]
