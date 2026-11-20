"""Modo assistido com Playwright (seção 2.2): o agente preenche no navegador do usuário e para antes de salvar.

Regras que valem sempre:
- login, 2FA, CAPTCHA, senha e aceite de termos são do usuário (RN-03): o agente
  abre a página e espera;
- antes de preencher, confere se os campos esperados existem; se não, para e
  volta para o copiloto (RNF-08, RF-OP-07);
- ritmo humano: intervalo entre ações e limite por sessão (RN-05);
- o agente nunca clica em salvar, enviar ou candidatar-se (RN-01, RF-CA-03):
  preenche, tira uma captura de tela para a auditoria e devolve o controle;
- no LinkedIn, só se o usuário ligar o modo assistido, ciente do risco (RN-04).

Os campos são localizados pelo rótulo acessível da página (o texto do <label>,
aria-label ou placeholder), com sinônimos configuráveis (RNF-14).
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .operacao.saude import LayoutMudou
from .storage import diretorio_dados

PASTA_PERFIL_NAVEGADOR = "navegador"

# Rótulos que cada campo costuma ter nos formulários (configuração, não código).
SINONIMOS: dict[str, list[str]] = {
    "nome": ["Nome completo", "Nome"],
    "email": ["E-mail", "Email", "Endereço de e-mail"],
    "telefone": ["Telefone", "Celular", "Telefone celular", "WhatsApp"],
    "cidade": ["Cidade"],
    "uf": ["Estado", "UF"],
    "pais": ["País"],
    "linkedin": ["LinkedIn", "Perfil do LinkedIn", "URL do LinkedIn"],
    "github": ["GitHub", "Perfil do GitHub"],
    "portfolio": ["Portfólio", "Site pessoal", "Site"],
    "resumo": ["Resumo profissional", "Resumo", "Sobre você", "Sobre"],
    "apresentacao": ["Apresente-se", "Apresentação", "Carta de apresentação"],
    "habilidades": ["Habilidades", "Competências", "Conhecimentos"],
    "idiomas": ["Idiomas"],
    "pretensao": ["Pretensão salarial", "Expectativa salarial"],
    "carga_horaria": ["Carga horária", "Disponibilidade de horário"],
    "mensagem": ["Mensagem", "Mensagem ao recrutador", "Carta de apresentação"],
}
# Campos estruturados (várias entradas com subcampos) ficam no copiloto.
CAMPOS_SO_COPILOTO = {"experiencias", "formacao", "certificacoes", "cpf"}


@dataclass
class CampoParaPreencher:
    id: str
    rotulo: str
    valor: str | None
    obrigatorio: bool = False
    rotulos_extras: list[str] = field(default_factory=list)
    arquivo: bool = False


@dataclass
class ResultadoAssistido:
    preenchidos: list[str] = field(default_factory=list)
    para_copiloto: list[str] = field(default_factory=list)   # o usuário completa (estruturado, manual, não achado)
    captura: Path | None = None
    parou_no_limite: bool = False


def rotulos_do_campo(campo: CampoParaPreencher) -> list[str]:
    return list(dict.fromkeys(campo.rotulos_extras + [campo.rotulo] + SINONIMOS.get(campo.id, [])))


def localizar(pagina, campo: CampoParaPreencher):
    """Primeiro elemento único que corresponde ao rótulo, aria-label ou placeholder do campo."""
    if campo.arquivo:
        alvo = pagina.locator("input[type=file]")
        return alvo.first if alvo.count() >= 1 else None
    for rotulo in rotulos_do_campo(campo):
        # Rótulo exato (aceita "*" de obrigatório, ":" e caixa diferente): "Nome" nunca casa com "Nome do pet".
        exato = re.compile(rf"^\s*{re.escape(rotulo)}\s*\*?\s*:?\s*$", re.IGNORECASE)
        for alvo in (pagina.get_by_label(exato), pagina.get_by_placeholder(exato)):
            try:
                if alvo.count() == 1:
                    return alvo
            except Exception:  # noqa: BLE001 - seletor inválido para esta página
                continue
    return None


def verificar_layout(pagina, campos: list[CampoParaPreencher]) -> list[str]:
    """RNF-08: campos obrigatórios preenchíveis que não estão na página."""
    return [c.rotulo for c in campos if c.obrigatorio and c.valor and c.id not in CAMPOS_SO_COPILOTO
            and localizar(pagina, c) is None]


def preencher(
    pagina, campos: list[CampoParaPreencher], *, limite_acoes: int, intervalo_segundos: float,
    dormir: Callable[[float], None] = time.sleep, pasta_capturas: Path | None = None,
) -> ResultadoAssistido:
    """Preenche os campos sem clicar em salvar/enviar. Levanta LayoutMudou se faltar campo obrigatório."""
    if faltando := verificar_layout(pagina, campos):
        raise LayoutMudou(f"campos esperados não encontrados na página: {', '.join(faltando)}")
    resultado = ResultadoAssistido()
    acoes = 0
    for campo in campos:
        if not campo.valor or campo.id in CAMPOS_SO_COPILOTO:
            resultado.para_copiloto.append(campo.rotulo)
            continue
        if acoes >= limite_acoes:
            resultado.parou_no_limite = True
            resultado.para_copiloto.append(campo.rotulo)
            continue
        alvo = localizar(pagina, campo)
        if alvo is None:
            resultado.para_copiloto.append(campo.rotulo)
            continue
        if acoes:
            dormir(intervalo_segundos)  # RN-05: ritmo humano
        if campo.arquivo:
            alvo.set_input_files(campo.valor)
        else:
            alvo.fill(campo.valor)
        acoes += 1
        resultado.preenchidos.append(campo.rotulo)
    if pasta_capturas is not None:
        pasta_capturas.mkdir(parents=True, exist_ok=True)
        resultado.captura = pasta_capturas / f"assistido-{datetime.now():%Y%m%d-%H%M%S}.png"
        pagina.screenshot(path=str(resultado.captura), full_page=True)
    return resultado


def playwright_disponivel() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


class NavegadorOcupado(Exception):
    """O navegador do agente já está aberto por outra tarefa (o perfil só aceita um uso por vez)."""

    def __init__(self, uso: str | None = None) -> None:
        self.uso = uso
        onde = f"aberto em: {uso}" if uso else "aberto em outra tarefa"
        super().__init__(f"O navegador do agente já está {onde}. Feche aquela janela do navegador (ou espere a "
                         "tarefa terminar) e tente de novo.")


def _arquivo_dono() -> Path:
    return diretorio_dados() / "navegador.dono"


def uso_atual_do_navegador() -> str | None:
    """O que está usando o navegador do agente agora (se o processo dono ainda existe)."""
    import json

    from .operacao.andamento import processo_vivo

    try:
        dono = json.loads(_arquivo_dono().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dono.get("uso") if processo_vivo(int(dono.get("pid", 0))) else None


class _Trava:
    """Trava de arquivo entre processos: o app, a busca agendada e o terminal não abrem o perfil juntos."""

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        self._arquivo = None

    def adquirir(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo = open(self.caminho, "a+b")  # noqa: SIM115 - fica aberto enquanto a sessão durar
        try:
            if os.name == "nt":
                import msvcrt

                arquivo.seek(0)
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            arquivo.close()
            raise NavegadorOcupado(uso_atual_do_navegador()) from None
        self._arquivo = arquivo

    def soltar(self) -> None:
        if self._arquivo is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._arquivo.seek(0)
                msvcrt.locking(self._arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._arquivo.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._arquivo.close()
            self._arquivo = None


def fechado_pela_pessoa(erro: BaseException) -> bool:
    """A janela do navegador foi fechada no meio da tarefa: não é defeito do site, não para a fonte."""
    return type(erro).__name__ == "TargetClosedError" or "has been closed" in str(erro)


def erro_curto(erro: BaseException, limite: int = 220) -> str:
    """Primeira linha útil de um erro (o Playwright anexa o log inteiro do Chromium)."""
    linha = next((l.strip() for l in str(erro).splitlines() if l.strip()), type(erro).__name__)
    return linha if len(linha) <= limite else linha[:limite].rstrip() + "…"


ARQUIVO_SERVIDOR = "navegador.servidor"   # {"porta": ..., "pid": ...} do navegador compartilhado
ARQUIVO_SESSOES = "navegador.sessoes"     # tarefas usando o navegador agora: {"pid-n": "uso"}


@dataclass
class _Visao:
    """Só as abas desta tarefa (as outras tarefas têm as delas no mesmo navegador)."""

    sessao: "SessaoNavegador"

    @property
    def pages(self) -> list:
        return self.sessao.abas()


def _trava_curta(tentativas: int = 60):
    """Trava entre processos por pouco tempo (abrir o navegador, anotar sessões); espera a vez em vez de falhar."""
    trava = _Trava(diretorio_dados() / "navegador.trava")
    for _ in range(tentativas):
        try:
            trava.adquirir()
            return trava
        except NavegadorOcupado:
            time.sleep(0.25)
    raise NavegadorOcupado(uso_atual_do_navegador())


def _ler_json(nome: str) -> dict:
    import json

    try:
        return json.loads((diretorio_dados() / nome).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


ARQUIVO_CONEXOES = "navegador.log"
LINHAS_CONEXOES = 400


def registrar_conexao(texto: str) -> None:
    """RF-EV-18: cada tarefa que entra ou sai do navegador compartilhado fica registrada (data/navegador.log)."""
    from datetime import datetime

    caminho = diretorio_dados() / ARQUIVO_CONEXOES
    try:
        antigas = caminho.read_text(encoding="utf-8").splitlines(keepends=True)[-LINHAS_CONEXOES:] if caminho.is_file() else []
        from .arquivos import gravar_texto

        gravar_texto(caminho, "".join(antigas) + f"{datetime.now():%d/%m/%Y %H:%M:%S}  {texto}\n")
    except OSError:
        pass


def _gravar_json(nome: str, dados: dict) -> None:
    import json

    from .arquivos import gravar_texto

    gravar_texto(diretorio_dados() / nome, json.dumps(dados, ensure_ascii=False))


def _cdp_vivo(porta: int) -> bool:
    from urllib.request import urlopen

    try:
        with urlopen(f"http://127.0.0.1:{porta}/json/version", timeout=1.5) as resposta:
            return resposta.status == 200
    except OSError:
        return False


def _porta_livre() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _iniciar_servidor(executavel: str, pasta: Path) -> int:
    """Abre o Chromium do agente (perfil com seus logins) como processo próprio, aceitando várias tarefas por abas."""
    import subprocess
    import sys

    porta = _porta_livre()
    criacao = 0
    if sys.platform == "win32":
        criacao = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    processo = subprocess.Popen(
        [executavel, f"--user-data-dir={pasta}", f"--remote-debugging-port={porta}", "--remote-debugging-address=127.0.0.1",
         "--no-first-run", "--no-default-browser-check", "--disable-features=Translate", "about:blank"],
        creationflags=criacao, close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):  # até ~20 s para o navegador subir
        if _cdp_vivo(porta):
            _gravar_json(ARQUIVO_SERVIDOR, {"porta": porta, "pid": processo.pid})
            return porta
        time.sleep(0.25)
    processo.kill()
    raise RuntimeError("o navegador do agente não abriu a tempo")


class SessaoNavegador:
    """Uma aba própria no navegador do agente (perfil em data/navegador: os logins que você fizer ficam salvos).

    Várias tarefas ao mesmo tempo: o navegador do agente fica aberto como um só programa e cada tarefa abre a
    sua aba (busca, candidatura, Outlook, LinkedIn...). Quando a última tarefa termina, ele fecha sozinho.
    """

    def __init__(self, uso: str = "uma tarefa do agente") -> None:
        self.uso = uso
        self._playwright = None
        self._contexto = None
        self._navegador = None
        self._trava: _Trava | None = None
        self._chave: str | None = None
        self._abas: list = []
        self.pagina = None

    # -- abas desta tarefa
    def abas(self) -> list:
        return [p for p in self._abas if not p.is_closed()]

    def aberta(self) -> bool:
        """True enquanto alguma aba desta tarefa estiver aberta (você fecha quando terminar)."""
        try:
            return bool(self.abas())
        except Exception:  # noqa: BLE001 - navegador fechado
            return False

    def visao(self) -> _Visao:
        return _Visao(self)

    def nova_aba(self):
        aba = self._contexto.new_page()
        self._acompanhar(aba)
        return aba

    def _acompanhar(self, aba) -> None:
        self._abas.append(aba)
        aba.on("popup", self._acompanhar)  # janelas que o site abre a partir desta aba também são desta tarefa

    def __enter__(self) -> "SessaoNavegador":
        from playwright.sync_api import sync_playwright

        pasta = diretorio_dados() / PASTA_PERFIL_NAVEGADOR
        pasta.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        try:
            trava = _trava_curta()
            try:
                servidor = _ler_json(ARQUIVO_SERVIDOR)
                porta = servidor.get("porta")
                if not porta or not _cdp_vivo(int(porta)):
                    porta = _iniciar_servidor(self._playwright.chromium.executable_path, pasta)
                self._navegador = self._playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
                sessoes = _ler_json(ARQUIVO_SESSOES)
                self._chave = f"{os.getpid()}-{id(self)}"
                sessoes[self._chave] = self.uso
                _gravar_json(ARQUIVO_SESSOES, sessoes)
                registrar_conexao(f"entrou: {self.uso} (processo {os.getpid()}, porta {porta}); "
                                  f"{len(sessoes)} tarefa(s) no navegador")
            finally:
                trava.soltar()
            self._contexto = self._navegador.contexts[0] if self._navegador.contexts else self._navegador.new_context()
            self._contexto.set_default_navigation_timeout(45_000)
            self.pagina = self._contexto.new_page()
            self._acompanhar(self.pagina)
            for vazia in [p for p in self._contexto.pages if p.url == "about:blank" and p is not self.pagina]:
                try:  # a aba em branco de quando o navegador abriu
                    vazia.close()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc) -> None:
        from .operacao.andamento import processo_vivo

        try:
            for aba in self.abas():
                aba.close()
        except Exception:  # noqa: BLE001 - você pode ter fechado o navegador inteiro
            pass
        try:
            ultima = False
            if self._chave:
                trava = _trava_curta()
                try:
                    sessoes = {k: v for k, v in _ler_json(ARQUIVO_SESSOES).items()
                               if k != self._chave and processo_vivo(int(k.split("-")[0]))}
                    _gravar_json(ARQUIVO_SESSOES, sessoes)
                    ultima = not sessoes
                    registrar_conexao(f"saiu: {self.uso} (processo {os.getpid()})"
                                      + ("; navegador fechado e porta de controle encerrada" if ultima else ""))
                finally:
                    trava.soltar()
            if ultima and self._navegador is not None:  # última tarefa: fecha o navegador do agente
                try:
                    self._navegador.new_browser_cdp_session().send("Browser.close")
                except Exception:  # noqa: BLE001 - já fechado
                    pass
        finally:
            if self._playwright is not None:
                self._playwright.stop()
            self._contexto = self._playwright = self._navegador = self._chave = None


class SessaoNavegadorExclusiva:
    """Modo antigo (um navegador só desta tarefa); fica como reserva."""

    def __init__(self, uso: str = "uma tarefa do agente") -> None:
        self.uso = uso
        self._playwright = None
        self._contexto = None
        self._trava: _Trava | None = None
        self.pagina = None

    def __enter__(self) -> "SessaoNavegadorExclusiva":
        import json
        from datetime import datetime

        from playwright.sync_api import sync_playwright

        pasta = diretorio_dados() / PASTA_PERFIL_NAVEGADOR
        pasta.mkdir(parents=True, exist_ok=True)
        self._trava = _Trava(diretorio_dados() / "navegador.trava")
        self._trava.adquirir()
        try:  # anota quem está usando, para o aviso de "navegador ocupado" dizer o quê
            _arquivo_dono().write_text(json.dumps({"uso": self.uso, "pid": os.getpid(),
                                                   "desde": datetime.now().isoformat(timespec="seconds")}),
                                       encoding="utf-8")
        except OSError:
            pass
        try:
            self._playwright = sync_playwright().start()
            self._contexto = self._playwright.chromium.launch_persistent_context(str(pasta), headless=False)
            self._contexto.set_default_navigation_timeout(45_000)
            self.pagina = self._contexto.pages[0] if self._contexto.pages else self._contexto.new_page()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._contexto is not None:
                self._contexto.close()
        except Exception:  # noqa: BLE001 - a janela pode já ter sido fechada pela pessoa
            pass
        finally:
            if self._playwright is not None:
                self._playwright.stop()
            if self._trava is not None:
                try:
                    _arquivo_dono().unlink(missing_ok=True)
                except OSError:
                    pass
                self._trava.soltar()
            self._contexto = self._playwright = self._trava = None
