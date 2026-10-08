# Interface — estado da entrega

Adição em 08/10/2026: **Mestre → Dados / Game Master → Dice** aceita até
10 milhões de dados, mostra cada resultado em páginas de 100 dados, subtotal,
modificador e total. Rolagens grandes e exportação completa em `.txt` usam
processamento em segundo plano, progresso e cancelamento. A troca de idioma
preserva os números e traduz a apresentação; nenhuma sessão é alterada.
365 testes passaram, incluindo rolagem de um milhão de dados na interface,
paginação, cancelamento, exportação integral, tradução e persistência da navegação.
Conferência adicional: 10 milhões de d6 reais, 40 MB de resultados e soma verificada.
Os 25 testes direcionados de dados/interface/traduções/preferências também passaram
com Python Windows via Wine. Executáveis Linux e Windows reconstruídos com os dois
novos módulos; ZIPs Linux, Windows e código-fonte atualizados.

Validação de Mass Combat em 15/09/2026: formulário Batalhas inspecionado em
PT-BR/inglês no topo, meio e fim da rolagem; diálogos de logística, reposições e
pós-batalha conferidos nos dois idiomas. Executáveis reconstruídos e abertura
verificada em Linux e Windows via Wine. Ver `CONCLUSAO_MASS_COMBAT.md` para
escopo, testes e limites; esta conclusão não certifica todo o roadmap geral.

## Implementado e testado

- Reposições por elemento: percentual, custo e prazo nominais; orçamento,
  pagamento confirmado, ordem persistente, confirmação do tempo transcorrido
  e recuperação ao concluir. Cancelamento, reabertura e desfazer em PT/EN.

- Logística mensal para atacante/defensor: verba, LS por meio, NT, rotas,
  terreno, temporada, prontidão e Administração. Configuração e pagamento mensal
  são ações distintas e confirmadas; calcular/rolar nunca gasta verba. Planos
  persistidos e validados, cancelamento e desfazer testados em PT/EN.

- Batalhas: memória de cálculo identifica separadamente o ajuste de estratégia
  por superioridade, traduzido em PT-BR/inglês e com referência às pp. 34–35.
  Abrange Ataque Deliberado/Indireto, Defesa Deliberada/Móvel e Escaramuça.

- Batalhas: seleção de estratégia de cada lado em PT-BR/inglês, distinta do
  valor da perícia Estratégia. Eventos sem combate têm mensagens próprias e
  não criam rodada aplicável. Alterar a estratégia invalida resultados pendentes.
  Negociação aceita é representada selecionando Parley nos dois lados; recusa
  e mudanças de iniciativa ainda exigem avaliação do mestre.

- Batalhas: campos de PB, comparação de PB atual/futuro, editor de TS elegível e
  neutralizadores por classe e opção de batalha de encontro. Parâmetros persistidos
  ao aplicar rodadas; elegibilidade e alocação de unidades permanecem escolhas explícitas.

- Batalhas: aplicação confirmada de rodadas, baixas acumuladas sem redução prematura de TS,
  encerramento com percentuais finais informados pelo mestre e desfazer da campanha.
  A interface atual usa duas forças simples de TS agregada; não é ainda um editor de exércitos.

- Controles de resistência em Magia/Psi, incluindo Regra de 16 e exibição das margens.
- Grupo de magia cerimonial com contribuições explícitas e parâmetros aplicados sem rolagem.
- Lifting treinada e Power Blow na aba Força, com prévia condicional e pré-requisitos.
- Aplicação confirmada de movimento veicular, persistência e desfazer.
- Editor de organizações e relacionamentos, compartilhado pelas abas Social e Batalhas.

- Navegação agrupada; página inicial com favoritos e recentes; menu lateral recolhível.
- Preferências separadas e versionadas: tema claro/escuro, fonte de 9 a 18, tamanho da janela,
  última ferramenta, favoritos de ferramentas e de catálogo. Salvamento atômico na pasta do usuário.
- Busca e filtros nos catálogos grandes; seleção confirmada, favoritos, consulta dos campos completos.
- Validação de números nos formulários, incluindo telas antigas, Tiro, Corpo a corpo e Trauma.
  Expressões de dano e notações de equipamento continuam sob validação dos motores próprios.
- Rolagem vertical/horizontal para alcançar campos em telas estreitas ou com fontes grandes.
- Resumo, memória de cálculo, cópia e exportação de resultados; comparação e histórico de até 20 saídas por ferramenta.
- Preservação das saídas ao reconstruir a interface, com identificação do idioma/unidades originais;
  nunca há uma nova rolagem apenas por mudar uma preferência.
- Aviso de resultado desatualizado quando entradas mudam.
- Janela de consulta da sessão, HP/FP, condições, histórico e desfazer.
- Prévia confirmada antes de aplicar Corpo a corpo, Grappling ou Trauma; resoluções incompatíveis
  com o estado atual da sessão são rejeitadas.
- Importação/exportação de presets numéricos por ferramenta. Não inclui equipamento, opções
  de regras ou estado da sessão; não é um construtor de personagens.
- Ajuda de uso e novas mensagens em português/inglês; testes de chaves e placeholders.
- Editor de estatísticas operacionais de veículos: nova cópia, atualização de registros
  personalizados, importação/exportação JSON e conversão de velocidade/aceleração/autonomia.
- Construtor de custo de poderes: vantagem, níveis, modificadores, fonte de poder e habilidade
  alternativa; configuração salva na pasta do usuário e importação/exportação. Modificadores
  manuais são identificados como Custom e exigem aprovação do mestre.
- Assistente de custo/tempo de magia com notação do catálogo, referência e aplicação explícita
  aos campos, sem rolagens ou gasto de recursos.

## Limites explícitos

Os testes de interface são executados em tela virtual Linux e com Python Windows sob Wine.
A validação via Wine não é um teste nativo do sistema Windows.

- A revisão editorial integral de cada arma, magia, veículo, poder e técnica ainda não está certificada.
  O navegador não identifica um registro como conferido sem evidência de auditoria.
- O texto de um resultado preservado não é retraduzido/recalculado. Seu contexto original é informado.
- Histórico de cálculos é temporário; exportação conserva uma saída. Histórico de combate permanece
  sob a persistência e os limites da sessão já existente.
- Presets numéricos não são um construtor de personagens. O editor de veículos preserva campos
  complexos não expostos; não constrói sistemas modulares de Spaceships. O construtor de poderes
  calcula custos, mas não valida integralmente compatibilidade de vantagens/modificadores ou resolve efeitos.
- Exemplos completos conferidos nos livros e assistentes especializados para todos os sistemas
  mágicos ainda dependem das pendências de regras descritas em AUDITORIA_IMPLEMENTACAO.md.
- A verificação via Wine não substitui teste nativo no Windows. Compatibilidade universal entre
  distribuições Linux também não é certificada por uma build na máquina de desenvolvimento.

## Por que ainda não se declara 100% do plano original

O núcleo de usabilidade foi ampliado, mas permanecem a auditoria editorial, os assistentes dos
sistemas alternativos completos e a validação nativa multiplataforma. Nenhuma dessas pendências é resolvida apenas
por aumentar a quantidade de telas ou pelo sucesso dos testes automatizados.
