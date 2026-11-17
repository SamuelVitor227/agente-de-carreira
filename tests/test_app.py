"""App de janela e atalho na Área de Trabalho."""

import pytest
from typer.main import get_command

from agente_carreira import app as app_mod
from agente_carreira.cli import app as cli_app


@pytest.fixture(autouse=True)
def dados_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_CARREIRA_DATA", str(tmp_path))
    return tmp_path


def _resolve(args):
    """Desce pelos grupos do Typer até o comando final; falha se algum nome não existir."""
    comando = get_command(cli_app)
    for nome in args:
        if not hasattr(comando, "commands"):
            break
        assert nome in comando.commands, f"'agente {' '.join(args)}' não existe"
        comando = comando.commands[nome]
    return comando


def test_todo_botao_aponta_para_comando_existente():
    for _, acoes in app_mod.GRUPOS:
        for acao in acoes:
            _resolve(list(acao.args))
    assert {"app", "atalho"} <= set(get_command(cli_app).commands)


def test_console_roda_o_proprio_modulo():
    comando = app_mod.comando_console(["funil", "preparar", "abc"], python="python.exe")
    assert comando == ["python.exe", "-m", "agente_carreira.app", "--executar", "funil", "preparar", "abc"]


def test_executar_no_console_mostra_erro_e_nao_fecha(monkeypatch, capsys):
    def sem_entrada(_prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", sem_entrada)
    assert app_mod.executar_no_console(["comando-que-nao-existe"]) == 2
    assert "Erro:" in capsys.readouterr().out
    assert app_mod.executar_no_console(["funil"]) == 0


def test_situacao_sem_perfil_orienta_a_importar():
    assert app_mod.situacao() == ['Sem perfil-mestre ainda: comece por "Importar currículo…" ou "Conectar LinkedIn (ZIP)…".']


def test_icone_tem_todos_os_tamanhos(tmp_path):
    from PIL import Image

    icone = app_mod.criar_icone(tmp_path / "a.ico")
    assert {(16, 16), (32, 32), (256, 256)} <= Image.open(icone).info["sizes"]


def test_atalho_usa_pythonw_e_caminhos_por_variavel():
    script = app_mod.script_atalho()
    assert "GetFolderPath('Desktop')" in script and "$env:AGENTE_ALVO" in script
    assert "-m agente_carreira.app" in script and "Área" not in script


def test_sem_perfil_orienta_sem_traceback(monkeypatch, capsys):
    from agente_carreira import cli

    monkeypatch.setattr("sys.argv", ["agente", "perfil", "mostrar"])
    with pytest.raises(SystemExit) as saida:
        cli.main()
    assert saida.value.code == 1
    texto = capsys.readouterr().out
    assert "Importar currículo" in texto and "agente li conectar" in texto and "Traceback" not in texto


def test_li_conectar_cria_perfil_e_sincroniza_estado(tmp_path):
    import zipfile

    from typer.testing import CliRunner

    from agente_carreira.linkedin.estado import carregar_estado
    from agente_carreira.storage import carregar_perfil

    zip_ = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_, "w") as zf:
        zf.writestr("Profile.csv", '"First Name","Last Name","Headline","Summary"\n"Ana","Teste","Dev .NET","Desenvolvo APIs"\n')
        zf.writestr("Skills.csv", '"Name"\n"C#"\n')
        zf.writestr("Email Addresses.csv", '"Email Address","Confirmed","Primary"\n"ana@example.com","Yes","Yes"\n')
    resultado = CliRunner().invoke(cli_app, ["li", "conectar", str(zip_)], input="y\n")
    assert resultado.exit_code == 0, resultado.output
    assert carregar_perfil().competencias_tecnicas == ["C#"]
    assert carregar_estado().campos["titulo"] == "Dev .NET"


def test_li_conectar_recusar_perfil_ainda_sincroniza(tmp_path):
    import zipfile

    from typer.testing import CliRunner

    from agente_carreira.linkedin.estado import carregar_estado
    from agente_carreira.storage import perfil_existe

    zip_ = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_, "w") as zf:
        zf.writestr("Profile.csv", '"First Name","Last Name","Headline"\n"Ana","Teste","Dev .NET"\n')
    resultado = CliRunner().invoke(cli_app, ["li", "conectar", str(zip_)], input="n\n")
    assert resultado.exit_code == 0, resultado.output
    assert not perfil_existe() and carregar_estado().campos["titulo"] == "Dev .NET"
