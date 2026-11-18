"""Preenchimento automático das informações básicas ao navegar num site de vagas (Gupy e outros).

No navegador do agente, enquanto você navega no site:
- todo formulário que aparecer recebe nome, e-mail, telefone, cidade, estado, país e links do seu perfil;
- só campos VAZIOS: o que você digitou nunca é apagado, e um campo que você limpou não é preenchido de novo;
- nada de CPF (RN-08), senha, data de nascimento ou perguntas de diversidade: isso é seu;
- o agente nunca clica em salvar, enviar ou candidatar-se (RN-01);
- login, 2FA e CAPTCHA são seus (RN-03).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlparse

from .models import PerfilMestre
from .navegador import CampoParaPreencher, localizar

UFS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}
TIPOS_PROIBIDOS = {"password", "hidden", "file", "checkbox", "radio", "submit", "button"}


def campos_basicos(perfil: PerfilMestre) -> list[CampoParaPreencher]:
    c, links = perfil.contato, perfil.links
    partes = (c.nome or "").split()
    campos = [
        CampoParaPreencher(id="basico:nome_completo", rotulo="Nome completo", valor=c.nome,
                           rotulos_extras=["Nome completo", "Seu nome completo", "Full name"]),
        CampoParaPreencher(id="basico:nome", rotulo="Nome", valor=partes[0] if partes else None,
                           rotulos_extras=["Nome", "Primeiro nome", "First name"]),
        CampoParaPreencher(id="basico:sobrenome", rotulo="Sobrenome", valor=" ".join(partes[1:]) or None,
                           rotulos_extras=["Sobrenome", "Último sobrenome", "Last name"]),
        CampoParaPreencher(id="basico:email", rotulo="E-mail", valor=c.email,
                           rotulos_extras=["E-mail", "Email", "Seu e-mail", "Endereço de e-mail"]),
        CampoParaPreencher(id="basico:telefone", rotulo="Celular", valor=c.telefone,
                           rotulos_extras=["Celular", "Telefone", "Telefone celular", "Número de celular", "WhatsApp"]),
        CampoParaPreencher(id="basico:cidade", rotulo="Cidade", valor=c.cidade, rotulos_extras=["Cidade", "Município"]),
        CampoParaPreencher(id="basico:uf", rotulo="Estado", valor=c.uf, rotulos_extras=["Estado", "UF"]),
        CampoParaPreencher(id="basico:pais", rotulo="País", valor=c.pais, rotulos_extras=["País", "Country"]),
        CampoParaPreencher(id="basico:linkedin", rotulo="LinkedIn", valor=links.linkedin,
                           rotulos_extras=["LinkedIn", "Perfil do LinkedIn", "URL do LinkedIn", "Link do LinkedIn"]),
        CampoParaPreencher(id="basico:github", rotulo="GitHub", valor=links.github,
                           rotulos_extras=["GitHub", "Perfil do GitHub", "Link do GitHub"]),
        CampoParaPreencher(id="basico:portfolio", rotulo="Portfólio", valor=links.portfolio,
                           rotulos_extras=["Portfólio", "Portfolio", "Site pessoal", "Link do portfólio"]),
    ]
    return [campo for campo in campos if campo.valor]


def _vazio_e_editavel(alvo) -> tuple[bool, str]:
    info = alvo.evaluate("""e => ({tag: e.tagName.toLowerCase(), tipo: (e.getAttribute('type') || '').toLowerCase(),
        bloqueado: e.disabled || e.readOnly, visivel: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length),
        valor: e.tagName === 'SELECT' ? (e.selectedIndex > 0 ? e.options[e.selectedIndex].text : '') : (e.value || '')})""")
    if info["bloqueado"] or not info["visivel"] or info["tipo"] in TIPOS_PROIBIDOS:
        return False, info["tag"]
    return not info["valor"].strip(), info["tag"]


def preencher_vazios(pagina, campos: list[CampoParaPreencher], ja_feitos: set[tuple[str, str]]) -> list[str]:
    """Uma passada na página: preenche os campos básicos vazios que achar. Devolve os rótulos preenchidos."""
    url = (pagina.url or "").split("?")[0].split("#")[0]
    por_id = {c.id: c for c in campos}
    tem_sobrenome = "basico:sobrenome" in por_id and localizar(pagina, por_id["basico:sobrenome"]) is not None
    feitos: list[str] = []
    for campo in campos:
        chave = (url, campo.id)
        if chave in ja_feitos:
            continue
        valor = campo.valor
        if campo.id == "basico:nome" and not tem_sobrenome:
            valor = por_id.get("basico:nome_completo", campo).valor  # "Nome" sozinho = nome completo
        if campo.arquivo:  # currículo: só no primeiro campo de arquivo vazio da página
            feito = _anexar(pagina, campo)
            if feito is not None:
                ja_feitos.add(chave)
                if feito:
                    feitos.append(campo.rotulo)
            continue
        alvo = localizar(pagina, campo)
        if alvo is None:
            continue
        try:
            vazio, tag = _vazio_e_editavel(alvo)
            if not vazio:
                ja_feitos.add(chave)  # já tem valor (seu ou do site): nunca sobrescreve
                continue
            if tag == "select":
                opcoes = [valor] + ([UFS[valor.upper()]] if campo.id == "basico:uf" and valor.upper() in UFS else [])
                for opcao in opcoes:
                    try:
                        alvo.select_option(label=opcao, timeout=2_000)
                        break
                    except Exception:  # noqa: BLE001 - tenta a próxima forma (sigla ou nome do estado)
                        continue
                else:
                    continue
            else:
                alvo.fill(valor, timeout=3_000)
        except Exception:  # noqa: BLE001 - campo sumiu ou mudou durante a passada
            continue
        ja_feitos.add(chave)
        feitos.append(campo.rotulo)
    return feitos


def campo_curriculo(caminho) -> CampoParaPreencher:
    return CampoParaPreencher(id="basico:cv", rotulo="Currículo (arquivo)", valor=str(caminho), arquivo=True)


def _anexar(pagina, campo: CampoParaPreencher) -> bool | None:
    """Anexa o currículo no primeiro campo de arquivo ainda vazio. None = a página não tem campo de arquivo."""
    entradas = pagina.locator("input[type=file]")
    try:
        if not entradas.count():
            return None
        for k in range(entradas.count()):
            entrada = entradas.nth(k)
            if entrada.evaluate("e => e.disabled || (e.files && e.files.length > 0)"):
                continue
            aceita = (entrada.get_attribute("accept") or "").lower().replace(" ", "")
            tipos = [t for t in aceita.split(",") if t]
            if tipos and not any(t in (".pdf", "application/pdf", "*/*", "*", "application/*") for t in tipos):
                continue  # campo de foto ("image/*"), por exemplo
            entrada.set_input_files(campo.valor, timeout=5_000)
            return True
        return False
    except Exception:  # noqa: BLE001 - campo sumiu durante a passada
        return None


def dominio_raiz(url: str) -> str:
    """'https://omega.gupy.io/jobs/1' → 'gupy.io'; 'https://www.vagas.com.br/x' → 'vagas.com.br'."""
    partes = dominio_de(url).split(".")
    if len(partes) >= 3 and partes[-1] == "br" and partes[-2] in ("com", "org", "net", "gov"):
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def dominio_de(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def acompanhar(contexto, dominios: list[str], campos: list[CampoParaPreencher], *,
               ao_preencher: Callable[[str, list[str]], None] = lambda url, rotulos: None,
               dormir: Callable[[float], None] = time.sleep, horas: float = 3, intervalo_s: float = 2.5) -> int:
    """Enquanto o navegador estiver aberto, preenche os formulários dos domínios indicados. Devolve o total preenchido."""
    ja_feitos: set[tuple[str, str]] = set()
    total = 0
    for _ in range(int(horas * 3600 / intervalo_s)):
        try:
            abertas = [p for p in contexto.pages if not p.is_closed()]
        except Exception:  # noqa: BLE001 - navegador fechado
            break
        if not abertas:
            break
        for pagina in abertas:
            try:
                host = dominio_de(pagina.url)
            except Exception:  # noqa: BLE001
                continue
            if not any(host == d or host.endswith("." + d) for d in dominios):
                continue
            feitos = preencher_vazios(pagina, campos, ja_feitos)
            if feitos:
                total += len(feitos)
                ao_preencher(pagina.url, feitos)
        dormir(intervalo_s)
    return total
