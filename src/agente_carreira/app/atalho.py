"""Ícone do app e atalho na Área de Trabalho (Windows)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NOME_APP = "Agente de Carreira"
ARQUIVO_ICONE = "agente.ico"


def raiz_do_projeto() -> Path:
    """Pasta com o pyproject.toml; é dela que o agente lê data/ (quando AGENTE_CARREIRA_DATA não está definido)."""
    candidata = Path(__file__).resolve().parents[3]
    return candidata if (candidata / "pyproject.toml").is_file() else Path.cwd()


def caminho_icone() -> Path:
    from ..storage import diretorio_dados

    return diretorio_dados() / "app" / ARQUIVO_ICONE


def criar_icone(destino: Path) -> Path:
    """Ícone simples (maleta verde com 'AC'), gerado com o Pillow que já vem com o fpdf2."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, 248, 248), radius=56, fill=(38, 99, 72, 255))
    d.rounded_rectangle((92, 44, 164, 84), radius=14, outline=(236, 244, 239, 255), width=12)
    d.rounded_rectangle((40, 76, 216, 208), radius=24, fill=(236, 244, 239, 255))
    fonte = None
    for nome in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            fonte = ImageFont.truetype(nome, 84)
            break
        except OSError:
            continue
    d.text((128, 144), "AC", fill=(38, 99, 72, 255), font=fonte or ImageFont.load_default(), anchor="mm")
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return destino


def script_atalho() -> str:
    """PowerShell que cria o .lnk; os caminhos vêm por variáveis de ambiente (acentos e espaços sem problema)."""
    return (
        "$ErrorActionPreference = 'Stop'; "
        "$desktop = [Environment]::GetFolderPath('Desktop'); "
        "$lnk = Join-Path $desktop ($env:AGENTE_NOME + '.lnk'); "
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk); "
        "$s.TargetPath = $env:AGENTE_ALVO; $s.Arguments = $env:AGENTE_ARGS; "
        "$s.WorkingDirectory = $env:AGENTE_RAIZ; $s.IconLocation = $env:AGENTE_ICONE; "
        "$s.Description = 'Abre o agente de carreira'; $s.Save(); Write-Output $lnk"
    )


def scripts_do_venv() -> Path:
    """Pasta Scripts do venv do projeto (não a do Python que está rodando, que pode ser o base)."""
    venv = raiz_do_projeto() / ".venv"
    return venv / ("Scripts" if sys.platform == "win32" else "bin") if venv.is_dir() else Path(sys.executable).parent


def _python_base_sem_console() -> Path | None:
    """pythonw.exe do Python base, lido do pyvenv.cfg do venv."""
    cfg = raiz_do_projeto() / ".venv" / "pyvenv.cfg"
    if not cfg.is_file():
        return None
    for linha in cfg.read_text(encoding="utf-8").splitlines():
        chave, _, valor = linha.partition("=")
        if chave.strip() == "home":
            candidato = Path(valor.strip()) / "pythonw.exe"
            return candidato if candidato.is_file() else None
    return None


def script_partida(site_packages: Path, raiz: Path) -> str:
    return (
        "# Gerado por 'agente atalho': abre o app sem console (Python base + pacotes do venv do projeto).\n"
        "import os\nimport site\n\n"
        f"site.addsitedir({str(site_packages)!r})\n"
        f"os.chdir({str(raiz)!r})\n\n"
        "from agente_carreira.app import main\n\nmain()\n"
    )


def lancador() -> tuple[Path, str]:
    """O que abre a janela sem nenhum console junto.

    No Windows, o pythonw.exe e o agente-app.exe do venv são lançadores que acabam num python.exe, e o
    Windows 11 abre um terminal junto. O pythonw.exe do Python base não tem console: ele roda um script
    de partida (em data/app, fora do git) que carrega os pacotes do venv.
    """
    base = _python_base_sem_console()
    site_packages = raiz_do_projeto() / ".venv" / "Lib" / "site-packages"
    if base is not None and site_packages.is_dir():
        partida = caminho_icone().with_name("iniciar.pyw")
        partida.parent.mkdir(parents=True, exist_ok=True)
        partida.write_text(script_partida(site_packages, raiz_do_projeto()), encoding="utf-8")
        return base, f'"{partida}"'
    scripts = scripts_do_venv()
    for nome, argumentos in (("agente-app.exe", ""), ("pythonw.exe", "-m agente_carreira.app")):
        if (scripts / nome).is_file():
            return scripts / nome, argumentos
    raise RuntimeError(f"Nem agente-app.exe nem pythonw.exe em {scripts}; rode 'uv sync'.")


def criar_atalho() -> Path:
    if sys.platform != "win32":
        raise RuntimeError("O atalho na Área de Trabalho é só para Windows; use 'uv run agente-app'.")
    alvo, argumentos = lancador()
    icone = criar_icone(caminho_icone())
    ambiente = dict(os.environ, AGENTE_NOME=NOME_APP, AGENTE_ALVO=str(alvo), AGENTE_ARGS=argumentos,
                    AGENTE_RAIZ=str(raiz_do_projeto()), AGENTE_ICONE=str(icone))
    resultado = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script_atalho()],
                               env=ambiente, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode != 0:
        raise RuntimeError(f"Falha ao criar o atalho: {(resultado.stderr or resultado.stdout).strip()}")
    return Path(resultado.stdout.strip().splitlines()[-1])
