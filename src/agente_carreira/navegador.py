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


class SessaoNavegador:
    """Navegador visível com perfil próprio em data/navegador: o login que você fizer fica salvo."""

    def __init__(self) -> None:
        self._playwright = None
        self._contexto = None
        self.pagina = None

    def __enter__(self) -> "SessaoNavegador":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        pasta = diretorio_dados() / PASTA_PERFIL_NAVEGADOR
        pasta.mkdir(parents=True, exist_ok=True)
        self._contexto = self._playwright.chromium.launch_persistent_context(str(pasta), headless=False)
        self.pagina = self._contexto.pages[0] if self._contexto.pages else self._contexto.new_page()
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._contexto is not None:
                self._contexto.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()
