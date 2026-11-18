"""Cópias de segurança diárias dos dados, guardadas por 7 dias.

Na primeira vez que o agente roda no dia (app, terminal ou busca agendada), os arquivos de dados
(perfil, vagas, candidaturas, configurações...) são copiados para data/copias/AAAA-MM-DD/. O navegador do
agente e as saídas (PDFs, resumos) ficam de fora: são grandes e podem ser gerados de novo.

Restaurar um dia guarda antes o estado atual em data/copias/antes-de-restaurar-AAAAMMDD-HHMMSS/.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .storage import diretorio_dados

PASTA = "copias"
DIAS_GUARDADOS = 7
RESERVAS_GUARDADAS = 3
ESTADO_DO_MOMENTO = {"andamento.json", "agendadas.json"}  # o que está acontecendo agora, não dados
_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PREFIXO_RESERVA = "antes-de-restaurar-"


@dataclass
class Copia:
    nome: str          # "2026-11-18" ou "antes-de-restaurar-20261118-101500"
    pasta: Path
    arquivos: int
    tamanho: int       # bytes

    @property
    def rotulo(self) -> str:
        if _DIA.match(self.nome):
            return f"{date.fromisoformat(self.nome):%d/%m/%Y}"
        quando = datetime.strptime(self.nome.removeprefix(PREFIXO_RESERVA), "%Y%m%d-%H%M%S")
        return f"antes da restauração de {quando:%d/%m %H:%M}"


def pasta_copias() -> Path:
    return diretorio_dados() / PASTA


def arquivos_de_dados() -> list[Path]:
    pasta = diretorio_dados()
    if not pasta.is_dir():
        return []
    return sorted(
        p for p in pasta.glob("*.json")
        if p.is_file() and p.name not in ESTADO_DO_MOMENTO and not p.name.startswith(("navegador.", "."))
        and ".danificado-" not in p.name
    )


def _copiar_para(destino: Path, arquivos: list[Path]) -> None:
    """Copia tudo para uma pasta temporária e só então dá o nome final: cópia completa ou nenhuma."""
    temporaria = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
    shutil.rmtree(temporaria, ignore_errors=True)
    temporaria.mkdir(parents=True)
    try:
        for arquivo in arquivos:
            shutil.copy2(arquivo, temporaria / arquivo.name)
        temporaria.rename(destino)
    finally:
        shutil.rmtree(temporaria, ignore_errors=True)


def garantir_copia_do_dia(hoje: date | None = None) -> Path | None:
    """Faz a cópia de hoje se ela ainda não existe. Devolve a pasta criada (None se já havia ou não há dados)."""
    destino = pasta_copias() / (hoje or date.today()).isoformat()
    if destino.is_dir():
        return None
    arquivos = arquivos_de_dados()
    if not arquivos:
        return None
    try:
        _copiar_para(destino, arquivos)
    except OSError:  # outro processo fez a cópia no mesmo instante
        return destino if destino.is_dir() else None
    _limpar_antigas()
    return destino


def _limpar_antigas() -> None:
    pastas = [p for p in pasta_copias().iterdir() if p.is_dir()]
    dias = sorted(p for p in pastas if _DIA.match(p.name))
    reservas = sorted(p for p in pastas if p.name.startswith(PREFIXO_RESERVA))
    for velha in dias[:-DIAS_GUARDADOS] + reservas[:-RESERVAS_GUARDADAS]:
        shutil.rmtree(velha, ignore_errors=True)


def listar_copias() -> list[Copia]:
    """Da mais nova para a mais antiga."""
    pasta = pasta_copias()
    if not pasta.is_dir():
        return []
    copias = []
    for p in pasta.iterdir():
        if p.is_dir() and (_DIA.match(p.name) or p.name.startswith(PREFIXO_RESERVA)):
            arquivos = [a for a in p.glob("*.json") if a.is_file()]
            copias.append(Copia(p.name, p, len(arquivos), sum(a.stat().st_size for a in arquivos)))
    # Dias e reservas na ordem em que foram feitos (a reserva leva data e hora no nome).
    return sorted(copias, key=lambda c: c.nome if _DIA.match(c.nome) else
                  datetime.strptime(c.nome.removeprefix(PREFIXO_RESERVA), "%Y%m%d-%H%M%S").strftime("%Y-%m-%d~%H%M%S"),
                  reverse=True)


def copias_do_arquivo(nome: str) -> list[Path]:
    """As cópias de um arquivo de dados, da mais nova para a mais antiga."""
    return [c.pasta / nome for c in listar_copias() if (c.pasta / nome).is_file()]


def restaurar(nome: str) -> list[str]:
    """Volta os arquivos de dados para a cópia `nome`; antes guarda o estado atual. Devolve os arquivos restaurados."""
    from .arquivos import gravar_texto

    origem = pasta_copias() / nome
    if not origem.is_dir() or not (_DIA.match(nome) or nome.startswith(PREFIXO_RESERVA)):
        raise ValueError(f"Cópia {nome!r} não existe. Veja as cópias com 'agente copias'.")
    atuais = arquivos_de_dados()
    if atuais:
        _copiar_para(pasta_copias() / f"{PREFIXO_RESERVA}{datetime.now():%Y%m%d-%H%M%S}", atuais)
    restaurados = []
    for arquivo in sorted(origem.glob("*.json")):
        gravar_texto(diretorio_dados() / arquivo.name, arquivo.read_text(encoding="utf-8"))
        restaurados.append(arquivo.name)
    _limpar_antigas()
    return restaurados
