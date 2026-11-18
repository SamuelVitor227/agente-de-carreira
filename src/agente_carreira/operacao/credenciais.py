"""Configuração do e-mail sem terminal: alertas de vagas (IMAP) e avisos do agente (SMTP).

As credenciais continuam só em variáveis de ambiente (RNF-01): no Windows, gravadas nas variáveis do seu
usuário (setx), que valem também para a busca agendada. Nada vai para data/ nem para o git.
Use uma "senha de app" do provedor, nunca a senha principal da conta.
"""

from __future__ import annotations

import imaplib
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta

PROVEDORES = {
    "gmail": ("Gmail", "imap.gmail.com", "smtp.gmail.com"),
    "outlook": ("Outlook / Hotmail", "outlook.office365.com", "smtp.office365.com"),
    "yahoo": ("Yahoo", "imap.mail.yahoo.com", "smtp.mail.yahoo.com"),
}
COMO_CRIAR_SENHA_DE_APP = {
    "gmail": "Conta Google → Segurança → Verificação em duas etapas (ligada) → Senhas de app → crie uma para 'Agente'.",
    "outlook": "Conta Microsoft → Segurança → Opções avançadas de segurança → Senhas de aplicativo.",
    "yahoo": "Yahoo → Informações da conta → Segurança da conta → Gerar senha de app.",
}


@dataclass
class ConfigEmail:
    provedor: str
    email: str
    senha: str
    pasta: str = "INBOX"
    avisos: bool = True       # também usar para mandar os avisos do agente (SMTP)


def variaveis(cfg: ConfigEmail) -> dict[str, str]:
    if cfg.provedor not in PROVEDORES:
        raise ValueError(f"Provedor desconhecido: {cfg.provedor}. Use: {', '.join(PROVEDORES)}.")
    if "@" not in cfg.email or not cfg.senha.strip():
        raise ValueError("Informe o e-mail completo e a senha de app.")
    _, imap, smtp = PROVEDORES[cfg.provedor]
    valores = {"AGENTE_IMAP_HOST": imap, "AGENTE_IMAP_USUARIO": cfg.email.strip(),
               "AGENTE_IMAP_SENHA": cfg.senha.strip().replace(" ", ""), "AGENTE_IMAP_PASTA": cfg.pasta.strip() or "INBOX"}
    if cfg.avisos:
        valores |= {"AGENTE_SMTP_HOST": smtp, "AGENTE_SMTP_PORTA": "587", "AGENTE_SMTP_USUARIO": cfg.email.strip(),
                    "AGENTE_SMTP_SENHA": valores["AGENTE_IMAP_SENHA"]}
    return valores


def gravar_variaveis_do_usuario(valores: dict[str, str], *, executar=subprocess.run) -> None:
    """Grava nas variáveis do usuário do Windows (valem para novos processos) e no processo atual."""
    if sys.platform == "win32":
        sem_janela = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for nome, valor in valores.items():
            resultado = executar(["setx", nome, valor], capture_output=True, text=True, creationflags=sem_janela)
            if resultado.returncode != 0:
                raise RuntimeError(f"Não consegui gravar {nome}: {(resultado.stderr or resultado.stdout).strip()}")
    os.environ.update(valores)


def testar_imap(host: str, usuario: str, senha: str, pasta: str, *, imap_factory=imaplib.IMAP4_SSL) -> int:
    """Entra em modo somente leitura e conta os e-mails da última semana na pasta (RNF-03)."""
    conexao = imap_factory(host)
    try:
        conexao.login(usuario, senha)
        tipo, _ = conexao.select(f'"{pasta}"', readonly=True)
        if tipo != "OK":
            raise RuntimeError(f"a pasta '{pasta}' não existe nessa caixa de e-mail")
        desde = date.today() - timedelta(days=7)
        meses = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        tipo, dados = conexao.search(None, "SINCE", f"{desde.day:02d}-{meses[desde.month - 1]}-{desde.year}")
        return len((dados[0] or b"").split()) if tipo == "OK" else 0
    finally:
        try:
            conexao.logout()
        except Exception:  # noqa: BLE001
            pass


def email_configurado() -> str | None:
    """O e-mail lido nos alertas, se configurado (variáveis do processo ou do usuário no Windows)."""
    usuario = os.environ.get("AGENTE_IMAP_USUARIO")
    if usuario or sys.platform != "win32":
        return usuario
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as chave:
            return winreg.QueryValueEx(chave, "AGENTE_IMAP_USUARIO")[0] or None
    except OSError:
        return None


def carregar_variaveis_do_usuario() -> None:
    """No Windows, traz para o processo as variáveis AGENTE_* gravadas depois que o app abriu."""
    if sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as chave:
            i = 0
            while True:
                try:
                    nome, valor, _ = winreg.EnumValue(chave, i)
                except OSError:
                    break
                if nome.upper().startswith("AGENTE_") and nome not in os.environ:
                    os.environ[nome] = str(valor)
                i += 1
    except OSError:
        pass
