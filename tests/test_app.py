"""App de janela: execução sem console, estado da tela inicial, atalho e coerência com a CLI."""

import ast
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.main import get_command

from agente_carreira.app import atalho, estado
from agente_carreira.app.execucao import Execucao, LeitorAnsi, opcoes_da_pergunta
from agente_carreira.candidaturas import Candidatura, Candidaturas, Etapa
from agente_carreira.cli import app as cli_app


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- coerência janela × CLI

def _chamadas_executar() -> list[list[str]]:
    """Argumentos literais de cada self.executar(...) em janela.py."""
    arvore = ast.parse(Path(atalho.__file__).with_name("janela.py").read_text(encoding="utf-8"))
    chamadas = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and getattr(no.func, "attr", None) == "executar" and len(no.args) >= 2:
            lista = no.args[1]
            if isinstance(lista, ast.List):
                chamadas.append([e.value if isinstance(e, ast.Constant) else None for e in lista.elts])
    return chamadas


def test_cada_acao_da_janela_usa_comando_e_opcoes_que_existem():
    chamadas = _chamadas_executar()
    assert len(chamadas) > 30
    raiz = get_command(cli_app)
    for args in chamadas:
        comando, i = raiz, 0
        while i < len(args) and isinstance(args[i], str) and hasattr(comando, "commands") and args[i] in comando.commands:
            comando, i = comando.commands[args[i]], i + 1
        assert i > 0, f"comando inexistente: {args}"
        opcoes = {o for p in comando.params for o in (*p.opts, *getattr(p, "secondary_opts", []))}
        for token in args[i:]:
            if isinstance(token, str) and token.startswith("--"):
                assert token in opcoes, f"'agente {' '.join(a or '?' for a in args)}': opção {token} não existe"


def test_atalho_e_comandos_registrados():
    script = atalho.script_atalho()
    assert "GetFolderPath('Desktop')" in script and "$env:AGENTE_ALVO" in script and "Área" not in script
    partida = atalho.script_partida(Path("C:/p/.venv/Lib/site-packages"), Path("C:/p"))
    assert "site.addsitedir(" in partida and "from agente_carreira.app import main" in partida
    compile(partida, "iniciar.pyw", "exec")
    alvo, argumentos = atalho.lancador()
    assert alvo.name in ("pythonw.exe", "agente-app.exe")
    if argumentos.endswith('iniciar.pyw"'):
        assert Path(argumentos.strip('"')).is_file()
    assert {"app", "atalho"} <= set(get_command(cli_app).commands)


def test_icone_tem_todos_os_tamanhos(tmp_path):
    from PIL import Image

    icone = atalho.criar_icone(tmp_path / "a.ico")
    assert {(16, 16), (32, 32), (256, 256)} <= Image.open(icone).info["sizes"]


# ---------------------------------------------------------------- perguntas e cores

def test_opcoes_entre_colchetes_viram_botoes():
    assert opcoes_da_pergunta("[a]provar o kit, [e]ditar a mensagem ou [c]ancelar") == [
        ("a", "Aprovar o kit"), ("e", "Editar a mensagem"), ("c", "Cancelar")]
    assert opcoes_da_pergunta("[o]utro motor (gemini), [l]ocal (sem IA) ou [n]ada agora")[0] == ("o", "Outro motor (gemini)")
    assert opcoes_da_pergunta("Motivo (número)") == []


def test_leitor_ansi_guarda_estilo_entre_pedacos():
    leitor = LeitorAnsi()
    assert leitor.ler("\x1b[1;32mPronto") == [("Pronto", ("negrito", "cor#2e7d32"))]
    assert leitor.ler(" ainda verde\x1b[0m fim") == [(" ainda verde", ("negrito", "cor#2e7d32")), (" fim", ())]
    assert leitor.ler("a\x1b[3") == [("a", ())]                       # sequência partida
    assert leitor.ler("1mb") == [("b", ("cor#c62828",))]
    assert leitor.ler("\x1b[38;2;10;20;30mx")[0][1] == ("cor#0a141e",)


def _rodar(args, respostas):
    """Roda sem janela: responde às perguntas na ordem dada (ou cancela com None)."""
    saida, perguntas = [], []
    pendentes = list(respostas)

    def ao_perguntar(p):
        perguntas.append(p)
        valor = pendentes.pop(0)
        p.cancelar() if valor is None else p.responder(valor)

    ex = Execucao(args, ao_escrever=saida.append, ao_perguntar=ao_perguntar, ao_terminar=lambda c: None)
    codigo = ex.rodar()
    return codigo, "".join(saida), perguntas


def test_confirmacao_vira_sim_nao_e_o_fluxo_segue(tmp_path):
    from agente_carreira.storage import carregar_perfil

    cv = tmp_path / "cv.txt"
    cv.write_text("Ana Teste\nana@example.com\n\nCompetências\nC#, SQL\n", encoding="utf-8")
    codigo, saida, perguntas = _rodar(["importar", str(cv)], [True])
    assert codigo == 0 and perguntas[0].tipo == "sim_nao"
    assert carregar_perfil().contato.email == "ana@example.com"
    assert "Perfil-mestre criado" in saida


def test_negar_e_cancelar_nao_mudam_nada(tmp_path):
    from agente_carreira.storage import perfil_existe

    cv = tmp_path / "cv.txt"
    cv.write_text("Ana Teste\nana@example.com\n", encoding="utf-8")
    assert _rodar(["importar", str(cv)], [False])[0] == 0 and not perfil_existe()
    codigo, saida, _ = _rodar(["importar", str(cv)], [None])
    assert codigo == 130 and "Cancelado" in saida and not perfil_existe()


def test_sem_perfil_orienta_e_erro_de_uso_nao_derruba():
    codigo, saida, _ = _rodar(["perfil", "mostrar"], [])
    assert codigo == 1 and "Importar currículo" in saida and "Traceback" not in saida
    codigo, saida, _ = _rodar(["comando-que-nao-existe"], [])
    assert codigo == 2 and "Erro" in saida


def test_restaura_terminal_depois_de_rodar():
    import builtins
    import sys

    import typer

    antes = (sys.stdout, typer.prompt, typer.confirm, builtins.input)
    _rodar(["perfil", "mostrar"], [])
    assert (sys.stdout, typer.prompt, typer.confirm, builtins.input) == antes


def test_prompt_numerico_pede_de_novo_e_texto_vazio_usa_padrao():
    ex = Execucao([], ao_escrever=lambda t: None, ao_perguntar=lambda p: None, ao_terminar=lambda c: None)
    respostas = iter(["abc", "7"])
    ex._perguntar = lambda p: next(respostas)
    assert ex.prompt("Quantos?", type=int) == 7
    ex._perguntar = lambda p: ""
    assert ex.prompt("Motivo (número)", default="3") == "3"


def test_li_conectar_pela_janela(tmp_path):
    from agente_carreira.linkedin.estado import carregar_estado

    zip_ = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_, "w") as zf:
        zf.writestr("Profile.csv", '"First Name","Last Name","Headline"\n"Ana","Teste","Dev .NET"\n')
        zf.writestr("Email Addresses.csv", '"Email Address","Confirmed","Primary"\n"ana@example.com","Yes","Yes"\n')
    codigo, _, _ = _rodar(["li", "conectar", str(zip_)], [True])
    assert codigo == 0 and carregar_estado().campos["titulo"] == "Dev .NET"


# ---------------------------------------------------------------- tela inicial e listas

def test_primeiros_passos_e_proximo_passo():
    passos = estado.primeiros_passos(tem_perfil=True, tem_linkedin=False, tem_busca=False, tem_vagas=False,
                                     tem_email=False, tem_agendamento=False)
    assert [p.feito for p in passos] == [True, False, False, False, False, False]
    assert [p.acao for p in passos][-2:] == ["buscar_vagas", "agendar_busca"]
    assert estado.proximo_passo(passos, {}, None).acao == "conectar_linkedin"
    prontos = estado.primeiros_passos(tem_perfil=True, tem_linkedin=True, tem_busca=True, tem_vagas=True)
    agora = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    assert estado.proximo_passo(prontos, {"aprovacoes": 2, "vagas_boas": 3}, agora, agora).acao == "aprovacoes"
    assert estado.proximo_passo(prontos, {"vagas_boas": 3}, agora, agora).acao == "vagas"
    assert estado.proximo_passo(prontos, {}, agora - timedelta(days=2), agora).acao == "buscar_vagas"
    assert estado.proximo_passo(prontos, {}, agora, agora).acao is None


def test_tela_inicial_sem_dados():
    inicio = estado.montar_inicio()
    assert inicio.nome is None and inicio.proximo.acao == "importar_cv"
    assert inicio.numeros == {"vagas_boas": 0, "em_andamento": 0, "lembretes": 0, "aprovacoes": 0, "parados": 0}


def test_lista_de_vagas_em_linguagem_simples():
    from agente_carreira.radar.modelos import Aderencia, BaseVagas, Sinal, VagaEncontrada

    base = BaseVagas(itens=[
        VagaEncontrada(id="a", titulo="Dev", empresa="X", status="no_resumo", aderencia=Aderencia(nota=90)),
        VagaEncontrada(id="b", titulo="Golpe", status="eliminada", aderencia=Aderencia(nota=95),
                       sinais=[Sinal(tipo="golpe:pix", mensagem="pix")]),
        VagaEncontrada(id="c", titulo="Aplicada", empresa="Y", status="salva", aderencia=Aderencia(nota=70)),
    ])
    aplicada = Candidatura(vaga_id="c", vaga_titulo="Aplicada", foco="x", variante="cv")
    aplicada.mudar_status(Etapa.APLICADA)
    candidaturas = Candidaturas(itens=[aplicada])
    assert [l.id for l in estado.linhas_vagas(base, candidaturas)] == ["a"]
    todas = {l.id: l for l in estado.linhas_vagas(base, candidaturas, "todas")}
    assert todas["a"].situacao == "Recomendada" and todas["b"].situacao == "Suspeita de golpe"
    assert todas["c"].situacao == "Já me candidatei" and list(todas) == ["b", "a", "c"]


def test_proximas_etapas_so_avancam_e_datas_amigaveis():
    c = Candidatura(vaga_titulo="Dev", foco="x", variante="cv")
    c.mudar_status(Etapa.APLICADA)
    c.mudar_status(Etapa.ENTREVISTA_RH)
    etapas = [e for e, _ in estado.proximas_etapas(c)]
    assert Etapa.EM_ANALISE not in etapas and Etapa.ENTREVISTA_TECNICA in etapas and Etapa.REPROVADO in etapas
    assert estado.data_para_cli("25/11/2026 14:30") == "2026-11-25 14:30"
    assert estado.data_para_cli("25/11/26 14h") == "2026-11-25 14:00"
    assert estado.data_para_cli("  ") is None
    with pytest.raises(ValueError):
        estado.data_para_cli("amanhã")


def test_candidaturas_em_andamento_primeiro():
    a = Candidatura(id="a", vaga_titulo="A", foco="x", variante="cv")
    a.mudar_status(Etapa.APLICADA)
    b = Candidatura(id="b", vaga_titulo="B", foco="x", variante="cv")
    b.mudar_status(Etapa.APLICADA)
    b.mudar_status(Etapa.ENTREVISTA_RH, quando=datetime(2026, 11, 25, 17, tzinfo=timezone.utc))
    r = Candidatura(id="r", vaga_titulo="R", foco="x", variante="cv")
    r.mudar_status(Etapa.APLICADA)
    r.mudar_status(Etapa.REPROVADO, motivo="inglês")
    colecao = Candidaturas(itens=[a, r, b])
    assert [l.id for l in estado.linhas_candidaturas(colecao)] == ["b", "a"]
    linhas = estado.linhas_candidaturas(colecao, mostrar_encerradas=True)
    assert [l.id for l in linhas] == ["b", "a", "r"] and linhas[2].proximo == "Motivo: inglês"
    assert linhas[0].proximo.startswith("Entrevista RH em 25/11")


def test_lista_numerada_vira_botoes():
    from agente_carreira.app.execucao import opcoes_numeradas

    linhas = ["Etapa encerrada.", "  1. perfil técnico", "  2. inglês", "  3. outro", ""]
    assert opcoes_numeradas(linhas) == [("1", "Perfil técnico"), ("2", "Inglês"), ("3", "Outro")]
    assert opcoes_numeradas(["  1. só um"]) == []
    assert opcoes_numeradas(["  1. a", "  3. b"]) == []                     # sequência quebrada: não arrisca


def test_varias_areas_viram_uma_busca_cada_e_comandos_existem():
    respostas = {"focos": ["backend-dotnet", "dados", "suporte"], "niveis": ["estagio", "junior"],
                 "contratos": ["estagio", "clt"], "cidades": "Belo Horizonte, Contagem", "remoto": False,
                 "salario": "R$ 1.500,50"}
    comandos, puladas = estado.comandos_busca(respostas, existentes={"dados"})
    assert [c[3] for c in comandos] == ["backend-dotnet", "suporte"]        # nome = área
    assert puladas == [estado.FOCOS["dados"]]
    assert comandos[0][comandos[0].index("--salario-minimo") + 1] == "1500.50"
    assert "--sem-remoto" in comandos[0] and "Belo Horizonte, Contagem" in comandos[0]
    criar = get_command(cli_app).commands["busca"].commands["criar"]
    opcoes = {o for p in criar.params for o in p.opts}
    assert all(t in opcoes for c in comandos for t in c if t.startswith("--"))
    for invalida, mensagem in (({**respostas, "focos": []}, "área"), ({**respostas, "niveis": []}, "nível"),
                               ({**respostas, "salario": "mil"}, "número")):
        with pytest.raises(ValueError, match=mensagem):
            estado.comandos_busca(invalida, set())


def test_varias_buscas_criadas_pela_cli():
    from agente_carreira.radar.modelos import carregar_config

    comandos, _ = estado.comandos_busca({"focos": ["backend-dotnet", "dados"], "niveis": ["estagio"],
                                         "contratos": ["estagio"], "remoto": True}, set())
    for comando in comandos:
        assert _rodar(comando, [])[0] == 0
    assert [b.nome for b in carregar_config().buscas] == ["backend-dotnet", "dados"]


def test_processo_filho_conversa_com_a_janela(tmp_path):
    """Cada janela roda num processo próprio: a pergunta chega como linha de controle e a resposta volta por stdin."""
    import json
    import os
    import subprocess
    import sys

    from agente_carreira.app.filho import MARCA

    cv = tmp_path / "cv.txt"
    cv.write_text("Ana Teste\nana@example.com\n\nCompetências\nC#, SQL\n", encoding="utf-8")
    ambiente = dict(os.environ, AGENTE_CARREIRA_DATA=str(tmp_path / "dados"), PYTHONIOENCODING="utf-8")
    processo = subprocess.Popen([sys.executable, "-m", "agente_carreira.app.filho", "importar", str(cv)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", bufsize=1, env=ambiente)
    perguntas, texto = [], []
    for linha in iter(processo.stdout.readline, ""):
        if MARCA in linha:
            perguntas.append(json.loads(linha.split(MARCA, 1)[1][len("PERGUNTA "):]))
            processo.stdin.write(json.dumps({"valor": True}) + "\n")
            processo.stdin.flush()
        else:
            texto.append(linha)
    assert processo.wait(timeout=60) == 0
    assert [p["tipo"] for p in perguntas] == ["sim_nao"] and "Perfil-mestre criado" in "".join(texto)
    assert (tmp_path / "dados" / "perfil-mestre.json").is_file()


def test_parar_com_pergunta_aberta_cancela_com_calma(tmp_path):
    """O pedido de parar chega no lugar da resposta: a tarefa termina como 'Cancelado', sem ser morta."""
    import json
    import os
    import subprocess
    import sys

    from agente_carreira.app.filho import MARCA, PEDIDO_PARAR

    cv = tmp_path / "cv.txt"
    cv.write_text("Ana Teste\nana@example.com\n\nCompetências\nC#, SQL\n", encoding="utf-8")
    ambiente = dict(os.environ, AGENTE_CARREIRA_DATA=str(tmp_path / "dados"), PYTHONIOENCODING="utf-8")
    processo = subprocess.Popen([sys.executable, "-m", "agente_carreira.app.filho", "importar", str(cv)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", bufsize=1, env=ambiente)
    texto = []
    for linha in iter(processo.stdout.readline, ""):
        if MARCA in linha:
            processo.stdin.write(PEDIDO_PARAR + "\n")
            processo.stdin.flush()
        else:
            texto.append(linha)
    assert processo.wait(timeout=60) == 130
    assert "Cancelado" in "".join(texto)
    assert not (tmp_path / "dados" / "perfil-mestre.json").exists()


def test_canal_interrompe_a_tarefa_quando_nao_ha_pergunta():
    import io
    import time

    from agente_carreira.app.filho import PEDIDO_PARAR, Canal

    interrupcoes = []
    canal = Canal(io.StringIO(PEDIDO_PARAR + "\n"), interromper=lambda: interrupcoes.append(1))
    for _ in range(50):
        if canal.fechada.is_set():
            break
        time.sleep(0.02)
    assert interrupcoes == [1] and canal.parar.is_set()
    assert canal.esperar_resposta() is None  # parada: nenhuma pergunta nova espera resposta


def test_saida_vai_para_o_log_quando_o_app_fecha(tmp_path, monkeypatch):
    from agente_carreira.app.filho import LOG_SEGUNDO_PLANO, Saida

    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))

    class JanelaFechada:
        def write(self, _texto):
            raise OSError(22, "Invalid argument")

        def flush(self):
            pass

    saida = Saida(JanelaFechada(), ["vagas", "rodada"])
    assert saida.escrever("\x1b[32mBuscando vagas…\x1b[0m\n")
    assert not saida.escrever("\x1ePERGUNTA {}\n", controle=True)  # pergunta sem ninguém para responder
    log = (tmp_path / "app" / LOG_SEGUNDO_PLANO).read_text(encoding="utf-8")
    assert "agente vagas rodada" in log and "Buscando vagas…" in log and "\x1b" not in log


# ---------------------------------------------------------------- tela de vagas

def _base_para_tela():
    from agente_carreira.radar.modelos import Aderencia, BaseVagas, VagaEncontrada

    agora = datetime.now(timezone.utc)
    return BaseVagas(itens=[
        VagaEncontrada(id="a", titulo="Desenvolvedor .NET Júnior", empresa="Omega", local="Belo Horizonte, MG",
                       modelo="hibrido", nivel="junior", status="no_resumo", primeira_coleta=agora,
                       aderencia=Aderencia(nota=74, atendidos=["C#", ".NET"], lacunas=["Docker"], encaixe_cargo=1.0)),
        VagaEncontrada(id="b", titulo="Estagiário em TI", empresa="Beta", local="Contagem, MG", nivel="estagio",
                       status="no_resumo", primeira_coleta=agora - timedelta(days=3),
                       aderencia=Aderencia(nota=52, estimada=True)),
        VagaEncontrada(id="c", titulo="Analista de Suporte", empresa="Gama", local="Remoto", modelo="remoto",
                       status="no_resumo", aderencia=Aderencia(nota=30)),
    ])


def test_abas_separam_recomendadas_e_outras_pela_nota():
    base, cands = _base_para_tela(), Candidaturas()
    assert [l.id for l in estado.linhas_vagas(base, cands, "recomendadas", 50)] == ["a", "b"]
    assert [l.id for l in estado.linhas_vagas(base, cands, "outras", 50)] == ["c"]
    estimada = estado.linhas_vagas(base, cands, "recomendadas", 50)[1]
    assert estimada.nota_texto == "≈52"


def test_procurar_filtrar_e_ordenar():
    linhas = estado.linhas_vagas(_base_para_tela(), Candidaturas(), "todas")
    assert [l.id for l in estado.filtrar_linhas(linhas, "net omega")] == ["a"]
    assert [l.id for l in estado.filtrar_linhas(linhas, "contagem")] == ["b"]   # procura também no local
    assert [l.id for l in estado.filtrar_linhas(linhas, modelo="remoto")] == ["c"]
    assert [l.id for l in estado.filtrar_linhas(linhas, nivel="estagio")] == ["b"]
    assert [l.id for l in estado.ordenar_linhas(linhas, "empresa", False)] == ["b", "c", "a"]
    assert [l.id for l in estado.ordenar_linhas(linhas, "encontrada", True)][-1] == "b"   # a mais antiga por último


def test_quando_foi_encontrada_e_nota_explicada():
    agora = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)
    assert estado.quando_encontrada(agora, agora) == "hoje"
    assert estado.quando_encontrada(agora - timedelta(days=1), agora) == "ontem"
    assert estado.quando_encontrada(agora - timedelta(days=5), agora) == "há 5 dias"
    vaga = _base_para_tela().buscar("a")
    explicacao = estado.explicar_nota(vaga.aderencia)
    assert explicacao[0] == "Você tem: C#, .NET" and "Pede e não está no seu perfil: Docker" in explicacao
    assert "O cargo e o nível combinam com as suas buscas." in explicacao
    assert estado.resumo_da_vaga(vaga).startswith("Omega · Belo Horizonte, MG · Híbrido · Júnior · encontrada")


def test_acoes_rapidas_salvam_e_descartam_sem_janela():
    from agente_carreira.radar.acoes import FocoNecessario, registrar_feedback, salvar_vaga
    from agente_carreira.radar.modelos import carregar_base, salvar_base
    from agente_carreira.vagas import carregar_vagas

    salvar_base(_base_para_tela())
    with pytest.raises(FocoNecessario):
        salvar_vaga("a")                                  # a vaga não diz a área
    assert salvar_vaga("a", "backend-dotnet") == "backend-dotnet"
    salvar_vaga("a", "backend-dotnet")                     # salvar de novo não duplica a vaga-alvo
    assert carregar_base().buscar("a").status == "salva" and len(carregar_vagas().vagas) == 1
    registrar_feedback("c", False, "area", descartar=True)
    c = carregar_base().buscar("c")
    assert c.status == "descartada" and c.feedback.motivo == "area"
    assert [l.id for l in estado.linhas_vagas(carregar_base(), Candidaturas(), "outras")] == []
