# Próximos requisitos — Agente de Carreira

Os 92 requisitos funcionais da especificação estão implementados (M1 a M8). Esta lista é a fase seguinte. Ela reúne o que ficou pendente no uso real e o que o uso mostrou que falta. Os IDs seguem o padrão da especificação, com o prefixo novo **RF-EV** (evolução).

**Prioridade:** Essencial (bloqueia o uso diário), Importante (melhora muito o resultado), Desejável.

## 1. Pendências do uso real (Essencial)

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| RF-EV-01 | **Retornos das candidaturas pelo Outlook na web.** "Ler e-mails de retorno" (RF-AC-02) usa hoje IMAP ou `.eml`, e nenhum dos dois está configurado. Deve usar a mesma leitura do Outlook na web que os alertas. | Um e-mail de "entrevista" ou "não seguiremos" de uma empresa com candidatura aberta move a etapa no funil, ou pede confirmação quando é ambíguo, sem marcar o e-mail como lido. |
| RF-EV-02 | **Avisos do agente sem SMTP.** Hoje as notificações ficam só em arquivo. Oferecer push pelo ntfy (aplicativo no celular) configurado pelo app, ou um aviso do Windows na própria máquina. | A busca das 7h avisa no celular ou na tela o resumo e as vagas acima do limiar. |
| RF-EV-03 | **Busca no LinkedIn com login na página nova** (`/jobs/search-results/`). A página nova ignora filtros e não traz lista de links; a leitura deve clicar cartão a cartão, ou usar as páginas públicas se você liberar essa permissão. | Uma busca de "estágio TI" em BH traz pelo menos 15 vagas com título, empresa e local, sem perder os filtros de nível e local. |
| RF-EV-04 | **Glassdoor pelo site com verificação humana feita por você.** O agente pausa na verificação ("Humans only"), avisa, espera você resolver e lê os resultados. Sem ninguém por perto, pula o Glassdoor naquele dia. | Depois da verificação, a busca traz vagas com título, empresa e link; a busca das 7h não trava se a verificação aparecer. |
| RF-EV-05 | **Validar a Candidatura Simplificada do LinkedIn numa vaga real**, acompanhada por você: seletores, etapas e a parada antes de "Enviar candidatura". | Numa vaga real, o agente preenche todas as etapas que sabe e para na revisão; o botão de envio nunca é clicado. |
| RF-EV-06 | **Respostas prontas preenchidas.** Pretensão salarial (estágio e CLT), disponibilidade de início, carga horária, inglês e "por que esta empresa" ainda estão vazias, e sem elas os formulários param. | Banco de respostas com os itens do Anexo C revisados por você; as perguntas comuns dos formulários são respondidas sem parar. |

## 2. Candidatura e preenchimento (Importante)

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| RF-EV-07 | **Perguntas da Gupy respondidas na hora**, como no LinkedIn: no formulário de candidatura, ler cada pergunta e responder só com o banco aprovado e o perfil (RN-09). | Numa candidatura da Gupy, as perguntas conhecidas são preenchidas e as desconhecidas ficam marcadas para você. |
| RF-EV-08 | **Carta ou mensagem por vaga** no campo "Apresente-se" ou "Carta", escrita a partir do kit (motor local ou IA com autorização). | Mensagem de até 700 caracteres, só com fatos do perfil, colada no campo certo e mostrada antes do envio. |
| RF-EV-09 | **Currículo sob medida visível antes do envio**: botão "Ver currículo desta vaga" no app e comparação com o currículo-base. | Você abre o PDF da vaga antes de candidatar e vê o que mudou. |
| RF-EV-10 | **Currículo em inglês** com o mesmo modelo, para vagas em inglês ou remotas no exterior. | Vaga com anúncio em inglês gera o currículo em inglês, em 1 página e legível por ATS. |
| RF-EV-11 | **Vagas.com e outros alertas só com links de rastreamento:** abrir o link de rastreamento com cuidado (nunca o de "cancelar inscrição") para descobrir a vaga, respeitando o robots.txt. | Os alertas de "Nova vaga compatível" viram vagas com link real; nenhum link de descadastro é aberto. |

## 3. Busca e notas (Importante)

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| RF-EV-12 | **Mais descrições lidas por busca.** As vagas que chegam só com o título ganham nota reduzida. Ler mais descrições por rodada (com pausas) e usar a descrição do e-mail quando houver. | 90% das vagas recomendadas com descrição lida. |
| RF-EV-13 | **Nota explicada no app**: ao clicar numa vaga, mostrar por que ela tem aquela nota (o que você tem, o que falta, filtros) e as vagas parecidas. | Cada vaga mostra os requisitos atendidos, as lacunas e os motivos de eliminação em linguagem simples. |
| RF-EV-14 | **Remoto: decisão sua.** Hoje vagas remotas de qualquer lugar entram. Opção no app: "remoto de qualquer lugar", "só remoto de empresas de MG" ou "sem remoto". | A escolha muda a lista na próxima reavaliação. |
| RF-EV-15 | **Empresas-alvo pelo app**: cadastrar a página de carreira de uma empresa (Gupy da empresa, site próprio) sem terminal. | Empresa cadastrada pelo app entra na busca seguinte. |

## 4. Robustez e manutenção (Importante)

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| RF-EV-16 | **Testes com páginas reais salvas** (RNF-14): guardar, sem dados pessoais, uma cópia das páginas do LinkedIn, da Gupy e do Outlook usadas nos seletores, para detectar quebras antes do uso. | Uma mudança de layout aparece nos testes com o nome do site, antes de afetar a busca. |
| RF-EV-17 | **Aviso de "site mudou" no app**, com o que fazer: a faixa de andamento mostra quando uma fonte parou e qual comando reativa. | Fonte parada aparece na tela inicial com o botão "Reativar" ou "Ver o problema". |
| RF-EV-18 | **Segurança do navegador compartilhado:** a porta de controle local só existe enquanto há tarefa aberta (já fecha sozinha); impedir o acesso de outros usuários do Windows e registrar cada conexão. | Nenhuma conexão de fora do agente consegue controlar o navegador; o log mostra cada tarefa que o usou. |
| RF-EV-19 | **Dados pessoais na nuvem:** o projeto está numa pasta do OneDrive, então `data/` (perfil, currículos, candidaturas) é sincronizado. Oferecer mover `data/` para fora do OneDrive ou criptografar. | Você escolhe onde os dados ficam, e o app mostra isso em Configurações. |

## 5. Experiência no app (Desejável)

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| RF-EV-20 | **Painel dentro do app**, com gráficos (vagas por semana, retornos, funil) em vez de abrir o navegador. | Tela "Relatórios" mostra os gráficos sem sair do app. |
| RF-EV-21 | **Simulado de entrevista**: perguntas prováveis da vaga, uma de cada vez, com dicas a partir das evidências do perfil. | A partir de "Preparar para entrevista", você treina as respostas e salva as melhores no banco de respostas. |
| RF-EV-22 | **Atualização periódica pelo LinkedIn**: lembrar a cada 30 dias de baixar o ZIP do LinkedIn e mostrar o que mudou no perfil. | Lembrete mensal e comparação antes e depois ao importar. |
| RF-EV-23 | **Instalador** para usar sem `uv` nem terminal (um clique), com atalho e navegador incluídos. | Um computador sem Python instala e abre o app pelo atalho. |

## 6. Melhorias no que já existia (feitas em 18/11/2026)

Revisão do produto pronto com os dados reais (116 vagas, a tarefa agendada e a gravação dos arquivos). IDs com o prefixo **RM** (melhoria).

| ID | Melhoria | Situação |
|----|----------|----------|
| RM-01 | **Busca das 7h confiável.** Ela nunca tinha rodado: a última tentativa foi recusada pelo Windows, e uma busca perdida não era recuperada. Agora a tarefa é criada por XML: roda sem janela, recupera a busca perdida assim que o PC liga, funciona na bateria e para sozinha depois de 2 h. A tela Início mostra a última busca automática e avisa se ela não rodou. | Feito. **Falta você recriar a tarefa uma vez** (Configurações → "Busca automática todo dia" → Agendar). |
| RM-02 | **Tarefas ao mesmo tempo sem perder nada.** Cada gravação relê o arquivo e junta as mudanças: a busca não desfaz o "Não tenho interesse" clicado no meio dela, nem as configurações mudadas enquanto roda. | Feito |
| RM-03 | **Nada fica pela metade.** A gravação é atômica, e "Parar" pede à tarefa que pare com calma (fecha o navegador) antes de forçar. Fechar o app com tarefas rodando pergunta se é para parar tudo ou deixar terminando. | Feito |
| RM-04 | **Cópias de segurança diárias** (7 dias), com restauração pelo app ou por `agente copias`. Arquivo danificado volta sozinho para a última cópia boa. | Feito |
| RM-05 | **Nota das vagas recalibrada.** Antes, uma vaga de SAP que só citava "SQL" ficava em 1º (75) e estágios em TI sem descrição ficavam perto de 0. Agora entram um dicionário maior de tecnologias, cobertura com pouca evidência puxada para o meio, encaixe de cargo e nível, desconto para anúncio em inglês com inglês básico e nota estimada ("≈") quando não há descrição. | Feito |
| RM-06 | **Aviso de vaga exclusiva ou afirmativa** (PcD, mulheres, pessoas negras...), sem eliminar e sem guardar nada sobre você. | Feito |
| RM-07 | **Tela de Vagas nova:** abas Recomendadas e Outras, procurar, filtros, ordenação, coluna "Encontrada", painel de detalhes com a nota explicada e seleção de várias vagas. | Feito |
| RM-08 | **Ações na hora**, sem janela de texto: salvar, "Não tenho interesse" (que agora tira a vaga da lista) e "Lembrete feito". | Feito |
| RM-09 | **Resumo diário mais curto:** as vagas de nota baixa vão para uma lista no fim. | Feito |
| RM-10 | **Início coerente:** "Vagas boas" usa o limiar de candidatura, e o passo do e-mail reconhece a leitura do Outlook pelo navegador. | Feito |
| RM-11 | **Código dividido por área** (CLI em 5 módulos, uma classe por tela do app), com um teste que confere todas as importações. | Feito |

Sobre o **RF-EV-19**: ele ficou mais urgente. A pasta do navegador do agente (`data/navegador`, com os logins do LinkedIn e do Outlook) também está dentro do OneDrive.

## Ordem sugerida

1. RF-EV-06 (respostas prontas) e RF-EV-01 (retornos pelo Outlook): destravam as candidaturas e o funil.
2. RF-EV-05 (validar o LinkedIn numa vaga real) e RF-EV-07 (perguntas da Gupy): candidaturas completas no site.
3. RF-EV-03 e RF-EV-04 (LinkedIn e Glassdoor pelo site) e RF-EV-12 (descrições): mais e melhores vagas.
4. RF-EV-02 (avisos) e RF-EV-17 (site mudou): o agente avisa você em vez de você ir olhar.
5. O resto conforme o uso.
