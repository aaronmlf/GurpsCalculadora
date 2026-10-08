# Entrega concluída: logística, perseguição e exceções de estratégia

Conclusão restrita a esta entrega de Mass Combat, não ao roadmap integral do
aplicativo. Referências: Mass Combat pp. 13–14 e 34–38. PDFs só locais.

## Critérios de conclusão e evidências

- [x] Perseguição: Liderança, escolha no sucesso, reação 1d na falha, modificadores
  Cav/Air, perdas logísticas 1d×5%, sem perseguição contra força já destruída.
  Motor `battle_aftermath.py`; testes `test_battle_aftermath.py`.
- [x] Recuperação depois da perseguição: redução por manter o campo, recuperação
  do vencedor, aniquilação mútua, perdas finais/TS e destruição da retaguarda.
  Exemplo TS 75.5, 35% inicial, vitória -> 15% final -> TS 64.
- [x] GUI de pós-batalha PT/EN, calcular sem dados, resolver, aplicar confirmado;
  deltas atômicos, desfazer, proteção contra reaplicação e resultados adulterados.
- [x] Inspeção visual do diálogo de pós-batalha nos dois idiomas. Corrigidos
  rótulos dos lados no resumo para não confundir participantes com o vencedor.
- [x] Logística: LS Land/Naval/Air, custos de criação e manutenção, capacidade e
  rotas de abastecimento, Administração, financiamento prioritário da retaguarda,
  prontidão reduzida, terreno, temporada, reposição proporcional e consequências.
- [x] GUI e sessão logística: entradas explícitas, resultados explicados, aplicação
  confirmada, persistência, migração, desfazer e importações inválidas.
- [x] Estratégias: Indirect Attack repetido/consecutivo com histórico persistente;
  bônus completos de Raid, opção contra logística, perdas em retiradas; Desperate;
  recusa de Parley e troca de iniciativa; restrições de encontro/confusão/cerco,
  Defense Bonus/Deliberate Attack; Rally e condições de encerramento da batalha.
- [x] Integração entre essas estratégias, perdas logísticas, encerramento e perseguição.
- [x] Auditoria de testes por requisito, exemplos, traduções e interface.
- [x] Rebuild Linux/Windows, abertura, ZIPs íntegros com JSONs e sem PDFs/imagens dos livros.

## Validação final — 15/09/2026

Executáveis Linux e Windows reconstruídos; abertura da janela principal verificada
em Linux e em Windows via Wine (não equivale a teste em Windows nativo).
Módulos novos e todos os JSONs de `data/` e `i18n/` conferidos nos dois executáveis.
Suíte de 344 testes passou em ambas as plataformas; o teste adicional de integração
`test_mass_campaign_flow` também passou em ambas, totalizando 345 casos validados.
Interface Batalhas inspecionada no topo, meio e fim da rolagem em PT-BR e inglês;
diálogos de logística, reposições e pós-batalha também inspecionados nos dois idiomas.

| Requisito | Evidências automatizadas em `tests/` |
| --- | --- |
| LS, rotas, custos, Administração, prontidão e reposições | `test_logistics.py`, `test_replacements.py` |
| Perseguição, recuperação, perdas e aplicação confirmada | `test_battle_aftermath.py` |
| Indirect Attack, Raid, Desperate e perdas logísticas | `test_strategy_history.py` |
| Parley, DB, contexto, Rally e iniciativa | `test_parley.py`, `test_defense_bonus.py`, `test_battle_context.py`, `test_rally.py`, `test_initiative.py` |
| Encerramento, persistência, desfazer e proteção contra adulteração | `test_battle_end.py`, `test_battle_integrity.py`, `test_mass_combat_audit.py` |
| Incursão → retirada → perseguição → recuperação, sem duplicar perdas | `test_mass_campaign_flow.py` |
| Traduções, unidades e fluxos da interface | `test_preferences_translations.py`, `test_unit_gui.py` |

Entradas que dependem do mestre continuam explícitas: elegibilidade de classes,
superioridade de Recon, contexto/terreno, custos e prazos nominais de reposição e
tempo transcorrido. Cálculos não modificam a sessão; aplicação exige confirmação.
Os três ZIPs são recompostos com os binários finais e o código-fonte atualizado,
sem o acervo. O histórico abaixo registra estados intermediários já superados.

## Histórico das etapas (pendências históricas, não estado atual)

Auditoria de integração: aplicação de rodada recalcula deterministicamente a
partir dos dados já rolados, rejeitando deltas alterados sem consumir RNG.
Cerco/DB agora persistem e são restaurados. Alterações contextuais externas
exigem confirmação própria, não avançam rodadas e podem ser desfeitas.
Corrigida a penalidade −2 de Retirada Total em confusão, com memória traduzida.
Testes de integridade, restauração e alteração contextual adicionados.
Ainda não há certificação final: faltam inspeção visual consolidada, auditoria
por requisito e reconstrução/validação dos pacotes.

Iniciativa: escolhas anunciadas e respostas separadas. Apenas o oponente da
estratégia lenta pode mudar, sem cadeia de novas trocas; Parley exige recusa.
Validação da estratégia final, memória de cálculo traduzida e histórico efetivo.
Testes de simetria de permissões, recusa, ausência de cadeia e persistência.
As mecânicas principais estão implementadas; isso não encerra o objetivo antes
da auditoria das integrações, inspeção visual e validação dos pacotes.

Término No Battle integrado à confirmação da GUI e à sessão, sem dados, novas
baixas ou incremento artificial de rodada. Preserva perdas anteriores, valida
snapshot/forças/PB, salva atomicamente, desfaz e encaminha ao pós-batalha.
335 testes completos passaram. Falta iniciativa e a auditoria integral antes
dos pacotes; controles contextuais ainda precisam de revisão de integração.

Término após combate implementado: 100% de baixas, aniquilação mútua,
Retirada Total independentemente do vencedor da rodada e Retirada Combatente
com vitória/empate. Resultado de batalha distinto da margem da rodada,
confirmado ao aplicar, persistente, desfazível e bloqueando novas rodadas.
Pós-batalha recebe vencedor/retirada e rejeita mudanças incompatíveis.
Ainda falta registrar o término No Battle (sem rodada), além de iniciativa
e auditoria final de integrações/contexto.

Rally integrado: teste de Liderança−2 ao sobreviver à rodada, resultado explícito
ou aleatório, exibição antes de aplicar e transição de confusão somente na
confirmação. Condições por força (confusão atual/inicial e mobilidade) persistem,
desfazem e são recuperadas na GUI. Não há teste de Rally para força destruída.
324 testes completos e cinco novos testes direcionados passaram.
Pendências principais: iniciativa e término automático; auditoria de integrações
e controles de alteração contextual explícita durante uma batalha.

Contexto: controles de confusão, confusão inicial, mobilidade e cerco; validações
de Rally, estratégias permitidas à força confusa, Defesa Deliberada e primeira
rodada de encontro. Contador de rodadas persiste, desfaz e reinicia no encerramento.
320 testes completos passaram, seguidos de quatro novos testes contextuais.
Os testes antigos de ausência de combate agora fornecem DB/confusão quando a
estratégia exige esses pré-requisitos; nenhuma regra foi relaxada para mantê-los.
Ainda faltam transições persistentes de confusão/Rally, iniciativa e término.

DB explícito em PT/EN: somente estratégias defensivas o recebem; Ataque
Deliberado divide o DB adversário por dois, arredondando para cima, sem mexer
no PB. Encontros rejeitam Ataque/Defesa Deliberados antes da conversão de
impasse para Escaramuça. 319 testes completos passaram; depois, teste adicional
de restrição de encontro e testes direcionados de DB/tradução passaram.
Ainda pendentes: contexto de rodada/confusão/cerco, iniciativa, Rally e término.

Parley unilateral agora tem resposta explícita na GUI e no motor: aceitar pausa
sem dados; recusar usa Defesa com −1 adicional, preservado no cálculo/resolução.
Recusa contra retirada segue No Battle, e negociação bilateral sempre pausa.
Histórico aplicado registra a estratégia efetiva. Troca de iniciativa ainda falta.

Desperate integrado ao motor e aos controles opcionais PT/EN: diferença mínima
de 25 pontos percentuais de baixas, estratégias incompatíveis bloqueadas, +4
na estratégia e +10% de baixas automáticas. Modificador +1 de Misfortunes of War
exibido para o teste individual separado. Incursão contra logística não remove
as baixas automáticas de Desperate das tropas. Testes de limiar, bônus e interação.
Ainda faltam Parley/iniciativa, elegibilidade/Defense Bonus, Rally e término.

Estratégias: histórico persistente de Ataque Indireto (×2 inicial; ×1,5 com
arredondamento para cima nos usos seguintes; −2 consecutivo). Avança somente
na aplicação, desfaz e é limpo ao encerrar. Raid soma +1 por Air/Cav/Nav/Recon,
com Recon confirmado explicitamente na interface. Raid vencedor pode direcionar
baixas à logística; retiradas aplicam as baixas logísticas previstas. Acúmulo,
persistência, confirmação e integração ao pós-batalha usam o livro separado de
perdas logísticas. 302 testes completos e 10 testes direcionados passaram (quatro
casos novos de Raid/retirada após a suíte). Ainda faltam Desperate, recusa de
Parley/iniciativa, elegibilidade/Defense Bonus, Rally e término automático.

Reposições concluídas em `calculators/replacements.py` e
`utils/replacements_ui.py`: orçamento proporcional por elemento, pagamento único,
prazo explícito, avanço confirmado, restauração apenas ao concluir, persistência,
desfazer e rejeição de duplicatas/valores inválidos. Exemplo de 10% com custo
integral $1.000 e prazo 120 dias resulta em $100 e 12 dias. TS nominal informada
pelo usuário permite recuperar inclusive elementos sem sobreviventes, sem
remover o modificador de prontidão. Interface inspecionada em PT/EN.
296 testes passaram na suíte Linux. Pacotes finais ainda pendentes das estratégias.

Continuação logística: `calculators/logistics.py` implementa LS Land/Naval/Air,
custos, rotas (porto, mar+terra, base aérea), Administração, prioridade de
financiamento, terreno, temporada e prontidão; reposição tem orçamento/prazo.
`CampaignSession.apply_maintenance` aplica um mês confirmado a uma força fora
de batalha, preservando baixas permanentes e o mês de recuperação da prontidão.
14 testes direcionados de logística passam, incluindo o exemplo publicado,
salvamento atômico, migração, desfazer e rejeição de replay.
GUI/configuração logística implementadas em `utils/logistics_ui.py` para os dois
lados: salvar parâmetros/verba/LS não paga manutenção; calcular e resolver não
alteram estado; aplicar mês confirma o resultado. Configurações persistidas e
validadas, desfazer, cancelamento e reabertura testados em PT/EN. Inspeção visual
realizada nos dois idiomas. 287 testes da suíte completa e 15 testes direcionados
de logística passaram (o último teste de configuração foi adicionado após a suíte).
Reposições agora usam o fluxo próprio descrito acima; não são concedidas
instantaneamente pelo pagamento da manutenção mensal.

271 testes Linux passaram após integração de pós-batalha, incluindo preservação
de TS fracionária sem baixas e perdas logísticas no encerramento manual. Pacotes
ainda são os da etapa anterior. Não declarar a entrega concluída até todos os
critérios acima.
