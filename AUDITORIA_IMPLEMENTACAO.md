# Revisão do plano v1.3–v1.6

## Estado

Implementação parcial. A existência de abas, modelos e entradas de catálogo não
significa que os cinco itens solicitados estejam concluídos. Nenhuma nova versão
estável foi declarada. Os pacotes Linux e Windows foram reconstruídos como
compilações de desenvolvimento após o reparo dos catálogos expandidos.

## Continuação — Mass Combat

Entrega de logística, perseguição e exceções de estratégia concluída em 15/09/2026.
Evidências e escopo em `CONCLUSAO_MASS_COMBAT.md`: 345 casos validados em Linux
e Windows via Wine, inspeção PT/EN e reconstrução dos pacotes com os novos módulos.
Isso não altera o estado parcial do roadmap geral. As notas abaixo são históricas.

- Perseguição/recuperação (p. 38) agora têm motor e diálogo PT/EN: Liderança,
  reação aleatória em falha, Hold/Pursue, Cav/Air, perdas logísticas separadas,
  recuperação do vencedor/aniquilação mútua e TS final. Aplicação atômica com
  confirmação, rejeição de resultado adulterado/desatualizado e desfazer.
  271 testes Linux passaram. Estado detalhado da entrega ativa em
  `CONCLUSAO_MASS_COMBAT.md`; manutenção logística e exceções ainda em andamento.
  Os pacotes anteriores ainda não contêm esta continuação.

- Ajustes de estratégia por superioridade (pp. 34–35): Deliberate Attack/Art,
  Indirect Attack/C3I, Deliberate Defense/F, Mobile Defense/Cav ou Nav e
  Skirmish/Air, Art ou F. Acréscimo único de +1, separado do bônus geral de
  classes na memória de cálculo; aplicado simetricamente às duas forças.
  Usa os bônus elegíveis após redução por encontro. 258 testes Linux passaram.
  Raid/Recon, repetição de Indirect Attack, elegibilidade contextual, logística
  e perseguição continuam pendentes; esta etapa não certifica o módulo completo.
  Pacotes Linux/Windows reconstruídos incluindo os seletores e as exceções sem
  combate das duas etapas anteriores. 57 testes direcionados passaram no Python
  Windows via Wine; ambos os executáveis abriram na verificação automatizada.
  Wine não substitui teste em Windows nativo.

- Continuação da GUI: seletores traduzidos para estratégias de ambos os lados,
  mensagens de pausa/retirada e bloqueio de aplicação de eventos sem combate.
  Parley nos dois lados representa negociação aceita; recusa e iniciativa ainda
  não automatizadas. Mudança de estratégia invalida a aplicação pendente.
  255 testes Linux passaram. Fonte atualizada; executáveis ainda são os anteriores.

- Exceções sem combate (p. 36), no motor: Parley bilateral retorna pausa;
  retirada contra retirada/defesa retorna `no_battle`. Não há rolagens,
  baixas, transferência de PB nem delta aplicável como rodada de combate.
  Parley unilateral exige decisão explícita e permanece bloqueado, sem
  presumir aceitação ou recusa. `BattleCalculation.event` distingue esses casos.
  Ainda faltam controles de estratégias nominais/negociação na GUI e o fluxo
  de encerramento automático por retirada. Não confundir esta proteção da API
  com a implementação completa de negociação ou perseguição.
  Validação: 253 testes Linux passaram, incluindo todas as combinações de
  retirada/defesa, ausência de rolagens e rejeição da aplicação desses eventos
  como rodada. Executáveis não reconstruídos nesta etapa; ZIP de fonte atualizado.
- PB integrado a cálculo, resultado, confirmação e sessão: bônus de estratégia,
  transferência do PB adversário, ganho por ataque, limitação de Raid, exceções de
  All-Out Defense/Mobile Defense/Fighting Retreat e desfazer (p. 37).
- Editor de TS elegível por classe, separado da TS agregada: faixas 2:1/3:1/5:1,
  mínimo de 1% da TS inimiga, neutralizadores e redução Air/Art/C3I em encontros
  (pp. 31–32). Alocações e contexto são salvos ao aplicar a rodada.
  Terreno, elegibilidade e alocação de elementos multifunção são informados pelo mestre;
  ainda não há derivação automática desses totais a partir de um editor de exércitos.
- Duas estratégias defensivas, exceto Parley, passam a Skirmish (p. 36).
- Validação da adição de PB/classes: 251 testes Linux e 50 testes direcionados
  no Python Windows via Wine passaram. Editor inspecionado nos dois idiomas.

- Separados `calculate()` (sem rolagens) e `resolve()`; batalhas inválidas não rolam
  dados nem produzem baixas aplicáveis. Rolagens explícitas inválidas não são substituídas.
- Baixas anteriores impõem −1 por 5%, sem reduzir TS durante a batalha (Mass Combat p. 37).
  A interface permite informar os totais anteriores e comparar estratégias efetivas antes de rolar.
- Deltas de rodada acumulam baixas aditivamente na sessão de campanha. A API
  `finalize_battle()` aplica uma única vez os percentuais finais confirmados pelo mestre,
  depois de perseguição/recuperação, e pode ser desfeita.
- Interface agora permite aplicar rodadas, finalizar a batalha e desfazer a última alteração
  da campanha, sempre com confirmação. Aplicações repetidas e resultados desatualizados são
  rejeitados; salvar uma rodada e suas forças iniciais forma um único passo de desfazer.
  Estado e baixas são recuperados ao reabrir o app. Percentuais finais de perseguição e
  recuperação continuam sendo informados pelo mestre, não calculados automaticamente.
- Validação desta etapa: 242 testes Linux passaram, incluindo cancelamento de diálogos,
  falha de gravação, rejeição de reaplicação, encerramento e restauração por desfazer.
  Mais 41 testes direcionados passaram no Python Windows via Wine; a tela de Batalhas
  foi inspecionada em PT-BR e inglês. Wine não substitui validação em Windows nativo.
- Corrigida a simetria de All-Out Attack/Defense, modificadores de baixas de estratégias
  e margem de Indirect Attack/Skirmish. Removidas mudanças automáticas de moral sem regra.
- Ainda faltam condições de elegibilidade e combinações especiais de estratégias,
  repetição de Indirect Attack, ajustes de estratégia condicionados à superioridade,
  alocação automática por elementos, logística e perseguição.
  Estas correções não certificam o módulo inteiro. Executáveis anteriores não são
  atualizados automaticamente por uma alteração nos fontes.

## Continuação de 2026-09-15

- Corrigida a tabela de distância para magia de Informação (B241); ela não usa a tabela de tiro.
- Regra de 16 aplicada antes da rolagem em magia e psi, para alvos vivos/sapientes, com
  exceção explícita para outros alvos. Resistências mostram margens e favorecem o defensor
  nos empates (B241, B348–349). Interface inclui resistência efetiva e opção de alvo.
- Magia cerimonial tem motor próprio: líder 15+, assistentes com contribuições individuais,
  limites de espectadores/oposição, bônus por energia, tempo ×10, falhas em 16/17/18 e
  gasto integral das contribuições mesmo em sucesso crítico (B238). Editor de grupo na aba Magia.
  Manutenção cerimonial ainda exige resolução separada; não é simulada pela conjuração inicial.
- Lifting baseada em HT sem Extra Effort aumenta BL por margem somente para levantar,
  não para transporte/encumbrance (B205). Power Blow inclui pré-requisitos, concentração,
  ST dupla/tripla e 1 FP por tentativa (B215). Disponíveis na aba Força; a prévia de Power
  Blow é explicitamente condicional. Integração completa à resolução corpo a corpo permanece pendente.
- Esforço Extra contínuo pode ser resolvido automaticamente por intervalos de até um minuto,
  reavaliando a penalidade por FP faltantes e interrompendo na primeira falha/insuficiência.
  As rolagens explícitas continuam disponíveis para testes; o personagem de entrada não é alterado.
- Sessão veicular com esquema, salvamento atômico, confirmação, rejeição de resultados
  desatualizados, desfazer e preservação de arquivos inválidos. Falha de gravação não altera
  a memória. Segundos fracionários não são descartados. Não equivale a combate espacial completo.
- Organizações/relacionamentos podem ser editados na interface e salvos com confirmação.
  São registros do mestre, sem progressão ou bônus sociais inventados. Aplicação/desfazer de
  campanha agora preserva a memória se o salvamento falhar; alvos inexistentes não são ignorados.
- Essas correções não certificam os catálogos completos nem concluem os sistemas mágicos
  alternativos, Spaceships, Mass Combat e integrações ainda listadas abaixo.
- Validação desta continuação: 231 testes Linux e 97 testes Python Windows via Wine
  passaram. Editores de cerimônia e campanha inspecionados em PT-BR/inglês em tela virtual.
  Wine não substitui teste nativo Windows.

## Reparo dos catálogos expandidos — 2026-09-06

- Falha de inicialização reproduzida: `PsiTechniqueRecord` não aceitava `cost_fp`
  e `notes`. Esses campos agora são preservados; o custo da técnica é separado do
  custo em pontos da habilidade. Metadados psi `levels`, `cost` e `notes` não são descartados.
- Preservadas as 813 magias, 134 habilidades psi, 14 técnicas psi e 126 veículos.
- Custos de magia como `min.`/`hr.` provinham de colunas trocadas; classe com
  inicial maiúscula também deixava de ativar regras de Area/Missile.
- Reextração por coordenadas da tabela de Magic: 828 linhas estatísticas; 802
  entradas do catálogo atual correspondem por nome e página. Correções ficam em
  `data/magic_table_stats.json`, sem sobrescrever os registros expandidos originais.
- Referências de regressão: Create Fire = 2/1, 1 segundo; Mind-Reading = 4/2,
  10 segundos. Custos/tempos variáveis ou não reconhecidos exigem parâmetros
  explícitos na interface. Fireball não recebe mais custo fixo inventado.
- Entradas psi sem parâmetros operacionais permanecem referências consultáveis;
  custo em pontos nunca é interpretado como FP e resolução fica bloqueada.
- **Não é uma certificação editorial de todo o catálogo**: extrações ambíguas,
  condições específicas de cada feitiço e estatísticas de veículos/psi ainda
  precisam de verificação completa nos livros. A correção impede travamentos
  e resultados baseados em campos claramente inválidos, sem inventar mecânicas.
- Validação: **176 testes** no Linux com interface virtual; **54 testes** de
  cálculos/catálogos/interface no Python Windows sob Wine. Ambos os executáveis
  abriram a janela principal, confirmada pelo título, e incorporam os 11 JSONs.
- ZIPs Linux, Windows e fontes reconstruídos. Windows nativo e outras
  distribuições Linux ainda não foram testados.

## Histórico anterior de tradução e distribuição

- Todos os códigos literais de erro dos motores Strength, Magic, Powers, Vehicles
  e Campaign têm mensagens específicas PT/EN, com teste que detecta novas lacunas.
- Faixas de resultado de batalha traduzidas. Nomes publicados de equipamentos e
  sistemas preservam o original; revisão editorial integral dos catálogos continua pendente.
- Empacotamento do executável inclui somente JSONs das pastas data/i18n.
- ZIPs rejeitam livros, imagens, links simbólicos e nomes de caminho inseguros.
  Fontes excluem arquivos temporários e ZIPs antigos. Falhas preservam o ZIP anterior.
- **172 testes passaram** em tela virtual. Linux reconstruído; 10 JSONs incorporados
  confirmados no arquivo executável, sem PDFs/imagens. Processo iniciou sem erro e
  permaneceu ativo até encerramento controlado após seis segundos.
- Linux e ZIP de fontes atualizados nesta continuação. Windows não reconstruído:
  Wine existe, mas o ambiente temporário com Python/PyInstaller Windows não está mais
  disponível. Compatibilidade Linux fora do sistema de compilação não foi validada.

## Correções verificadas nesta revisão

- Basic Lift arredondado quando >= 10 lb (Basic Set, p. 15).
- Conversão de adds em dados opcional: +7 vira 2d, +4 vira 1d; sem conversão
  automática de modificadores negativos (Basic Set, p. 269).
- Mighty Blows exige Attack; não se acumula com All-Out Attack. FP é cobrado
  por tentativa, incluindo erros e ataques defendidos; FP insuficiente bloqueia
  a resolução de ataques múltiplos (Basic Set, p. 357).
- Falha em Extra Effort volta à capacidade normal; sucesso crítico dispensa FP;
  falha crítica produz perda de HP. Resolver não altera o input.
- Lifting-only Super-Effort não aumenta throwing ou knockback; colisões usam HP.
- Validação de esforço integrada ao cálculo corpo a corpo; ST de dano de armas
  limitada a três vezes Min ST antes dos bônus de esforço.
- Magia: reduções usam habilidade-base, ajustada por low mana; tempo arredondado
  para cima; Missile não recebe redução de tempo. No mana bloqueia conjuração.
- Magia: falha comum custa 1 energia quando aplicável, falha crítica custo total,
  crítico bem-sucedido custo zero; débitos separados de FP, ER e energia externa.
- Resistência de magia e psi é copiada, não alterada no objeto de entrada.
- Movimento integra aceleração seguida de velocidade constante; viagem revalida
  combustível; naves não recebem limite de velocidade terrestre e sobrevivem ao undo.
- Influence comum usa Quick Contest; resultado por faixa, sem deslocamento de
  reação inventado. Diplomacy aponta comparação pendente com Reaction Roll (B359).

## Ainda necessário para atender integralmente ao pedido

### Continuação: esforço e interface de Força

- Teste de Extra Effort com penalidade pelos FP faltantes, antes de pagar o uso atual.
- Entrada explícita de Lifting baseada em Will, usando -1 por 10% de aumento de BL.
- Motivação aprovada pelo mestre (+5) disponível no modelo, desligada por padrão.
- Machine impede esforço extra comum e Mighty Blows.
- Super-Effort contínuo distingue transportar (1 FP/minuto) de sustentar (1 FP/hora).
- Esforço extra comum acima de um minuto exige resolução por intervalos; não é
  resolvido por uma única rolagem ignorando a fadiga acumulada.
- Falha crítica em Mighty Blows adiciona 1 HP de lesão que ignora DR; a localização
  do membro usado permanece pendente de confirmação, além dos demais efeitos críticos.
- Aba Força: seleção explícita de Lifting/Striking/ST total, FP atual/máximo, Will,
  Lifting, percentual de esforço, duração e modo contínuo; Calcular e Resolver separados.
  O perfil Cinematográfico não seleciona mais automaticamente Super-Effort em ST total.
- Novos rótulos PT/EN com paridade. Inicialização e cálculo da interface nos dois
  idiomas verificados em tela virtual; isso não substitui revisão visual completa.
- Validação atual: 159 testes passando. Pacotes anteriores permanecem sem reconstrução.

### Adição solicitada: idiomas e sistema imperial

- Camada de unidades com fatores exatos, sem arredondamento intermediário de entradas.
- Seletor métrico/imperial implementado inicialmente nos resultados de Força (kg/lb),
  independente do idioma e sem alterar valores salvos ou estatísticas dos livros.
- Rótulos principais dos resultados de Força traduzidos e novas chaves PT/EN equivalentes.
- Validação após essa adição: 162 testes passando.
- Continuação: menu **Unidades** aplica métrico/imperial aos campos físicos existentes
  de Investida, Quedas, Colisões, Explosões, Objetos Cadentes, Tiro, Corpo a corpo,
  Magia e Psi; resultados de Força, Veículos e velocidade de colisão usam a escolha.
  Resultados antigos já duplos (m/yd) mantêm as duas representações. Abas sem
  quantidades dimensionais não recebem conversões artificiais em HP, FP, ST ou TS.
- Os valores canônicos e presets mantêm suas unidades originais; controles de exibição
  não reescrevem as quantidades ao trocar idioma/unidades. Alcances estruturados de
  armas são convertidos nos campos; notação textual publicada permanece original.
- Preferências de idioma/unidades salvas atomicamente na pasta do usuário.
- Perfis, usos de força, ambientes veiculares e sistemas mágicos traduzidos sem
  alterar seus identificadores internos. Resumos, reações e diagnósticos frequentes
  traduzidos; códigos desconhecidos permanecem identificados como diagnóstico técnico.
- Corrigido rótulo de habilidade de magia: o motor espera perícia básica, não efetiva;
  Psi possui rótulo separado. Rolagens resumidas não exibem mais dicionários Python.
- Validação: **168 testes passando**, incluindo testes reais de widgets em Xvfb,
  mudanças PT/EN, frações, atualizações de catálogo, preferências e ausência de
  observadores acumulados em reconstruções. Testes também rejeitam chaves JSON
  duplicadas e conferem placeholders e formatos entre idiomas.
- **Pendente:** revisão editorial exaustiva de glossário e de todos os catálogos,
  tradução específica de diagnósticos menos comuns, inspeção visual completa e
  reconstrução dos executáveis/ZIPs. Não declarar esses itens concluídos pelos testes.

### Pendências por módulo

1. **Magia/Powers/Psi:** resolvedores específicos dos sistemas alternativos restantes,
   catálogos completos, pré-requisitos, efeitos integrados a Injury,
   política completa de recursos/manutenção e aplicação à sessão pela interface.
   Sistemas alternativos sem motor próprio estão bloqueados, não simulados pela
   fórmula de magia padrão. Clerical e magia padrão ainda precisam de revisão completa.
2. **Vehicles/Spaceships:** colisões determinísticas separadas de rolagens, controle
   por perícia, curvas/frenagem/terrenos conforme equipamento, sistemas danificados,
   combate espacial completo, editor modular de naves e catálogos auditados.
   Persistência de movimento e editor de estatísticas operacionais já estão implementados.
3. **Social/Mass Combat:** modificadores sociais completos, organizações/relacionamentos
   utilizáveis na interface, classes/reconhecimento/estratégias, logística, pursuit
   e acumulação correta de baixas por rodada antes da atualização definitiva de TS.
4. **Força/Super-Effort:** representação explícita dos níveis comprados e aprimorados,
   usos de Arm ST, integração das novas opções de Lifting e Power Blow ao combate,
   Throwing Art, Strongbow e integração em todos os módulos previstos.
5. **Ataques fortes:** vantagens/técnicas restantes, confirmação e consequências
   localizadas dos críticos de esforço, limites de arma sob Super-Effort e controles
   completos de dano/esforço no corpo a corpo.

Também faltam tradução de todas as saídas e erros novos, aplicação confirmada dos
deltas nas abas novas, revisão visual nos dois idiomas e reconstrução/validação de
Linux, Windows e ZIP de fontes. Os PDFs permanecem fontes locais, fora dos pacotes.

## Verificação

`python3 -m unittest discover -s tests -q`

Os testes de regressão desta revisão estão em `tests/test_rules_audit.py`.
Dois testes antigos foram corrigidos para respeitar B15 e a natureza opcional de B269.
