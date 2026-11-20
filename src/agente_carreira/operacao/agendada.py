"""Tarefas agendadas no Windows: criar no Agendador, rodar sem janela e mostrar como foi.

- instalar(): grava o script de partida (data/app/tarefa.pyw) e o XML da tarefa, e cria a tarefa;
- rodar(): o que o Agendador executa. A saída vai para o log (data/rodada.log ou data/relatorio.log, com
  tamanho limitado) e o resultado de cada execução fica em data/agendadas.json;
- situacao(): a linha da tela Início ("Busca automática: todo dia às 07:00 · última: hoje às 07:02 ✓"),
  com aviso quando a busca não rodou ou terminou com erro.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..arquivos import gravar_json, gravar_texto
from ..radar.agenda import (NOME_TAREFA, NOME_TAREFA_SEMANAL, SCRIPT_TAREFA, comando_criar, proxima_vez,
                            script_tarefa, xml_tarefa)
from ..storage import diretorio_dados

ARQUIVO = "agendadas.json"
LIMITE_LOG = 512 * 1024
LOGS = {"vagas rodada": "rodada.log", "relatorio semanal": "relatorio.log"}
DESCRICOES = {NOME_TAREFA: "Agente de Carreira: busca diária de vagas",
              NOME_TAREFA_SEMANAL: "Agente de Carreira: relatório semanal"}
FOLGA = timedelta(hours=3)  # depois do horário, quanto esperar antes de dizer que a busca não rodou
SCRIPTS_ANTIGOS = ("rodada-vagas.cmd", "relatorio-semanal.cmd")


def chave(args: list[str]) -> str:
    return " ".join(a for a in args if not a.startswith("-"))


def ler() -> dict:
    caminho = diretorio_dados() / ARQUIVO
    try:
        return json.loads(caminho.read_text(encoding="utf-8")) if caminho.is_file() else {}
    except (OSError, ValueError):
        return {}


def _anotar(nome: str, **campos) -> None:
    dados = ler()
    dados.setdefault(nome, {}).update(campos)
    gravar_json(diretorio_dados() / ARQUIVO, dados)


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- criar a tarefa

def lancador_tarefa() -> tuple[Path, Path]:
    """(pythonw.exe do Python base, script de partida): roda sem nenhuma janela de console."""
    from ..app.atalho import _python_base_sem_console, raiz_do_projeto

    base = _python_base_sem_console()
    site_packages = raiz_do_projeto() / ".venv" / "Lib" / "site-packages"
    if base is None or not site_packages.is_dir():
        raise RuntimeError("Não achei o Python do projeto (pasta .venv). Rode 'uv sync' na pasta do agente.")
    script = diretorio_dados() / "app" / SCRIPT_TAREFA
    gravar_texto(script, script_tarefa(site_packages, raiz_do_projeto(), os.environ.get("AGENTE_CARREIRA_DATA")))
    return base, script


def preparar(nome: str, args: list[str], hora: str, dia: str | None = None,
             agora: datetime | None = None) -> tuple[Path, list[str]]:
    """Grava o script de partida e o XML da tarefa em data/app; devolve o XML e o comando que cria a tarefa."""
    from ..app.atalho import raiz_do_projeto

    executavel, script = lancador_tarefa()
    argumentos = " ".join([f'"{script}"', *args])
    inicio = proxima_vez(hora, agora or datetime.now(), dia)
    xml = diretorio_dados() / "app" / f"{nome}.xml"
    xml.parent.mkdir(parents=True, exist_ok=True)
    xml.write_text(xml_tarefa(executavel, argumentos, raiz_do_projeto(), inicio, DESCRICOES.get(nome, nome), dia),
                   encoding="utf-16")
    return xml, comando_criar(nome, xml)


def instalar(nome: str, args: list[str], hora: str, dia: str | None = None, *, executar=subprocess.run) -> Path:
    """Cria (ou recria) a tarefa no Agendador do Windows. Erro do schtasks vira RuntimeError com a mensagem dele."""
    xml, comando = preparar(nome, args, hora, dia)
    resultado = executar(comando, capture_output=True, text=True, encoding="oem" if sys.platform == "win32" else None,
                         errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if resultado.returncode != 0:
        raise RuntimeError((resultado.stderr or resultado.stdout or "").strip()
                           or f"o schtasks terminou com código {resultado.returncode}")
    _anotar(chave(args), tarefa=nome, instalada_em=_agora_iso(), hora=hora, dia=dia)
    for antigo in SCRIPTS_ANTIGOS:  # a tarefa antiga rodava um .cmd com janela de console
        (diretorio_dados() / antigo).unlink(missing_ok=True)
    return xml


# ---------------------------------------------------------------- rodar (o que o Agendador chama)

def _encurtar(caminho: Path) -> None:
    """Mantém o log pequeno: passou do limite, fica só a metade mais recente."""
    try:
        if not caminho.is_file() or caminho.stat().st_size <= LIMITE_LOG:
            return
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        resto = texto[-LIMITE_LOG // 2:]
        gravar_texto(caminho, resto[resto.find("\n") + 1:])
    except OSError:
        pass


def rodar(args: list[str]) -> int:
    """Roda 'agente ARGS' sem janela, com a saída no log, e anota o resultado em data/agendadas.json."""
    from .credenciais import carregar_variaveis_do_usuario

    carregar_variaveis_do_usuario()  # a pasta dos dados pode ter mudado (RF-EV-19) depois da tarefa criada
    os.environ["AGENTE_ORIGEM"] = "agendada"
    os.environ.setdefault("COLUMNS", "110")
    nome = chave(args)
    log = diretorio_dados() / LOGS.get(nome, "agendada.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    _encurtar(log)
    _anotar(nome, inicio=_agora_iso(), fim=None, codigo=None)
    antigos = sys.stdout, sys.stderr, sys.stdin
    with open(log, "a", encoding="utf-8", errors="replace") as saida:
        sys.stdout = sys.stderr = saida
        sys.stdin = io.StringIO("")  # ninguém para responder: uma pergunta cancela em vez de travar
        try:
            codigo = _executar(args, saida)
        finally:
            sys.stdout, sys.stderr, sys.stdin = antigos
    _anotar(nome, fim=_agora_iso(), codigo=codigo)
    return codigo


def _executar(args: list[str], saida) -> int:
    from ..storage import PerfilAusente

    inicio = datetime.now()
    print(f"\n===== {inicio:%d/%m/%Y %H:%M} · agente {' '.join(args)} (automática) =====", flush=True)
    try:
        from ..copias import garantir_copia_do_dia

        garantir_copia_do_dia()
    except Exception as erro:  # noqa: BLE001 - a cópia nunca impede a busca
        print(f"Aviso: a cópia de segurança do dia falhou: {erro}", flush=True)
    codigo = 1
    try:
        from typer.main import get_command

        from ..cli import app

        resultado = get_command(app).main(args=args, prog_name="agente", standalone_mode=False)
        codigo = resultado if isinstance(resultado, int) else 0
    except SystemExit as fim:
        codigo = fim.code if isinstance(fim.code, int) else 0 if fim.code is None else 1
    except PerfilAusente as erro:
        print(erro, flush=True)
    except BaseException:  # noqa: BLE001 - tudo vai para o log
        traceback.print_exc(file=saida)
    if chave(args) == "vagas rodada":  # RF-EV-01: depois das vagas, os retornos das empresas (mesmo Outlook)
        try:
            print("\n----- retornos das candidaturas -----", flush=True)
            get_command(app).main(args=["funil", "emails"], prog_name="agente", standalone_mode=False)
        except BaseException:  # noqa: BLE001 - os retornos nunca derrubam a busca
            traceback.print_exc(file=saida)
    print(f"===== fim: código {codigo} em {(datetime.now() - inicio).total_seconds():.0f} s =====", flush=True)
    return codigo


# ---------------------------------------------------------------- tela Início

@dataclass
class Situacao:
    texto: str
    problema: bool = False


def _data(texto: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(texto).astimezone() if texto else None
    except ValueError:
        return None


def _quando(momento: datetime, agora: datetime) -> str:
    dias = (agora.date() - momento.date()).days
    dia = "hoje" if dias == 0 else "ontem" if dias == 1 else f"{momento:%d/%m}"
    return f"{dia} às {momento:%H:%M}"


def situacao(agendada: bool | None, hora: str, agora: datetime | None = None) -> Situacao | None:
    """O que a tela Início mostra sobre a busca automática (None se não há busca agendada)."""
    if not agendada:
        return None
    agora = (agora or datetime.now()).astimezone()
    registro = ler().get("vagas rodada", {})
    instalada = _data(registro.get("instalada_em"))
    hora = registro.get("hora") or hora
    texto = f"Busca automática: todo dia às {hora}"
    if instalada is None:
        return Situacao(f"{texto}. Ela foi criada por uma versão antiga do agente e pode não rodar: recrie em "
                        "Configurações > \"Busca automática todo dia\" > Agendar.", problema=True)
    inicio, fim = _data(registro.get("inicio")), _data(registro.get("fim"))
    h, m = map(int, hora.split(":"))
    prevista = agora.replace(hour=h, minute=m, second=0, microsecond=0)
    if prevista + FOLGA > agora:
        prevista -= timedelta(days=1)  # a de hoje ainda pode estar rodando ou nem começou
    if prevista > instalada and (inicio is None or inicio < prevista - timedelta(minutes=1)):
        return Situacao(f"{texto}. A de {prevista:%d/%m} não rodou (o PC estava desligado?). Ela roda sozinha "
                        "assim que o PC ligar; se o aviso continuar, veja o registro.", problema=True)
    if fim is None and inicio is not None:
        if agora - inicio < timedelta(hours=2):
            return Situacao(f"{texto} · rodando agora (começou {_quando(inicio, agora)})")
        return Situacao(f"{texto}. A última ({_quando(inicio, agora)}) não terminou. Veja o registro.", problema=True)
    if fim is not None and registro.get("codigo") not in (0, None):
        return Situacao(f"{texto}. A última ({_quando(fim, agora)}) terminou com erro. Veja o registro.", problema=True)
    if fim is not None:
        return Situacao(f"{texto} · última: {_quando(fim, agora)} ✓")
    return Situacao(f"{texto} · a primeira será {proxima_vez(hora, agora.replace(tzinfo=None)):%d/%m} às {hora}")
