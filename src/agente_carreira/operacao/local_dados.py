"""Onde ficam os seus dados (RF-EV-19): perfil, currículos, candidaturas e o navegador do agente com os logins.

Por padrão eles ficam em data/, dentro da pasta do projeto. Se essa pasta estiver no OneDrive, tudo vai para a
nuvem da Microsoft, inclusive as sessões do LinkedIn e do Outlook. Aqui dá para ver isso e mover os dados para uma
pasta só deste computador (padrão: %LOCALAPPDATA%\\AgenteCarreira\\data). A variável AGENTE_CARREIRA_DATA passa a
apontar para lá, e o atalho e a busca agendada precisam ser recriados (o app faz isso).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..storage import diretorio_dados

VARIAVEL = "AGENTE_CARREIRA_DATA"


@dataclass
class LocalDados:
    pasta: Path
    na_nuvem: str | None  # "OneDrive" (ou outro serviço) quando a pasta sincroniza; None se é só deste computador
    tamanho_mb: float


def _pastas_nuvem() -> list[tuple[str, Path]]:
    pastas = []
    for variavel in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(variavel):
            pastas.append(("OneDrive", Path(os.environ[variavel])))
    return pastas


def servico_de_nuvem(pasta: Path) -> str | None:
    """Qual serviço sincroniza a pasta (OneDrive, Google Drive, Dropbox), se algum."""
    pasta = Path(pasta).resolve()
    for nome, raiz in _pastas_nuvem():
        try:
            pasta.relative_to(raiz.resolve())
            return nome
        except ValueError:
            continue
    partes = {p.lower() for p in pasta.parts}
    for nome, marcas in (("OneDrive", ("onedrive",)), ("Google Drive", ("google drive", "meu drive", "my drive")),
                         ("Dropbox", ("dropbox",))):
        if any(m in parte for parte in partes for m in marcas):
            return nome
    return None


def _tamanho_mb(pasta: Path) -> float:
    total = 0
    for p in pasta.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return round(total / 1024 / 1024, 1)


def local_atual() -> LocalDados:
    pasta = diretorio_dados().resolve()
    return LocalDados(pasta, servico_de_nuvem(pasta), _tamanho_mb(pasta) if pasta.is_dir() else 0.0)


def destino_padrao() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "AgenteCarreira" / "data"


class NaoDaParaMover(Exception):
    """Alguma condição impede mover agora (tarefa rodando, navegador aberto, destino ocupado)."""


def _navegador_aberto(pasta: Path) -> bool:
    sessoes = pasta / "navegador.sessoes"
    try:
        return bool(sessoes.is_file() and sessoes.read_text(encoding="utf-8").strip() not in ("", "{}"))
    except OSError:
        return False


def mover_dados(destino: Path | None = None, *, gravar_variavel=None) -> Path:
    """Copia tudo para `destino`, confere, aponta AGENTE_CARREIRA_DATA para lá e só então apaga a pasta antiga."""
    from ..operacao import andamento
    from .credenciais import gravar_variaveis_do_usuario

    origem = diretorio_dados().resolve()
    destino = (destino or destino_padrao()).resolve()
    if destino == origem:
        raise NaoDaParaMover("Os dados já estão nessa pasta.")
    if servico_de_nuvem(destino):
        raise NaoDaParaMover(f"A pasta {destino} também sincroniza com a nuvem ({servico_de_nuvem(destino)}).")
    if destino.exists() and any(destino.iterdir()):
        raise NaoDaParaMover(f"A pasta {destino} já tem arquivos. Escolha uma pasta vazia.")
    if andamento.em_andamento():
        raise NaoDaParaMover("Há uma tarefa rodando. Espere ela terminar (ou pare-a) e tente de novo.")
    if _navegador_aberto(origem):
        raise NaoDaParaMover("O navegador do agente está aberto. Feche-o e tente de novo.")
    if not origem.is_dir():
        raise NaoDaParaMover(f"Não há dados em {origem}.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(origem, destino, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.trava", "travas", "SingletonLock", "SingletonSocket", "SingletonCookie"))
    faltando = [p.relative_to(origem) for p in origem.rglob("*.json")
                if p.is_file() and not (destino / p.relative_to(origem)).is_file()]
    if faltando:
        raise NaoDaParaMover(f"A cópia ficou incompleta ({len(faltando)} arquivo(s)); nada foi apagado.")
    (gravar_variavel or gravar_variaveis_do_usuario)({VARIAVEL: str(destino)})
    os.environ[VARIAVEL] = str(destino)
    shutil.rmtree(origem, ignore_errors=True)  # o que estiver preso (raro) some quando o OneDrive soltar
    return destino
