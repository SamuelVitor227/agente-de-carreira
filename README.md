# Agente de Carreira

Agente de IA para gestão de carreira: otimização de currículo, perfil no LinkedIn, busca de vagas e acompanhamento de candidaturas.

## O que o agente faz

- Mantém um **perfil-mestre único** e otimiza o currículo: versão-base melhorada a partir das vagas-alvo e versão sob medida por vaga, sem inventar nada.
- Prepara as alterações padrão do **LinkedIn** (título, Sobre, competências, Open to Work, alertas), em modo copiloto por padrão.
- Cadastra e sincroniza o currículo em **outras plataformas** (Gupy primeiro).
- **Busca vagas** por alertas de e-mail e páginas de carreira, deduplica, pontua e entrega um resumo diário até as 8h.
- Monta o **kit de candidatura**, preenche o formulário e para antes do envio; acompanha o funil até a proposta.

## Regras centrais

| Regra | Descrição |
|-------|-----------|
| RN-01 | Nada sai sem aprovação explícita |
| RN-02 | Nada é inventado no CV ou no perfil |
| RN-04 | Sem bots no LinkedIn: copiloto por padrão; modo assistido só por opção do usuário |
| RN-14 / RF-IA-02 | Claude Pro e Gemini Pro só com aviso do motor, da tarefa e dos dados enviados, e autorização a cada uso |
| RN-07 | Estágio só com matrícula ativa (Lei 11.788/2008, art. 3º, I) |

## Fases

1. **MVP** — M1 (perfil e currículo), M2 (LinkedIn em copiloto), M4 (resumo diário), M8 (aprovações e uso de IA). Portão: CA-01 a CA-10.
2. **Candidatura** — M3 (Gupy + 2 plataformas P2), M5 (candidatura assistida), M6 (funil). Portão: CA-11 e CA-12.
3. **Aprendizado** — status lido dos e-mails, painel, relatório semanal, pesos por feedback, desempenho por variante de CV.

## Status da implementação

| Requisito | Descrição | Status |
|-----------|-----------|--------|
| RF-PM-01 | Perfil-mestre estruturado (contato, objetivo, resumo, experiências, formação, certificações, projetos, competências, idiomas, links) | ✅ Implementado |
| RF-PM-02 | Importar CV de PDF/DOCX, exportação do LinkedIn (ZIP) e texto livre, com confirmação de tudo o que foi extraído | ✅ Implementado |
| RF-PM-03 | Experiência com cargo, empresa, vínculo, período, local, modelo de trabalho, responsabilidades, conquistas e tecnologias | ✅ Implementado |
| RF-PM-04 | Banco de conquistas reutilizáveis (verbo de ação, resultado com número, tecnologias, competências, evidência) | ✅ Implementado |
| RF-PM-05 | Experiências fora de TI e projetos acadêmicos com competências transferíveis | ✅ Implementado |

## Como usar

Requer Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev        # instala as dependências
uv run pytest        # roda os testes
uv run agente --help # mostra os comandos
```

Comandos principais:

```bash
uv run agente perfil criar            # cria o perfil-mestre
uv run agente perfil mostrar          # exibe o perfil completo
uv run agente importar meu-cv.pdf     # importa CV (PDF/DOCX/ZIP do LinkedIn/TXT) com confirmação
uv run agente rascunhos               # lista itens importados pendentes de confirmação
uv run agente experiencia adicionar   # registra experiência (aceita fora de TI e projetos acadêmicos)
uv run agente conquista adicionar     # adiciona conquista ao banco de conquistas
```

Os dados ficam em `data/perfil-mestre.json` (fora do git), configurável pela variável `AGENTE_CARREIRA_DATA`.

## Documentação

- [Especificação de Requisitos](docs/Agente_de_Carreira_Especificacao_de_Requisitos.pdf) — documento completo *Agente de Carreira — Especificação de Requisitos* (versão de 16/11/2026), a fonte da verdade do projeto.

## Decisões em aberto

Nível-alvo depois de 2026/2; faixa salarial; presencial fora de BH ou mudança de cidade; visibilidade do Open to Work; modo assistido no LinkedIn; construção (A: dentro do Claude, ou B: código próprio em Python ou .NET); motor padrão por tarefa; canal de notificação; plataformas P2 da fase 2.
