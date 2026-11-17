"""App de janela do agente: botões para as ações do dia a dia e atalho na Área de Trabalho.

Cada ação abre uma janela de console com o comando correspondente da CLI, porque
muitos comandos pedem confirmação (RN-01): nada acontece sem você ver e responder.
Abra com o atalho criado por 'agente atalho' ou com 'uv run agente-app'.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

NOME_APP = "Agente de Carreira"
ARQUIVO_ICONE = "agente.ico"
URL_EXPORTACAO_LINKEDIN = "https://www.linkedin.com/mypreferences/d/download-my-data"
COMO_EXPORTAR_LINKEDIN = (
    "O agente não faz login no LinkedIn: assim sua conta não corre risco de restrição (RN-04). "
    "Seus dados entram pela exportação oficial:\n\n"
    "1. No LinkedIn: Eu → Configurações e privacidade → Privacidade de dados → Obter uma cópia dos seus dados.\n"
    "2. Marque o pacote completo (ou Perfil, Cargos, Formação, Competências e Conexões) e solicite.\n"
    "3. O LinkedIn manda o link por e-mail (de minutos a 24 h). Baixe o ZIP.\n\n"
    "Você já tem o ZIP?\n\nSim = escolher o arquivo · Não = abrir a página do LinkedIn para pedir"
)


def raiz_do_projeto() -> Path:
    """Pasta com o pyproject.toml; é dela que o agente lê data/ (quando AGENTE_CARREIRA_DATA não está definido)."""
    candidata = Path(__file__).resolve().parents[2]
    return candidata if (candidata / "pyproject.toml").is_file() else Path.cwd()


def python_console() -> str:
    """O python.exe ao lado do pythonw.exe que roda a janela (o console precisa dele)."""
    exe = Path(sys.executable)
    console = exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe
    return str(console if console.is_file() else exe)


# ---------------------------------------------------------------- ações

@dataclass(frozen=True)
class Acao:
    rotulo: str
    args: tuple[str, ...] = ()
    escolher: str | None = None     # "vaga", "candidatura", "url" ou "arquivo": pergunta antes de rodar


GRUPOS: list[tuple[str, list[Acao]]] = [
    ("Hoje", [
        Acao("Buscar vagas agora", ("vagas", "rodada")),
        Acao("Resumo do dia", ("vagas", "resumo")),
        Acao("Lembretes do funil", ("funil", "lembretes")),
        Acao("Fila de aprovações", ("fila", "revisar")),
        Acao("Ler e-mails de retorno", ("funil", "emails")),
    ]),
    ("Vagas e candidaturas", [
        Acao("Listar vagas", ("vagas", "listar")),
        Acao("Ver uma vaga…", ("vagas", "ver"), escolher="vaga"),
        Acao("Candidatar-me…", ("candidatar",), escolher="vaga"),
        Acao("Adicionar vaga por link…", ("vagas", "link"), escolher="url"),
        Acao("Funil de candidaturas", ("funil",)),
        Acao("Preparar entrevista…", ("funil", "preparar"), escolher="candidatura"),
    ]),
    ("Perfil, CV e LinkedIn", [
        Acao("Ver perfil", ("perfil", "mostrar")),
        Acao("Validar perfil", ("perfil", "validar")),
        Acao("Importar currículo…", ("importar",), escolher="arquivo"),
        Acao("Conectar LinkedIn (ZIP)…", ("li", "conectar"), escolher="zip_linkedin"),
        Acao("Nota do CV (ATS)", ("cv", "nota")),
        Acao("Lacunas do CV", ("cv", "lacunas")),
        Acao("Auditar LinkedIn", ("li", "auditar")),
        Acao("Propor alterações no LinkedIn", ("li", "propor")),
    ]),
    ("Relatórios e operação", [
        Acao("Relatório semanal", ("relatorio", "semanal")),
        Acao("Exportar dados (CSV)", ("exportar",)),
        Acao("Critérios de aceitação", ("aceite",)),
        Acao("Tarefas", ("tarefas",)),
        Acao("Saúde dos adaptadores", ("saude",)),
        Acao("Configuração", ("config",)),
    ]),
]


def comando_console(args: list[str], python: str | None = None) -> list[str]:
    return [python or python_console(), "-m", "agente_carreira.app", "--executar", *args]


def abrir_console(args: list[str]) -> subprocess.Popen:
    """Roda 'agente ARGS' numa janela de console nova, que espera Enter para fechar."""
    criacao = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen(comando_console(args), cwd=raiz_do_projeto(), creationflags=criacao)


def executar_no_console(args: list[str]) -> int:
    """Ponto de entrada da janela de console: roda o comando e segura a janela aberta."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(f"{NOME_APP} — agente {' '.join(args)}")
    from typer.main import get_command

    from .cli import app

    from .storage import PerfilAusente

    print(f"> agente {' '.join(args)}\n")
    codigo = 0
    try:
        resultado = get_command(app).main(args=args, prog_name="agente", standalone_mode=False)
        codigo = resultado if isinstance(resultado, int) else 0
    except PerfilAusente as erro:
        print(erro)
        codigo = 1
    except KeyboardInterrupt:
        print("\nCancelado.")
    except SystemExit as saida:
        codigo = saida.code if isinstance(saida.code, int) else 0
    except Exception as erro:  # noqa: BLE001 - mostra o erro em vez de fechar a janela
        if type(erro).__name__ == "Abort":
            print("\nCancelado.")
        elif hasattr(erro, "format_message"):
            print(f"\nErro: {erro.format_message()}")
            codigo = 2
        else:
            print(f"\nErro inesperado: {type(erro).__name__}: {erro}")
            codigo = 1
    try:
        input("\nPressione Enter para fechar esta janela...")
    except EOFError:
        pass
    return codigo


# ---------------------------------------------------------------- situação (cabeçalho da janela)

def situacao() -> list[str]:
    """Linhas curtas com o que pede atenção agora; nunca levanta erro."""
    linhas: list[str] = []
    try:
        from .funil import vencidos
        from .radar.modelos import carregar_config
        from .relatorios import Dados, foi_aplicada
        from .storage import perfil_existe

        if not perfil_existe():
            return ["Sem perfil-mestre ainda: comece por \"Importar currículo…\" ou \"Conectar LinkedIn (ZIP)…\"."]
        dados = Dados.carregar()
        limiar = carregar_config().limiar_alerta
        aplicadas = {c.vaga_id for c in dados.candidaturas.itens if foi_aplicada(c)}
        boas = [v for v in dados.base.itens if v.status in ("no_resumo", "salva") and v.nota >= limiar
                and not v.risco and v.id not in aplicadas]
        abertas = [c for c in dados.candidaturas.itens if foi_aplicada(c) and not c.encerrada]
        ultima = dados.base.ultima_rodada
        quando = ultima.astimezone().strftime("%d/%m %H:%M") if ultima else "nunca"
        linhas.append(f"Última busca de vagas: {quando} · {len(boas)} vaga(s) com nota ≥ {limiar} sem candidatura")
        linhas.append(f"{len(abertas)} candidatura(s) em andamento · {len(vencidos(dados.lembretes))} lembrete(s) para agora · "
                      f"{len(dados.fila)} item(ns) na fila de aprovações")
        parados = sorted(n for n, a in dados.saude.adaptadores.items() if a.status == "parado")
        if parados:
            linhas.append(f"Adaptadores parados: {', '.join(parados)} (veja \"Saúde dos adaptadores\")")
    except Exception as erro:  # noqa: BLE001
        linhas.append(f"Não foi possível ler a situação: {type(erro).__name__}: {erro}")
    return linhas


def opcoes_de_vaga() -> list[tuple[str, str]]:
    from .radar.modelos import carregar_base

    vagas = [v for v in carregar_base().itens if v.status not in ("eliminada", "expirada", "descartada")]
    vagas.sort(key=lambda v: -v.nota)
    return [(v.id, f"{v.nota:>3} · {v.titulo} — {v.empresa or '?'}{' ⚠' if v.risco else ''}") for v in vagas]


def opcoes_de_candidatura() -> list[tuple[str, str]]:
    from .candidaturas import NOMES_ETAPA, carregar_candidaturas

    abertas = [c for c in carregar_candidaturas().itens if not c.encerrada]
    return [(c.id, f"{NOMES_ETAPA[c.status]} · {c.vaga_titulo} — {c.empresa or '?'}") for c in abertas]


# ---------------------------------------------------------------- ícone e atalho

def criar_icone(destino: Path) -> Path:
    """Ícone simples (maleta verde com 'AC'), gerado com o Pillow que já vem com o fpdf2."""
    from PIL import Image, ImageDraw, ImageFont

    tamanho = 256
    img = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
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
    fonte = fonte or ImageFont.load_default()
    d.text((128, 144), "AC", fill=(38, 99, 72, 255), font=fonte, anchor="mm")
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
        "$s.TargetPath = $env:AGENTE_ALVO; $s.Arguments = '-m agente_carreira.app'; "
        "$s.WorkingDirectory = $env:AGENTE_RAIZ; $s.IconLocation = $env:AGENTE_ICONE; "
        "$s.Description = 'Abre o agente de carreira'; $s.Save(); Write-Output $lnk"
    )


def criar_atalho() -> Path:
    if sys.platform != "win32":
        raise RuntimeError("O atalho na Área de Trabalho é só para Windows; use 'uv run agente-app'.")
    from .storage import diretorio_dados

    raiz = raiz_do_projeto()
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise RuntimeError(f"pythonw.exe não encontrado ao lado de {sys.executable}.")
    icone = criar_icone(diretorio_dados() / "app" / ARQUIVO_ICONE)
    ambiente = dict(os.environ, AGENTE_NOME=NOME_APP, AGENTE_ALVO=str(pythonw), AGENTE_RAIZ=str(raiz),
                    AGENTE_ICONE=str(icone))
    resultado = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script_atalho()],
                               env=ambiente, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode != 0:
        raise RuntimeError(f"Falha ao criar o atalho: {(resultado.stderr or resultado.stdout).strip()}")
    return Path(resultado.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------- janela

def _escolher(janela, titulo: str, opcoes: list[tuple[str, str]]) -> str | None:
    import tkinter as tk
    from tkinter import ttk

    if not opcoes:
        from tkinter import messagebox

        messagebox.showinfo(NOME_APP, "Nada para escolher ainda.", parent=janela)
        return None
    dialogo = tk.Toplevel(janela)
    dialogo.title(titulo)
    dialogo.transient(janela)
    dialogo.grab_set()
    escolhido: list[str] = []
    lista = tk.Listbox(dialogo, width=80, height=min(len(opcoes), 15), activestyle="dotbox", font=("Segoe UI", 10))
    for _, rotulo in opcoes:
        lista.insert("end", rotulo)
    lista.selection_set(0)
    lista.grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 6), sticky="nsew")

    def ok(_evento=None):
        if lista.curselection():
            escolhido.append(opcoes[lista.curselection()[0]][0])
        dialogo.destroy()

    lista.bind("<Double-Button-1>", ok)
    lista.bind("<Return>", ok)
    ttk.Button(dialogo, text="Escolher", command=ok).grid(row=1, column=0, padx=12, pady=(0, 12), sticky="e")
    ttk.Button(dialogo, text="Cancelar", command=dialogo.destroy).grid(row=1, column=1, padx=(0, 12), pady=(0, 12), sticky="w")
    lista.focus_set()
    janela.wait_window(dialogo)
    return escolhido[0] if escolhido else None


def abrir_janela() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    if sys.platform == "win32":
        try:  # texto nítido em telas com escala (125%, 150%...)
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    janela = tk.Tk()
    janela.title(NOME_APP)
    janela.minsize(760, 520)
    try:
        from .storage import diretorio_dados

        icone = diretorio_dados() / "app" / ARQUIVO_ICONE
        if not icone.is_file():
            criar_icone(icone)
        janela.iconbitmap(default=str(icone))
    except Exception:  # noqa: BLE001 - sem ícone, a janela abre igual
        pass
    estilo = ttk.Style(janela)
    if "vista" in estilo.theme_names():
        estilo.theme_use("vista")
    estilo.configure("Titulo.TLabel", font=("Segoe UI Semibold", 16))
    estilo.configure("Situacao.TLabel", font=("Segoe UI", 10))
    estilo.configure("Rodape.TLabel", font=("Segoe UI", 9), foreground="#666666")

    topo = ttk.Frame(janela, padding=(16, 14, 16, 6))
    topo.pack(fill="x")
    ttk.Label(topo, text=NOME_APP, style="Titulo.TLabel").pack(anchor="w")
    texto_situacao = tk.StringVar(value="Carregando…")
    ttk.Label(topo, textvariable=texto_situacao, style="Situacao.TLabel", justify="left").pack(anchor="w", pady=(4, 0))

    def atualizar(_evento=None):
        texto_situacao.set("\n".join(situacao()))

    def rodar(acao: Acao):
        args = list(acao.args)
        try:
            if acao.escolher == "vaga":
                escolhido = _escolher(janela, acao.rotulo.rstrip("…"), opcoes_de_vaga())
            elif acao.escolher == "candidatura":
                escolhido = _escolher(janela, acao.rotulo.rstrip("…"), opcoes_de_candidatura())
            elif acao.escolher == "url":
                escolhido = simpledialog.askstring(NOME_APP, "Link da vaga:", parent=janela)
            elif acao.escolher == "arquivo":
                escolhido = filedialog.askopenfilename(
                    parent=janela, title="Escolha o currículo",
                    filetypes=[("Currículo", "*.pdf *.docx *.zip *.txt"), ("Todos os arquivos", "*.*")])
            elif acao.escolher == "zip_linkedin":
                tem_zip = messagebox.askyesnocancel(NOME_APP, COMO_EXPORTAR_LINKEDIN, parent=janela)
                if tem_zip is None:
                    return
                if not tem_zip:
                    webbrowser.open(URL_EXPORTACAO_LINKEDIN)
                    return
                escolhido = filedialog.askopenfilename(
                    parent=janela, title="Escolha o ZIP baixado do LinkedIn",
                    filetypes=[("Exportação do LinkedIn", "*.zip")])
            else:
                escolhido = ""
        except Exception as erro:  # noqa: BLE001
            messagebox.showerror(NOME_APP, f"{type(erro).__name__}: {erro}", parent=janela)
            return
        if escolhido is None or (acao.escolher and not str(escolhido).strip()):
            return
        if escolhido:
            args.append(str(escolhido).strip())
        abrir_console(args)

    def abrir_painel():
        try:
            from .relatorios import salvar_painel_html

            webbrowser.open(salvar_painel_html().resolve().as_uri())
        except Exception as erro:  # noqa: BLE001
            messagebox.showerror(NOME_APP, f"Não deu para gerar o painel: {erro}", parent=janela)

    def abrir_dados():
        from .storage import diretorio_dados

        pasta = diretorio_dados()
        pasta.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(pasta)
        else:
            webbrowser.open(pasta.as_uri())

    def abrir_terminal():
        scripts = Path(sys.executable).parent
        ambiente = dict(os.environ, PATH=f"{scripts}{os.pathsep}{os.environ.get('PATH', '')}")
        subprocess.Popen(["cmd.exe", "/k", f"title {NOME_APP} & echo Digite: agente --help"],
                         cwd=raiz_do_projeto(), env=ambiente, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))

    grade = ttk.Frame(janela, padding=(16, 6, 16, 6))
    grade.pack(fill="both", expand=True)
    for indice, (titulo, acoes) in enumerate(GRUPOS):
        quadro = ttk.LabelFrame(grade, text=titulo, padding=10)
        quadro.grid(row=indice // 2, column=indice % 2, padx=6, pady=6, sticky="nsew")
        for acao in acoes:
            botao = ttk.Button(quadro, text=acao.rotulo, command=lambda a=acao: rodar(a))
            botao.pack(fill="x", pady=2)
        if titulo == "Relatórios e operação":
            ttk.Button(quadro, text="Abrir painel no navegador", command=abrir_painel).pack(fill="x", pady=2)
    for coluna in (0, 1):
        grade.columnconfigure(coluna, weight=1)

    rodape = ttk.Frame(janela, padding=(16, 4, 16, 14))
    rodape.pack(fill="x")
    ttk.Button(rodape, text="Atualizar situação", command=atualizar).pack(side="left")
    ttk.Button(rodape, text="Abrir pasta de dados", command=abrir_dados).pack(side="left", padx=6)
    ttk.Button(rodape, text="Terminal do agente", command=abrir_terminal).pack(side="left")
    ttk.Label(rodape, text="Cada ação abre um console; nada é enviado sem a sua confirmação.",
              style="Rodape.TLabel").pack(side="right")

    ultima_atualizacao = [datetime.now(timezone.utc)]

    def ao_focar(_evento):
        agora = datetime.now(timezone.utc)
        if (agora - ultima_atualizacao[0]).total_seconds() > 5:  # ao voltar de um console, atualiza
            ultima_atualizacao[0] = agora
            atualizar()

    janela.bind("<FocusIn>", ao_focar)
    janela.after(50, atualizar)
    janela.mainloop()


def main() -> None:
    if os.environ.get("AGENTE_CARREIRA_DATA") is None:
        os.chdir(raiz_do_projeto())  # data/ do projeto, mesmo aberto pelo atalho
    if len(sys.argv) > 1 and sys.argv[1] == "--executar":
        raise SystemExit(executar_no_console(sys.argv[2:]))
    abrir_janela()


if __name__ == "__main__":
    main()
