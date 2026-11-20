"""CLI do M5 (candidatura assistida) e do M6 (acompanhamento do funil)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .storage import carregar_perfil, diretorio_dados

console = Console()
respostas_app = typer.Typer(help="Banco de respostas-padrão aprovadas (RF-CA-02, Anexo C).", invoke_without_command=True)
funil_app = typer.Typer(help="Funil de candidaturas: etapas, lembretes, e-mails e preparação (RF-AC-01 a RF-AC-06).",
                        invoke_without_command=True)
contatos_app = typer.Typer(help="Contatos de recrutadores e indicações (RF-AC-05).", invoke_without_command=True)


def _sair(erro) -> None:
    console.print(f"[red]{escape(str(erro))}[/red]")
    raise typer.Exit(1)


def _escolha(pergunta: str, opcoes: set[str]) -> str:
    while True:
        escolha = typer.prompt(pergunta).lstrip("﻿").strip().lower()[:1]
        if escolha in opcoes:
            return escolha
        console.print("Opção inválida.")


# ---------------------------------------------------------------- RF-CA-02

@respostas_app.callback()
def respostas_principal(ctx: typer.Context) -> None:
    """Lista as perguntas do Anexo C e as respostas que você aprovou."""
    if ctx.invoked_subcommand is not None:
        return
    from .respostas import PERGUNTAS, carregar_respostas

    banco = carregar_respostas()
    tabela = Table(title="Respostas-padrão (Anexo C)")
    for col in ("Chave", "Pergunta", "Sua resposta", "Como o agente usa"):
        tabela.add_column(col, overflow="fold")
    for chave, (pergunta, uso) in PERGUNTAS.items():
        resposta = banco.resposta(chave)
        tabela.add_row(chave, pergunta, Text(resposta) if resposta else Text("— (o agente não inventa: fica para você)", style="dim"), uso)
    console.print(tabela)
    console.print("Defina com: agente respostas definir CHAVE \"sua resposta\"")


@respostas_app.command("definir")
def respostas_definir(
    chave: str = typer.Argument(...),
    resposta: str = typer.Argument(...),
    valida_ate: str | None = typer.Option(None, "--valida-ate", help="AAAA-MM-DD, se a resposta vence (ex.: disponibilidade)."),
) -> None:
    """Aprova uma resposta-padrão para reutilizar nas candidaturas."""
    from .respostas import carregar_respostas, definir_resposta, salvar_respostas

    banco = carregar_respostas()
    try:
        definir_resposta(banco, chave, resposta, date.fromisoformat(valida_ate) if valida_ate else None)
    except ValueError as erro:
        _sair(erro)
    salvar_respostas(banco)
    console.print(f"[green]Resposta '{escape(chave)}' aprovada.[/green]")


@respostas_app.command("remover")
def respostas_remover(chave: str = typer.Argument(...)) -> None:
    """Remove uma resposta-padrão."""
    from .respostas import carregar_respostas, salvar_respostas

    banco = carregar_respostas()
    if banco.itens.pop(chave, None) is None:
        _sair(f"Não há resposta para {chave}.")
    salvar_respostas(banco)
    console.print(f"[green]Resposta '{escape(chave)}' removida.[/green]")


# ---------------------------------------------------------------- RF-CA-01 / 03 / 04 / 05 / 06 / 07

def _ler_perguntas(arquivo: Path | None) -> list[tuple[str, bool | None]]:
    """Uma pergunta por linha; '*' ou '[E]' no início marca eliminatória, '[N]' marca que não é."""
    if arquivo:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    else:
        console.print("Digite as perguntas de triagem do formulário, uma por linha (comece com * as eliminatórias; linha vazia termina).")
        linhas = []
        while (linha := typer.prompt(">", default="", show_default=False)).strip():
            linhas.append(linha)
    perguntas: list[tuple[str, bool | None]] = []
    for linha in linhas:
        texto = linha.strip()
        if not texto:
            continue
        marca: bool | None = None
        if texto.startswith(("*", "[E]", "[e]")):
            marca, texto = True, texto.lstrip("*").removeprefix("[E]").removeprefix("[e]").strip()
        elif texto.startswith(("[N]", "[n]")):
            marca, texto = False, texto[3:].strip()
        perguntas.append((texto, marca))
    return perguntas


def _mostrar_kit(kit) -> None:
    if kit.eliminatorias:
        linhas = []
        for p in kit.eliminatorias:
            linhas.append(f"[bold]{escape(p.texto)}[/bold]\n  → {escape(p.resposta or 'SEM RESPOSTA — responda você')}"
                          + (f"\n  [yellow]⚠ {escape(p.alerta)}[/yellow]" if p.alerta else ""))
        console.print(Panel("\n".join(linhas), title="Perguntas eliminatórias — confira antes de tudo (RF-CA-07)", border_style="red"))
    cob = kit.cobertura
    console.print(Panel(
        f"Atendidos: {escape(', '.join(cob.atendidos) or '—')}\nIncluídos no CV: {escape(', '.join(cob.incluidos) or '—')}\n"
        f"Sem lastro: {escape(', '.join(cob.sem_lastro) or '—')}\n"
        + ("\n".join(f"• {escape(m)}" for m in kit.mudancas_cv[:6]) or "CV-base já alinhado à vaga"),
        title="CV sob medida (RF-CV-11)", border_style="cyan"))
    console.print(Panel(Text(kit.mensagem), title=f"Mensagem · {len(kit.mensagem)} caracteres · escrita por: "
                                                  f"{kit.motor_mensagem or 'agente (motor local)'}", border_style="cyan"))
    outras = [p for p in kit.perguntas if not p.eliminatoria]
    if outras:
        tabela = Table(title="Outras perguntas de triagem")
        for col in ("Pergunta", "Resposta", "Origem"):
            tabela.add_column(col, overflow="fold")
        for p in outras:
            tabela.add_row(Text(p.texto), Text(p.resposta or "SEM RESPOSTA — responda você"),
                           p.origem + (f" · {p.alerta}" if p.alerta else ""))
        console.print(tabela)


def _guardar_kit(candidatura, kit, perfil) -> list[Path]:
    """RF-CA-06: descrição completa da vaga, CV, mensagem e respostas ficam na pasta da candidatura."""
    from .analise.exportar import exportar_docx, exportar_pdf
    from .candidatar.kit import kit_markdown
    from .candidaturas import pasta_candidatura

    pasta = pasta_candidatura(candidatura)
    (pasta / "kit.json").write_text(kit.model_dump_json(indent=2), encoding="utf-8")
    (pasta / "kit.md").write_text(kit_markdown(kit), encoding="utf-8")
    (pasta / "vaga.md").write_text(f"# {kit.vaga.titulo}\n\n{kit.vaga.descricao or '(descrição não coletada)'}\n", encoding="utf-8")
    (pasta / "mensagem.txt").write_text(kit.mensagem, encoding="utf-8")
    cv_pdf, _ = exportar_pdf(kit.variante, pasta / f"cv-{candidatura.id}.pdf")
    cv_docx = exportar_docx(kit.variante, pasta / f"cv-{candidatura.id}.docx")
    candidatura.kit_dir = str(pasta)
    return [cv_pdf, cv_docx]


def _registrar_envio(candidatura, kit, modo: str, captura: Path | None) -> None:
    from .candidaturas import Etapa
    from .configuracao import carregar_configuracao
    from .funil import atualizar_lembretes, carregar_lembretes, salvar_lembretes
    from .ia import autoria
    from .operacao.auditoria import registrar_acao

    candidatura.mudar_status(Etapa.APLICADA)
    respostas = "\n".join(f"{p.texto} → {p.resposta or '(respondida por você na plataforma)'}" for p in kit.perguntas)
    registrar_acao(
        plataforma=candidatura.plataforma or "?", acao="enviar candidatura",
        alvo=f"{candidatura.vaga_titulo}{f' — {candidatura.empresa}' if candidatura.empresa else ''}",
        depois=f"CV {candidatura.variante}\n\nMensagem:\n{kit.mensagem}\n\nRespostas:\n{respostas}", modo=modo,
        aprovado_em=datetime.now(timezone.utc), origem_aprovacao=f"kit da candidatura {candidatura.id} (envio confirmado por você)",
        captura=captura, autoria=autoria(kit.motor_mensagem),
    )
    lembretes = carregar_lembretes()
    atualizar_lembretes(lembretes, candidatura, carregar_configuracao().limites.followup_dias)
    salvar_lembretes(lembretes)


def _esperar_fechar(sessao) -> None:
    """Espera você fechar a janela do navegador do agente (o envio é seu; feche quando terminar)."""
    import time

    while True:
        try:
            if not sessao.aberta():
                return
        except Exception:  # noqa: BLE001 - navegador já fechado
            return
        time.sleep(1.5)


def _candidatura_no_site(link: str, cv: Path | None, perfil, contrato: str | None = None,
                         mensagem: str | None = None) -> None:
    """Abre a vaga no site (Gupy, Vagas, InfoJobs...) e preenche sozinho os dados básicos, o currículo, as perguntas
    com resposta aprovada e a mensagem de apresentação, até você fechar."""
    from .linkedin.automatico import responder_com_perfil
    from .navegador import SessaoNavegador
    from .preenchimento_auto import acompanhar, campo_curriculo, campos_basicos, dominio_raiz
    from .respostas import carregar_respostas

    campos = campos_basicos(perfil) + ([campo_curriculo(cv)] if cv and cv.is_file() else [])
    responder = responder_com_perfil(perfil, carregar_respostas(), contrato)
    with SessaoNavegador(uso="a candidatura no site da vaga") as sessao:
        sessao.pagina.goto(link, wait_until="domcontentloaded")
        console.print(Panel(
            "A vaga abriu no navegador do agente. Entre na conta se o site pedir (login é seu) e clique em "
            "'Candidatar-se'.\nEm cada formulário, o agente preenche nome, e-mail, telefone, cidade, links, anexa o "
            "currículo sob medida e responde as perguntas que você já respondeu em \"Respostas prontas\" (pretensão, "
            "disponibilidade, inglês...), só em campos vazios. No campo de apresentação vai a mensagem da vaga.\n"
            "Perguntas de diversidade são suas. Confira tudo, responda o que faltar e clique em ENVIAR você mesmo. "
            "Depois feche o navegador.", title="Candidatura no site", border_style="magenta"))

        def avisar(endereco: str, rotulos: list[str]) -> None:
            console.print(f"[green]Preenchido:[/green] {escape(', '.join(rotulos))}")

        acompanhar(sessao.visao(), [dominio_raiz(link)], campos, ao_preencher=avisar, responder=responder,
                   mensagem=mensagem)


def _preencher_linkedin(link: str, central, cv: Path | None, perfil, contrato: str | None,
                        esperar_fechar: bool = False) -> Path | None:
    """Candidatura Simplificada no navegador do agente: preenche e avança, para antes de enviar (RN-04 por opção)."""
    from .linkedin.automatico import LoginNecessario, candidatura_simplificada, responder_com_perfil
    from .navegador import SessaoNavegador
    from .operacao.notificacoes import notificar
    from .operacao.saude import LayoutMudou, carregar_saude, salvar_saude
    from .respostas import carregar_respostas

    nome = "assistido:linkedin"
    saude = carregar_saude()
    if not saude.pode_usar(nome):
        console.print("[yellow]A candidatura automática no LinkedIn está parada após um erro; seguindo em copiloto "
                      "(reative em 'agente saude reativar assistido:linkedin').[/yellow]")
        return None
    responder = responder_com_perfil(perfil, carregar_respostas(), contrato)
    with SessaoNavegador(uso="a candidatura no LinkedIn") as sessao:
        console.print("[magenta]Abrindo a vaga no LinkedIn, no navegador do agente…[/magenta]")
        resultado = None
        for tentativa in range(2):
            try:
                resultado = candidatura_simplificada(
                    sessao.pagina, link, responder, cv, central.linkedin_automatico,
                    limite_acoes=central.limites.acoes_por_sessao, pasta_capturas=diretorio_dados() / "auditoria" / "capturas")
                break
            except LoginNecessario as erro:
                if tentativa:
                    console.print(f"[red]{escape(str(erro))}[/red]")
                    return None
                console.print(Panel("O LinkedIn pediu login. Entre na sua conta no navegador que abriu (login, 2FA e "
                                    "CAPTCHA são seus, RN-03). Depois volte aqui.", title="Login no LinkedIn",
                                    border_style="magenta"))
                typer.prompt("Tecle Enter quando tiver entrado", default="", show_default=False)
            except LayoutMudou as erro:
                saude.falha(nome, str(erro), parar=True)
                salvar_saude(saude)
                notificar("falha_adaptador", "Candidatura automática parada no LinkedIn", str(erro), central)
                console.print(f"[red]Parei: {escape(str(erro))}. Siga em copiloto com os valores abaixo.[/red]")
                return None
        saude.sucesso(nome)
        salvar_saude(saude)
        if resultado.preenchidos:
            console.print(f"[green]Preenchido pelo agente em {resultado.etapas} etapa(s):[/green] "
                          f"{escape(', '.join(dict.fromkeys(resultado.preenchidos)))}")
        if resultado.sem_resposta:
            console.print(f"[yellow]Só você pode responder:[/yellow] {escape('; '.join(resultado.sem_resposta))}")
        console.print(f"[bold]{escape(resultado.mensagem)}[/bold]")
        if esperar_fechar:
            console.print("Quando terminar no LinkedIn, feche o navegador do agente.")
            _esperar_fechar(sessao)
        else:
            typer.prompt("Tecle Enter depois de revisar (e enviar, se quiser) para fechar o navegador", default="",
                         show_default=False)
        return resultado.captura if resultado.parou != "sem_candidatura_simplificada" else None


def _preencher_assistido(kit, link: str, central, cv: Path | None = None, perfil=None, contrato: str | None = None) -> Path | None:
    from .configuracao import plataforma_da_url
    from .navegador import CampoParaPreencher, SessaoNavegador, preencher
    from .operacao.notificacoes import notificar
    from .operacao.saude import LayoutMudou, carregar_saude, salvar_saude

    plataforma = plataforma_da_url(link)
    if plataforma == "linkedin":
        return _preencher_linkedin(link, central, cv, perfil, contrato)
    nome = f"assistido:{plataforma}"
    saude = carregar_saude()
    if not saude.pode_usar(nome):
        console.print(f"[yellow]O preenchimento assistido em {plataforma} está parado; seguindo em copiloto.[/yellow]")
        return None
    campos = [CampoParaPreencher(id="mensagem", rotulo="Mensagem", valor=kit.mensagem)]
    if kit.apresentacao:
        campos.append(CampoParaPreencher(id="apresentacao", rotulo="Apresente-se", valor=kit.apresentacao))
    campos += [CampoParaPreencher(id=f"pergunta{i}", rotulo=p.texto, valor=p.resposta, obrigatorio=bool(p.resposta and p.eliminatoria))
               for i, p in enumerate(kit.perguntas)]
    if cv is not None and cv.is_file():
        campos.append(CampoParaPreencher(id="cv", rotulo="Currículo", valor=str(cv), arquivo=True))
    with SessaoNavegador(uso="o preenchimento assistido de uma candidatura") as sessao:
        sessao.pagina.goto(link)
        console.print(Panel("No navegador: faça login, 2FA e CAPTCHA (RN-03) e abra o formulário de candidatura. "
                            "Depois volte aqui: o agente preenche e anexa o currículo.", title="Modo assistido",
                            border_style="magenta"))
        typer.prompt("Tecle Enter quando o formulário estiver aberto", default="", show_default=False)
        try:
            resultado = preencher(sessao.pagina, campos, limite_acoes=central.limites.acoes_por_sessao,
                                  intervalo_segundos=central.limites.intervalo_entre_acoes_segundos,
                                  pasta_capturas=diretorio_dados() / "auditoria" / "capturas")
        except LayoutMudou as erro:
            saude.falha(nome, str(erro), parar=True)
            salvar_saude(saude)
            notificar("falha_adaptador", f"Candidatura assistida parada em {plataforma}", str(erro), central)
            console.print(f"[red]Parei sem preencher: {escape(str(erro))}. Siga em copiloto com os valores abaixo.[/red]")
            return None
        saude.sucesso(nome)
        salvar_saude(saude)
        console.print(f"[green]Preenchido pelo agente:[/green] {escape(', '.join(resultado.preenchidos) or '—')}")
        if resultado.para_copiloto:
            console.print(f"[yellow]Fica com você:[/yellow] {escape(', '.join(resultado.para_copiloto))}")
        console.print("[bold]Pare na tela de revisão e confira tudo. O agente não envia: o clique em enviar é seu.[/bold]")
        typer.prompt("Tecle Enter depois de revisar (e enviar, se quiser) para fechar o navegador", default="", show_default=False)
        return resultado.captura


def candidatar(
    vaga_id: str = typer.Argument(..., metavar="ID_DA_VAGA", help="ID em 'agente vagas listar'."),
    perguntas: Path | None = typer.Option(None, "--perguntas", exists=True, readable=True,
                                          help="Perguntas de triagem, uma por linha (* = eliminatória)."),
    foco: str | None = typer.Option(None, "--foco"),
    nivel: str | None = typer.Option(None, "--nivel"),
    idioma: str = typer.Option("pt", "--idioma"),
    copiloto: bool = typer.Option(False, "--copiloto", help="Não abrir o navegador, mesmo em plataforma assistida."),
    direto: bool = typer.Option(False, "--direto", help="Abre a vaga no site e preenche lá (sem perguntas aqui): "
                                "o que o botão 'Quero me candidatar' do app usa."),
) -> None:
    """Monta o kit, preenche no modo da plataforma e para na revisão; o envio é seu (RF-CA-01 a RF-CA-07)."""
    from .analise.lastro import verificar_lastro
    from .candidatar.kit import montar_kit
    from .candidatar.regras import checar_candidatura
    from .candidaturas import Candidatura, Etapa, carregar_candidaturas, salvar_candidaturas
    from .configuracao import carregar_configuracao, plataforma_da_url
    from .confirmacao import pendencias_na_variante
    from .navegador import playwright_disponivel
    from .radar.modelos import SINONIMOS_POR_FOCO, carregar_base
    from .respostas import carregar_respostas, definir_resposta, salvar_respostas

    perfil = carregar_perfil()
    central = carregar_configuracao()
    try:
        vaga = carregar_base().buscar(vaga_id)
    except ValueError as erro:
        _sair(erro)
    colecao = carregar_candidaturas()
    for bloqueio in checar_candidatura(colecao, vaga, perfil, central.limites):
        if not bloqueio.contornavel:
            _sair(f"Não dá para candidatar: {bloqueio.mensagem}")
        console.print(f"[yellow]{escape(bloqueio.mensagem)}[/yellow]")
        if not typer.confirm("Seguir mesmo assim, só desta vez?", default=False):
            raise typer.Exit(0)
    if not vaga.descricao:
        console.print("[yellow]A descrição da vaga não foi coletada: o CV sob medida fica pelo título. Cole a descrição com "
                      "'agente vagas link URL --descricao vaga.txt' para um kit melhor.[/yellow]")

    banco = carregar_respostas()
    foco = foco or (vaga.busca if vaga.busca in SINONIMOS_POR_FOCO else "backend-dotnet")
    plataforma = plataforma_da_url(vaga.link) if vaga.link else None
    linkedin_automatico = (plataforma == "linkedin" and central.linkedin_automatico.ativo and not copiloto
                           and not central.somente_sugestao and playwright_disponivel())
    if (linkedin_automatico or direto) and perguntas is None:
        # As perguntas do formulário ficam no próprio site (no LinkedIn automático, o agente responde lá mesmo).
        lista_perguntas: list[tuple[str, bool | None]] = []
    else:
        lista_perguntas = _ler_perguntas(perguntas)
    kit = montar_kit(perfil, vaga, lista_perguntas, banco, foco=foco, idioma=idioma, nivel=nivel or vaga.nivel or "estagio")
    if pendencias_na_variante(kit.variante) or verificar_lastro(kit.variante, perfil):
        _sair("O CV sob medida tem frases [A CONFIRMAR] ou itens sem lastro (RN-02); rode 'agente confirmar' e revise o perfil.")

    for p in kit.sem_resposta:
        resposta = typer.prompt(f"Sua resposta para '{p.texto}' (Enter = responder direto na plataforma)", default="", show_default=False)
        if resposta.strip():
            p.resposta, p.origem = resposta.strip(), "usuario"
            if p.chave and p.chave != "diversidade" and typer.confirm("Guardar como resposta-padrão para as próximas?", default=False):
                definir_resposta(banco, p.chave, p.resposta)
                salvar_respostas(banco)

    while not direto:  # no modo direto, o clique em "Quero me candidatar" aprova o kit; você revisa tudo no site
        _mostrar_kit(kit)
        escolha = _escolha("[a]provar o kit, [e]ditar a mensagem ou [c]ancelar", {"a", "e", "c"})
        if escolha == "c":
            console.print("Nada foi registrado nem enviado.")
            raise typer.Exit(0)
        if escolha == "a":
            break
        resposta = typer.prompt("Nova mensagem (ou caminho de um arquivo .txt)")
        caminho = Path(resposta.strip().strip('"'))
        kit.mensagem = caminho.read_text(encoding="utf-8").strip() if caminho.suffix == ".txt" and caminho.is_file() else resposta.strip()
        kit.motor_mensagem = "usuario"

    candidatura = next((c for c in colecao.itens if c.vaga_id == vaga.id and c.status == Etapa.SELECIONADA), None)
    if candidatura is None:
        candidatura = Candidatura(vaga_id=vaga.id, vaga_titulo=vaga.titulo, empresa=vaga.empresa, foco=foco,
                                  variante=kit.variante.nome_arquivo, idioma=idioma, vaga_link=vaga.link,
                                  plataforma=plataforma_da_url(vaga.link) if vaga.link else None,
                                  nota_aderencia=vaga.nota, status=Etapa.ENCONTRADA)
        candidatura.mudar_status(Etapa.SELECIONADA)
        colecao.itens.append(candidatura)
    arquivos = _guardar_kit(candidatura, kit, perfil)
    salvar_candidaturas(colecao)
    console.print(f"[green]Kit guardado em[/green] {candidatura.kit_dir} (candidatura {candidatura.id}).")

    modo = central.modos_plataforma.get(candidatura.plataforma or "", "copiloto")
    captura = None
    if direto:
        if not vaga.link:
            _sair("Esta vaga não tem link para abrir. Use 'Adicionar vaga por link' com o endereço da vaga.")
        if central.somente_sugestao or not playwright_disponivel():
            _sair("O modo só sugestões está ligado (ou falta o navegador do agente): abra a vaga você mesmo.")
        from .navegador import NavegadorOcupado

        cv = Path(arquivos[0]) if arquivos else None
        try:
            if linkedin_automatico:
                captura = _preencher_linkedin(vaga.link, central, cv, perfil, vaga.contrato, esperar_fechar=True)
                modo = "assistido"
            else:
                _candidatura_no_site(vaga.link, cv, perfil, vaga.contrato, kit.mensagem)
                modo = "assistido"
        except NavegadorOcupado as erro:
            _sair(f"{erro}")
        if typer.confirm("Você enviou a candidatura no site?", default=False):
            _registrar_envio(candidatura, kit, modo, captura)
            salvar_candidaturas(colecao)
            console.print("[green]Candidatura registrada como enviada; follow-up agendado.[/green]")
        else:
            console.print("Tudo bem: a candidatura ficou preparada (kit e currículo guardados) e não foi marcada como enviada.")
        return
    usar_assistido = linkedin_automatico or (
        modo == "assistido" and not copiloto and vaga.link and not central.somente_sugestao and playwright_disponivel())
    if usar_assistido:
        from .navegador import NavegadorOcupado

        try:
            captura = _preencher_assistido(kit, vaga.link, central, cv=Path(arquivos[0]) if arquivos else None,
                                           perfil=perfil, contrato=vaga.contrato)
        except NavegadorOcupado as erro:
            console.print(f"[yellow]{escape(str(erro))} Seguindo em copiloto.[/yellow]")
            captura = None
        modo = "assistido" if captura is not None else modo
    if captura is None:
        console.print(Panel(
            "\n".join([f"1. Abra a vaga: {escape(vaga.link or '(sem link)')}", "2. Faça login, 2FA e CAPTCHA (seu, RN-03).",
                       f"3. Anexe o CV: {arquivos[0]}", "4. Cole a mensagem (em mensagem.txt na pasta do kit)."]
                      + [f"{i}. {escape(p.texto)} → {escape(p.resposta or 'responda você')}" for i, p in enumerate(kit.perguntas, 5)]
                      + ["Por último: PARE na tela de revisão e confira tudo. O envio é seu."]),
            title="Preenchimento em copiloto (RF-CA-03)", border_style="cyan"))
        modo = "copiloto" if not usar_assistido else modo

    if typer.confirm("Você revisou na tela de revisão e CLICOU EM ENVIAR?", default=False):
        _registrar_envio(candidatura, kit, modo, captura)
        salvar_candidaturas(colecao)
        console.print("[green]Candidatura registrada como aplicada e auditada; follow-up agendado.[/green]")
    else:
        console.print(f"Candidatura preparada, não enviada. Quando enviar: 'agente funil enviada {candidatura.id}'.")


def indicacao(
    vaga_id: str = typer.Argument(..., metavar="ID_DA_VAGA"),
    conexoes: Path = typer.Option(..., "--conexoes", exists=True, readable=True,
                                  help="Connections.csv ou o ZIP da exportação de dados do LinkedIn."),
) -> None:
    """Sugere pedidos de indicação a quem trabalha na empresa da vaga; o envio é manual (RF-CA-08)."""
    from .candidatar.indicacao import conexoes_na_empresa, ler_conexoes, rascunho_indicacao
    from .radar.modelos import carregar_base

    perfil = carregar_perfil()
    try:
        vaga = carregar_base().buscar(vaga_id)
    except ValueError as erro:
        _sair(erro)
    if not vaga.empresa:
        _sair("A vaga não tem empresa identificada.")
    pessoas = conexoes_na_empresa(ler_conexoes(conexoes), vaga.empresa)
    if not pessoas:
        console.print(f"Nenhuma conexão sua trabalha na {escape(vaga.empresa)}, pela exportação.")
        return
    for pessoa in pessoas[:5]:
        console.print(Panel(Text(rascunho_indicacao(perfil, pessoa, vaga.titulo, vaga.empresa, vaga.link)),
                            title=f"{escape(pessoa.nome)} — {escape(pessoa.cargo or '')}", border_style="cyan"))
    console.print("Envie você pelo LinkedIn, personalizando (RN-11). Os dados das conexões não são guardados (RNF-05).")


# ---------------------------------------------------------------- RF-AC-01 / RF-AC-06

@funil_app.callback()
def funil_principal(ctx: typer.Context) -> None:
    """Mostra as candidaturas por etapa do funil."""
    if ctx.invoked_subcommand is not None:
        return
    from .candidaturas import NOMES_ETAPA, carregar_candidaturas

    itens = carregar_candidaturas().itens
    if not itens:
        console.print("Nenhuma candidatura ainda. Comece com 'agente candidatar ID_DA_VAGA'.")
        return
    tabela = Table(title=f"Funil ({len(itens)} candidatura[s])")
    for col in ("ID", "Vaga", "Empresa", "Etapa", "Desde", "Próximo / motivo"):
        tabela.add_column(col, overflow="fold")
    for c in sorted(itens, key=lambda c: c.historico[-1].quando if c.historico else c.criada_em, reverse=True):
        desde = (c.historico[-1].quando if c.historico else c.criada_em).astimezone()
        proximo = (f"{c.proxima_etapa_em.astimezone():%d/%m %H:%M}" if c.proxima_etapa_em
                   else (c.motivo_saida or ""))
        tabela.add_row(c.id, Text(c.vaga_titulo), Text(c.empresa or ""), NOMES_ETAPA[c.status], f"{desde:%d/%m/%Y}", Text(proximo))
    console.print(tabela)
    console.print("Mova com 'agente funil mover ID ETAPA'. Etapas: " + ", ".join(e.value for e in NOMES_ETAPA))


@funil_app.command("mover")
def funil_mover(
    id_: str = typer.Argument(..., metavar="ID"),
    etapa: str = typer.Argument(..., help="em_analise, teste_tecnico, entrevista_rh, entrevista_tecnica, proposta, contratado, reprovado, desistencia, vaga_encerrada"),
    motivo: str | None = typer.Option(None, "--motivo", help="Obrigatório para reprovação e desistência (RF-AC-06)."),
    detalhe: str | None = typer.Option(None, "--detalhe"),
    quando: str | None = typer.Option(None, "--quando", help="Data da etapa agendada: 'AAAA-MM-DD HH:MM'."),
) -> None:
    """Muda a etapa da candidatura, com data, motivo e lembretes (RF-AC-01, RF-AC-03, RF-AC-06)."""
    from .candidaturas import ETAPAS_COM_DATA, MOTIVOS_SAIDA, Etapa, carregar_candidaturas, salvar_candidaturas
    from .configuracao import carregar_configuracao
    from .funil import atualizar_lembretes, carregar_lembretes, salvar_lembretes

    colecao = carregar_candidaturas()
    try:
        cand = colecao.buscar(id_)
        nova = Etapa(etapa)
    except ValueError as erro:
        _sair(erro)
    if nova in (Etapa.REPROVADO, Etapa.DESISTENCIA) and not motivo:
        opcoes = MOTIVOS_SAIDA[nova]
        for i, m in enumerate(opcoes, 1):
            console.print(f"  {i}. {m}")
        escolha = typer.prompt("Motivo (número)", default=str(len(opcoes)))
        motivo = opcoes[int(escolha) - 1] if escolha.isdigit() and 1 <= int(escolha) <= len(opcoes) else escolha
    data = None
    if nova in ETAPAS_COM_DATA:
        texto = quando if quando is not None else typer.prompt("Data e hora (AAAA-MM-DD HH:MM; Enter = sem data)", default="", show_default=False)
        if texto.strip():
            try:
                data = datetime.strptime(texto.strip(), "%Y-%m-%d %H:%M").astimezone().astimezone(timezone.utc)
            except ValueError:
                _sair("Use AAAA-MM-DD HH:MM.")
    try:
        cand.mudar_status(nova, motivo=motivo, detalhe=detalhe, quando=data)
    except ValueError as erro:
        _sair(erro)
    lembretes = carregar_lembretes()
    criados = atualizar_lembretes(lembretes, cand, carregar_configuracao().limites.followup_dias)
    salvar_lembretes(lembretes)
    salvar_candidaturas(colecao)
    console.print(f"[green]{escape(cand.vaga_titulo)} → {nova.value}[/green]" + (f" · motivo: {escape(motivo)}" if motivo else ""))
    for l in criados:
        console.print(f"  lembrete: {escape(l.descricao)} em {l.quando.astimezone():%d/%m %H:%M}")
    if nova in ETAPAS_COM_DATA:
        console.print(f"Prepare-se com 'agente funil preparar {cand.id}'.")


@funil_app.command("enviada")
def funil_enviada(
    id_: str = typer.Argument(..., metavar="ID"),
    captura: Path | None = typer.Option(None, "--captura", exists=True, readable=True),
) -> None:
    """Confirma que você enviou uma candidatura preparada (registro, auditoria e follow-up)."""
    from .candidatar.kit import Kit
    from .candidaturas import Etapa, carregar_candidaturas, salvar_candidaturas

    colecao = carregar_candidaturas()
    try:
        cand = colecao.buscar(id_)
    except ValueError as erro:
        _sair(erro)
    if cand.status != Etapa.SELECIONADA or not cand.kit_dir:
        _sair("Só uma candidatura preparada pelo 'agente candidatar' pode ser confirmada como enviada.")
    kit = Kit.model_validate_json((Path(cand.kit_dir) / "kit.json").read_text(encoding="utf-8"))
    if not typer.confirm(f"Confirma que ENVIOU a candidatura para {cand.vaga_titulo}?", default=False):
        raise typer.Exit(0)
    _registrar_envio(cand, kit, "copiloto", captura)
    salvar_candidaturas(colecao)
    console.print("[green]Registrada como aplicada e auditada; follow-up agendado.[/green]")


# ---------------------------------------------------------------- RF-AC-03

@funil_app.command("lembretes")
def funil_lembretes(todos: bool = typer.Option(False, "--todos", help="Inclui os futuros e os feitos.")) -> None:
    """Follow-ups vencidos e etapas das próximas 24 h (RF-AC-03)."""
    from .funil import carregar_lembretes, vencidos

    lembretes = carregar_lembretes()
    lista = lembretes.itens if todos else vencidos(lembretes)
    if not lista:
        console.print("Nenhum lembrete pendente.")
        return
    tabela = Table(title="Lembretes")
    for col in ("ID", "Quando", "Tipo", "Descrição", "Feito"):
        tabela.add_column(col, overflow="fold")
    for l in sorted(lista, key=lambda l: l.quando):
        tabela.add_row(l.id, f"{l.quando.astimezone():%d/%m %H:%M}", l.tipo, Text(l.descricao), "sim" if l.feito else "")
    console.print(tabela)
    console.print("Rascunho de follow-up: 'agente funil followup ID_DA_CANDIDATURA'. Marcar feito: 'agente funil feito ID'.")


@funil_app.command("feito")
def funil_feito(id_: str = typer.Argument(..., metavar="ID_DO_LEMBRETE")) -> None:
    """Marca um lembrete como feito."""
    from .funil import marcar_lembrete_feito

    if not marcar_lembrete_feito(id_):
        _sair(f"Lembrete {id_} não existe.")
    console.print("[green]Lembrete marcado como feito.[/green]")


@funil_app.command("followup")
def funil_followup(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Rascunho de mensagem de follow-up; o envio é seu (RN-11)."""
    from .candidaturas import carregar_candidaturas
    from .funil import rascunho_followup

    try:
        cand = carregar_candidaturas().buscar(id_)
    except ValueError as erro:
        _sair(erro)
    console.print(Panel(Text(rascunho_followup(cand, carregar_perfil().contato.nome)), title="Follow-up (envio manual)", border_style="cyan"))


@funil_app.command("agenda")
def funil_agenda() -> None:
    """Exporta lembretes pendentes para o calendário (.ics: Google, Outlook, Apple) (RF-AC-03)."""
    from .funil import carregar_lembretes, ics

    pendentes = [l for l in carregar_lembretes().itens if not l.feito]
    if not pendentes:
        console.print("Nenhum lembrete pendente para exportar.")
        return
    destino = diretorio_dados() / "agenda" / "agente-de-carreira.ics"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(ics(pendentes).encode("utf-8"))
    console.print(f"[green]{len(pendentes)} evento(s) em[/green] {destino} — importe no seu calendário.")


# ---------------------------------------------------------------- RF-AC-02

@funil_app.command("emails")
def funil_emails(
    pasta: Path | None = typer.Option(None, "--pasta", help="Pasta com e-mails .eml de retorno (padrão: data/caixa-retornos)."),
    sem_imap: bool = typer.Option(False, "--sem-imap"),
) -> None:
    """Lê os e-mails de retorno das plataformas e atualiza o funil; os ambíguos pedem confirmação (RF-AC-02)."""
    import os

    from .candidaturas import Etapa, carregar_candidaturas, salvar_candidaturas
    from .configuracao import carregar_configuracao
    from .funil import (
        PendenciaEmail,
        atualizar_lembretes,
        carregar_lembretes,
        carregar_pendencias,
        interpretar_email,
        salvar_lembretes,
        salvar_pendencias,
    )
    from .radar.coleta import _partes, config_imap, ler_eml, ler_imap
    from .radar.extracao import html_para_texto

    pasta = pasta or diretorio_dados() / "caixa-retornos"
    pasta.mkdir(parents=True, exist_ok=True)
    mensagens = []
    for caminho in sorted(pasta.glob("*.eml")):
        msg = ler_eml(caminho)
        mensagens.append(((msg.get("Message-ID") or caminho.name).strip(), msg))
    imap = None if sem_imap else config_imap()
    if imap:
        imap = {**imap, "pasta": os.environ.get("AGENTE_IMAP_PASTA_RETORNOS", "Retornos")}
        try:
            mensagens += ler_imap(imap, date.today().replace(day=1), )
        except Exception as erro:  # noqa: BLE001 - IMAP indisponível não impede ler os .eml
            console.print(f"[yellow]IMAP: {escape(str(erro))}[/yellow]")

    colecao, pendencias = carregar_candidaturas(), carregar_pendencias()
    if carregar_configuracao().email_navegador.ativo and not sem_imap:  # RF-EV-01: o mesmo Outlook dos alertas
        from .navegador import playwright_disponivel
        from .radar.outlook_web import consultas_de_retorno, ler_retornos

        if consultas_de_retorno(colecao) and playwright_disponivel():
            console.print("[magenta]Outlook: procurando e-mails das empresas onde você se candidatou (só leitura)…[/magenta]")
            lidas, avisos = ler_retornos(colecao, set(pendencias.processados))
            mensagens += lidas
            for aviso in avisos:
                console.print(f"[yellow]{escape(aviso)}[/yellow]")
    lembretes = carregar_lembretes()
    aplicadas = novas_pendencias = 0
    for msgid, msg in mensagens:
        if msgid in pendencias.processados:
            continue
        plano, html = _partes(msg)
        corpo = plano or html_para_texto(html or "")
        assunto = str(msg.get("Subject", ""))
        cand, etapa, candidatas, etapas = interpretar_email(colecao, assunto, corpo)
        if cand and etapa:
            cand.mudar_status(etapa, motivo="informado por e-mail da plataforma" if etapa == Etapa.REPROVADO else None)
            atualizar_lembretes(lembretes, cand, carregar_configuracao().limites.followup_dias)
            console.print(f"[green]{escape(cand.vaga_titulo)} → {etapa.value}[/green] (e-mail: {escape(assunto)})")
            aplicadas += 1
        elif candidatas or etapas:
            pendencias.itens.append(PendenciaEmail(msgid=msgid, assunto=assunto, trecho=" ".join(corpo.split())[:300],
                                                   etapas=etapas, candidaturas=[c.id for c in candidatas]))
            novas_pendencias += 1
        pendencias.processados.append(msgid)
    salvar_candidaturas(colecao)
    salvar_lembretes(lembretes)
    salvar_pendencias(pendencias)
    console.print(f"{len(mensagens)} e-mail(s) lido(s) · {aplicadas} atualização(ões) · {novas_pendencias} para confirmar"
                  + (" — rode 'agente funil confirmar'." if novas_pendencias else "."))
    if aplicadas or novas_pendencias:
        from .operacao.notificacoes import notificar

        notificar("lembrete_funil", "Retorno de empresa",
                  f"{aplicadas} candidatura(s) mudaram de etapa por e-mail"
                  + (f" e {novas_pendencias} e-mail(s) esperam você confirmar (Minhas candidaturas)." if novas_pendencias
                     else ". Veja em Minhas candidaturas."), carregar_configuracao())


@funil_app.command("confirmar")
def funil_confirmar() -> None:
    """Confirma as atualizações de e-mails ambíguos (RF-AC-02)."""
    from .candidaturas import NOMES_ETAPA, Etapa, carregar_candidaturas, salvar_candidaturas
    from .configuracao import carregar_configuracao
    from .funil import atualizar_lembretes, carregar_lembretes, carregar_pendencias, salvar_lembretes, salvar_pendencias

    pendencias, colecao, lembretes = carregar_pendencias(), carregar_candidaturas(), carregar_lembretes()
    if not pendencias.itens:
        console.print("Nenhum e-mail esperando confirmação.")
        return
    abertas = [c for c in colecao.itens if not c.encerrada]
    for pendencia in list(pendencias.itens):
        console.print(Panel(f"[bold]{escape(pendencia.assunto)}[/bold]\n{escape(pendencia.trecho)}", title="E-mail", border_style="yellow"))
        candidatas = [c for c in abertas if c.id in pendencia.candidaturas] or abertas
        for i, c in enumerate(candidatas, 1):
            console.print(f"  {i}. {escape(c.vaga_titulo)} — {escape(c.empresa or '?')} ({NOMES_ETAPA[c.status]})")
        escolha = typer.prompt("Qual candidatura? (número; Enter = ignorar este e-mail)", default="", show_default=False)
        if escolha.isdigit() and 1 <= int(escolha) <= len(candidatas):
            cand = candidatas[int(escolha) - 1]
            sugestao = pendencia.etapas[0].value if pendencia.etapas else ""
            etapa = typer.prompt("Nova etapa", default=sugestao)
            try:
                cand.mudar_status(Etapa(etapa), motivo="informado por e-mail da plataforma" if etapa == "reprovado" else None)
                atualizar_lembretes(lembretes, cand, carregar_configuracao().limites.followup_dias)
                console.print(f"[green]{escape(cand.vaga_titulo)} → {etapa}[/green]")
            except ValueError as erro:
                console.print(f"[red]{escape(str(erro))}[/red]")
        pendencias.itens.remove(pendencia)
    salvar_candidaturas(colecao)
    salvar_lembretes(lembretes)
    salvar_pendencias(pendencias)


# ---------------------------------------------------------------- RF-AC-04

@funil_app.command("preparar")
def funil_preparar(
    id_: str = typer.Argument(..., metavar="ID"),
    anotacoes: str | None = typer.Option(None, "--anotacoes", help="O que você já sabe da empresa."),
) -> None:
    """Material de preparação para entrevista (RF-AC-04)."""
    from .candidatar.kit import Kit, VagaDoKit
    from .candidaturas import carregar_candidaturas, pasta_candidatura
    from .preparacao import material
    from .radar.modelos import carregar_base
    from .respostas import carregar_respostas

    try:
        cand = carregar_candidaturas().buscar(id_)
    except ValueError as erro:
        _sair(erro)
    vaga = None
    if cand.kit_dir and (Path(cand.kit_dir) / "kit.json").is_file():
        vaga = Kit.model_validate_json((Path(cand.kit_dir) / "kit.json").read_text(encoding="utf-8")).vaga
    elif cand.vaga_id:
        try:
            from .candidatar.kit import vaga_do_kit

            vaga = vaga_do_kit(carregar_base().buscar(cand.vaga_id))
        except ValueError:
            vaga = None
    vaga = vaga or VagaDoKit(titulo=cand.vaga_titulo, empresa=cand.empresa)
    texto = material(carregar_perfil(), vaga, carregar_respostas(), anotacoes)
    destino = pasta_candidatura(cand) / "preparacao.md"
    destino.write_text(texto, encoding="utf-8")
    console.print(texto, markup=False, highlight=False)
    console.print(f"[green]Salvo em[/green] {destino}")


# ---------------------------------------------------------------- RF-AC-05

@contatos_app.callback()
def contatos_principal(ctx: typer.Context) -> None:
    """Lista os contatos (só nome, empresa, cargo e canal — RNF-05)."""
    if ctx.invoked_subcommand is not None:
        return
    from .funil import carregar_contatos

    contatos = carregar_contatos().itens
    if not contatos:
        console.print("Nenhum contato registrado.")
        return
    tabela = Table(title="Contatos")
    for col in ("ID", "Nome", "Empresa", "Cargo", "Canal", "Interações", "Candidaturas"):
        tabela.add_column(col, overflow="fold")
    for c in contatos:
        tabela.add_row(c.id, Text(c.nome), Text(c.empresa or ""), Text(c.cargo or ""), Text(c.canal or ""),
                       str(len(c.interacoes)), ", ".join(c.candidaturas))
    console.print(tabela)


@contatos_app.command("adicionar")
def contatos_adicionar(
    nome: str = typer.Option(..., "--nome"),
    empresa: str | None = typer.Option(None, "--empresa"),
    cargo: str | None = typer.Option(None, "--cargo"),
    canal: str | None = typer.Option(None, "--canal", help="Ex.: LinkedIn, e-mail corporativo."),
    candidatura: str | None = typer.Option(None, "--candidatura", help="ID da candidatura relacionada."),
) -> None:
    """Registra um recrutador ou indicação, só com os dados necessários."""
    from .funil import Contato, carregar_contatos, salvar_contatos

    contatos = carregar_contatos()
    contato = Contato(nome=nome, empresa=empresa, cargo=cargo, canal=canal, candidaturas=[candidatura] if candidatura else [])
    contatos.itens.append(contato)
    salvar_contatos(contatos)
    console.print(f"[green]Contato {contato.id} registrado.[/green]")


@contatos_app.command("interacao")
def contatos_interacao(id_: str = typer.Argument(..., metavar="ID"), resumo: str = typer.Argument(...)) -> None:
    """Registra uma interação com o contato."""
    from .funil import Interacao, carregar_contatos, salvar_contatos

    contatos = carregar_contatos()
    try:
        contatos.buscar(id_).interacoes.append(Interacao(resumo=resumo))
    except ValueError as erro:
        _sair(erro)
    salvar_contatos(contatos)
    console.print("[green]Interação registrada.[/green]")


@contatos_app.command("excluir")
def contatos_excluir(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Exclui o contato e tudo dele, em um passo (RNF-05)."""
    from .funil import carregar_contatos, salvar_contatos

    contatos = carregar_contatos()
    try:
        contato = contatos.excluir(id_)
    except ValueError as erro:
        _sair(erro)
    salvar_contatos(contatos)
    console.print(f"[green]{escape(contato.nome)} excluído.[/green]")
