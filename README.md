# GURPS 4e Calculadora

Calculadora multi-ferramentas para o sistema **GURPS 4th Edition** construída com Python e Tkinter.

Versão atual: **v1.6.0**. Interface gráfica em **Português (BR)** e **Inglês**, com perfis Basic, Realista e Cinematográfico claramente separados.

### Interface Oficina

O menu lateral organiza as ferramentas em áreas recolhíveis. **Início** tem
cartões de acesso direto a Dados, Tiro, Corpo a corpo e Trauma, além de favoritos,
recentes e um resumo da sessão. Use **Ctrl+K** ou **Buscar ferramentas** para ir
direto a um módulo pelo nome em português ou inglês.

Em **Tiro**, **Impactos**, **Força**, **Magia**, **Poderes e Psi**, **Veículos**,
**Social** e **Batalhas**, os parâmetros ficam ao lado do resultado quando há
espaço. Em janelas estreitas, os painéis ficam empilhados. O resultado tem resumo
e memória de cálculo recolhível. Opções de combate, resistência e logística
ficam em seções separadas. Em **Dados**, o formulário e os atalhos ficam juntos;
o total, a exportação e as páginas de resultados têm um painel próprio.

Em **Aparência**, escolha o tema claro ou escuro, a fonte e as cores de fundo,
painéis e destaque. A prévia não altera a janela principal até aplicar; as cores
são salvas por tema e podem voltar ao padrão. O menu **Exibir** permite recolher
a navegação, consultar a sessão e importar/exportar configurações numéricas.
A Oficina usa apenas os controles do Tkinter, sem carregar imagens dos mockups.
Os catálogos grandes oferecem filtros, favoritos e consulta dos dados completos.
Resultados têm cópia, exportação, comparação e histórico temporário; ao trocar
idioma/unidades, o texto antigo é preservado com seu contexto original, sem rerrolar.
Antes de aplicar um ataque ou lesão à sessão, uma prévia pede confirmação.
Consulte [ENTREGA_GUI.md](ENTREGA_GUI.md) para o escopo implementado e os limites.

Em **Veículos**, o editor cria cópias personalizadas sem modificar registros publicados.
Em **Poderes e Psi**, o construtor calcula custos com modificadores selecionados e permite
salvar/importar/exportar configurações. Em **Magia**, o assistente ajuda a preencher custo
e tempo variáveis; não estima regras ausentes nem altera a sessão.

**Estado da revisão:** a numeração acima é a identificação existente, não uma
certificação de conclusão do plano v1.3–v1.6. Os cinco módulos novos ainda são
parciais. Consulte [AUDITORIA_IMPLEMENTACAO.md](AUDITORIA_IMPLEMENTACAO.md) para
correções verificadas e pendências. Os executáveis/ZIPs Linux e Windows e o ZIP de
fontes foram atualizados como compilações de desenvolvimento, com os reparos de
compatibilidade dos catálogos expandidos. Windows foi validado sob Wine, não nativamente.

Os registros novos foram preservados. Magias com custo/tempo variável ou incompleto
pedem valores escolhidos na aba Magia; entradas psi sem parâmetros operacionais são
identificadas como referências, não como poderes prontos para resolver.

O menu **Unidades** alterna entre métrico e imperial/GURPS, independentemente do
idioma. Campos de distância, velocidade e alcance preservam a quantidade física
durante a troca; presets mantêm as unidades originais dos motores. Resultados já
apresentados em metros e jardas continuam mostrando ambas as unidades. Preferências
de idioma e unidades são salvas na pasta de dados do usuário.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-green)
![GURPS](https://img.shields.io/badge/System-GURPS_4e-red)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Funcionalidades

### 1. Recuo (Knockback)
- Calcula a distância em jardas que um alvo é empurrado
- Tipos de dano: Crushing (sempre), Cutting (se DR não penetrado), Impaling/Piercing (não causa knockback)
- Fórmula: um múltiplo completo de `ST - 2` por jarda; para ST 3 ou menor, uma jarda por ponto de dano
- Verificação de equilíbrio com penalidades por jarda adicional
- Bônus de +4 para Equilíbrio Perfeito

### 2. Investida (Slam)
- Dano mútuo: `(HP × velocidade) / 100` para atacante e defensor
- Tipos de colisão: Cabeça a Cabeça, Pela Costas, De Lado
- Queda automática se dano ≥ 2× do oponente
- Teste de DX do defensor quando o dano do atacante é igual ou maior, sem chegar ao dobro

### 3. Quedas (Falls)
- Tabela completa de velocidade de queda (1-112 jardas) e fórmula revisada para distâncias maiores
- 4 tipos de superfície: Dura, Macia, Elástica, Água
- Redução por Acrobatics (-5 jardas / -~4.5m)
- Redução por Swimming (dano zero na água)
- DR de armadura e trauma contundente quando a armadura detém todo o dano

### 4. Colisões (Collisions)
- Cálculo de velocidade de colisão (soma, diferença, unilateral)
- Modificadores por tipo de superfície
- Suporte a objetos imóveis (paredes, chão)
- Limite de dano `HP + DR` para obstáculos quebráveis
- Fórmula: `(HP × velocidade) / 100`

### 5. Explosões (Explosões)
- Raio da explosão: 2 × dados de dano
- Raio de fragmentação: 5 × dados de dano
- Dano colateral: `dados / (3 × distância)`
- Fragmentos resolvidos como ataques de habilidade 15, com DR e lesão por acerto
- Explosão interna: ignora DR e trata o dano como um ataque aos vitals (×3)
- Tabela REF completa (14 tipos de explosivos)

### 6. Queda de Objetos (Falling Objects)
- Dano baseado na distância de queda
- Interações com Size Modifier (SM)
- Penalidades de movimento/defesa para objetos grandes
- Ataque à distância com Dropping, modificador de alcance e Dodge para alvos cientes

### 7. Combate (Combat)
- Rolagem de ataque (3d6 vs habilidade)
- Rolagem de defesa (3d6 vs defesa efetiva)
- Tabela de dano completa (ST 1-100, thrust/swing) e progressão para ST acima de 100
- Cálculo de Dodge, Parry e Block
- Modificadores de ferimento para 11 tipos de dano
- Acertos e erros críticos

### 8. Tiro (Ranged Combat)

- Cálculo determinístico da habilidade efetiva e da probabilidade em 3d6
- Resolução opcional de ataque, Dodge, quantidade de acertos, dano, DR e lesão
- Distância + velocidade, Size Modifier (SM), Aim, Accuracy (Acc), RoF, Rcl, Bulk, Malf. e hit locations
- Shotguns, rajadas, 1/2D, Max, divisores de armadura, armas dependentes de ST e Afflictions
- Perfis isolados: **Basic Set** (padrão), **Realista** (High-Tech + Tactical Shooting) e **Cinematográfico** (Gun Fu)
- Catálogo incorporado com 732 registros estatísticos do Basic Set, High-Tech, Low-Tech e Ultra-Tech
- Pesquisa, edição temporária, importação, exportação e presets JSON salvos na pasta de dados do usuário
- Memória de cálculo linha por linha com livro e página de cada modificador

### 9. Trauma (Injury)

- Motor compartilhado de dano, DR, divisores de armadura, dano penetrante e lesão
- Localizações do Basic Set e localizações expandidas de Martial Arts, isoladas por perfil
- Armaduras direcionais, parciais, flexíveis, rígidas, em camadas, ablativas e com DR dividido
- Choque, Ferimento Grave (Major Wound), incapacitação, desmembramento, knockdown, stun, inconsciência e morte
- Módulos opcionais de sangramento e trauma detalhado desligados por padrão
- Catálogo incorporado com 296 armaduras e importação/exportação de presets JSON

### 10. Corpo a corpo (Melee Combat)

- Manobras do Basic Set e opções de Martial Arts, com Deceptive Attack, Rapid Strike, Dual-Weapon Attack e Telegraphic Attack
- Resolução separada de ataque, Defesa Ativa, dano e aplicação confirmada à sessão
- Alcance (Reach), ST mínima, mão inábil, armas desequilibradas e estado Ready
- Grappling: agarrar, libertar-se, derrubar, imobilizar, estrangular, locks, throws e wrenching, sem Control Points
- Catálogos incorporados com 359 armas, 113 técnicas e 104 estilos; estilos são orientativos
- **Preparar sessão**: importação em lote de fichas `.gcs` (esquema v5) e da exportação Fantasy Grounds PC da Master Library; não cria nem altera fichas
- Cenários com elenco, grupos, ordem manual e ordenação por Velocidade Básica (DX desempata; empates restantes conservam a ordem manual)
- HP, FP, ferimentos e outras reservas são independentes para cada participante e cenário. Histórico, desfazer e salvamento atômico: uma falha não publica alterações em memória
- **Tiro → Trauma**: transfere um acerto comum já rolado, incluindo a redução por 1/2D quando aplicável; revise o alvo e a armadura antes de aplicar. Acertos com efeitos especiais ficam na aba Tiro.

### 11. Força e Esforço (Strength and Effort)

- Basic Lift, carga, empurrar, puxar, Lifting ST, Striking ST e Arm ST
- Extra Effort e Super-Effort, com separação entre Powers e a extensão cinematográfica de Supers
- Ataque Total (Forte), Mighty Blows, Weapon Master e conversão de bônus por dado
- Integração com o dano do combate corpo a corpo e custos em FP por `StateDelta`

### 12. Magia, Poderes e Psi

- Motores independentes para conjuração, construção de habilidades e uso psi
- Magia padrão com mana, custos, alcance, área, tempo, resistência, reservas de energia, previsão de manutenção e renovação manual
- Magias variáveis podem exigir parâmetros do mestre; sistemas alternativos sem motor próprio são marcados **Só referência**
- Psi: **Emotion Sense** e **Mental Surgery** têm níveis publicados calculáveis. Outras entradas psi são referências; efeitos narrativos ficam com o mestre.
- Consulte o status e a fonte no catálogo. Magia/Psi podem usar FP da sessão e só o aplicam após confirmação; ER e energia externa são controladas pelo mestre.

### 13. Veículos e Naves

- Movimento, aceleração, autonomia, combustível, delta-v e tempo de viagem
- Painel **Colisões e combate veicular**: colisão entre veículos com DR de ambos, cálculo e resolução de disparos usando o motor de Tiro; os resultados não alteram a sessão
- Catálogo de veículos e suporte a veículos personalizados na pasta do usuário
- Sessão veicular com aplicação explícita e desfazer

### 14. Social e Batalhas

- Reaction Rolls, Influence Rolls simples e expandidos e consequências sociais
- Organizações, relacionamentos, forças e elementos de Mass Combat
- Troop Strength (TS), estratégia, resultado e baixas
- Sessão persistente de campanha com aplicação explícita e desfazer

### 15. Dados do mestre (GM Dice)

- Aba **Mestre → Dados**, independente das sessões de combate e campanha
- Expressões como `104d6+20`, `3d-1`, `2d20` e `1000000d6`
- Até **10 milhões de dados** por rolagem, com processamento em segundo plano,
  progresso, cancelamento e armazenamento compacto dos resultados individuais
- Soma de todos os dados, modificador e total final; resultados negativos preservados
- Detalhes numerados em páginas de 100 dados, com navegação direta por página
- Cópia da página atual e exportação de **todos** os dados em arquivo `.txt`
- Cópia só do total, até 12 favoritas e 12 expressões recentes com seus totais, e atalhos **Teste 3d6** e **Disputa Rápida**
- Troca de idioma preserva os dados e traduz a apresentação sem nova rolagem

---

## Estrutura do Projeto

```
GurpsCalculadora/
├── main.py                          # Aplicação principal (GUI Tkinter)
├── calculators/                     # Módulos de cálculo
│   ├── knockback.py                 # Empurrão
│   ├── slam.py                      # Investida/Slam
│   ├── falls.py                     # Quedas
│   ├── collisions.py                # Colisões
│   ├── explosions.py                # Explosões
│   ├── falling_objects.py           # Queda de Objetos
│   ├── combat.py                    # Adaptador do combate antigo
│   ├── ranged_combat.py             # Tiro e resolução de ataques à distância
│   ├── injury.py                    # Dano, armaduras e trauma compartilhado
│   ├── melee_combat.py              # Corpo a corpo, técnicas e grappling
│   ├── combat_session.py            # Elenco, ordem e estado por cenário
│   ├── strength.py                  # Força, esforço e dano forte
│   ├── magic.py                     # Sistemas mágicos
│   ├── powers.py                    # Powers e Psionics
│   ├── vehicles.py                  # Veículos e naves
│   └── campaign.py                  # Social Engineering e Mass Combat
├── data/
│   ├── weapons.json                 # Armas à distância
│   ├── melee_weapons.json           # Armas corpo a corpo
│   ├── armor.json                   # Armaduras
│   ├── techniques.json              # Técnicas de Martial Arts
│   ├── styles.json                  # Estilos de Martial Arts
│   ├── extended_rules.json          # Magia, poderes, psi e Mass Combat
│   └── vehicles.json                # Veículos incorporados
├── utils/                           # Utilitários
│   ├── dice_roller.py               # Motor de rolagem de dados
│   ├── weapon_catalog.py             # Catálogo e presets de tiro
│   ├── combat_catalog.py             # Catálogos e presets da v1.2
│   └── i18n.py                      # Sistema de internacionalização
├── i18n/                            # Arquivos de tradução
│   ├── pt_BR.json                   # Português (Brasil)
│   └── en_US.json                   # Inglês
├── tests/                           # Testes de regressão das regras
└── README.md
```

> **Nota:** nenhum PDF, mapa, imagem ou texto descritivo dos livros é incluído. O catálogo contém somente nomes, estatísticas de jogo e referências de página.

---

## Requisitos

- **Python 3.11+**
- **Tkinter** (incluído no Python padrão, mas pode precisar de instalação separada no Linux)

### Instalação do Tkinter

No **Windows** e **macOS**, o Tkinter já vem com o Python. Só é necessário instalar manualmente no Linux:

**Ubuntu/Debian:**
```bash
sudo apt install python3-tk
```

**Arch/Manjaro:**
```bash
sudo pacman -S tk
```

**Fedora:**
```bash
sudo dnf install python3-tkinter
```

---

## Como Executar

### Pacotes prontos (recomendado)

Os pacotes de distribuicao ja incluem tudo o que o aplicativo precisa:

- **Windows 64 bits:** extraia `GurpsCacul_Windows.zip` e abra `GurpsCalculadora.exe`.
- **Linux 64 bits:** extraia `GurpsCacul_Linux.zip` e abra `GurpsCalculadora`.

Nao e necessario instalar Python nem usar um terminal. No Linux, talvez seja
necessario marcar o arquivo como executavel em **Propriedades > Permissoes**.

### Execucao pelo codigo-fonte

### Windows

```powershell
# 1. Instalar Python (se não tiver)
# Baixe em https://python.org/downloads
# MARQUE "Add Python to PATH" durante a instalação

# 2. Clonar o repositório
git clone https://github.com/aaronmlf/GurpsCalculadora
cd GurpsCalculadora

# 3. Rodar
python main.py
```

### Linux / macOS

```bash
# Clone o repositório
git clone https://github.com/aaronmlf/GurpsCalculadora
cd GurpsCalculadora

# Execute
python3 main.py
```

---

## Uso

1. **Trocar idioma:** Menu → Idioma → Português / English
2. **Selecionar calculadora:** Clique na aba desejada
3. **Preencher campos:** Insira os valores nos campos de entrada
4. **Calcular:** Clique no botão "Calcular" / "Calculate"
5. **Rolar dados:** Use os botões de rolagem para resultados aleatórios
6. **Aplicar:** Revise o resultado e confirme em **Aplicar à sessão** quando quiser registrar o efeito

### Fichas e cenários de combate

1. Abra **Início → Preparar sessão → Fichas** e selecione vários arquivos
   `.gcs` (esquema v5) ou arquivos `.xml` exportados com **Fantasy Grounds PC**
   da [Master Library do GCS](https://github.com/richardwilkes/gcs_master_library).
   O relatório separa os arquivos aceitos dos que precisam de correção.
2. Selecione as fichas importadas e adicione as cópias desejadas ao **Elenco**.
   Escolha os grupos, mova participantes na lista ou ordene por Velocidade
   Básica. Defina agente e alvo para as calculadoras de combate.
3. Use **Recursos atuais** para editar HP, FP e reservas só neste combate.
   Você pode incluir uma reserva temporária e vinculá-la como ER em Magia ou Psi.
   Em **Cenários**, salve ou abra cópias nomeadas.

Os arquivos originais permanecem intactos. Modelos `.gct` e catálogos como
`.adq`, `.skl` e `.eqp` não são fichas completas: use-os no GCS e salve
uma ficha `.gcs` para importar. Defesas ou SM efetivo ausentes devem ser
informados na calculadora; armas e DR por localização não são equipados
automaticamente.

### Mapa de batalha

Abra **Combate → Mapa** ou use **Mapa** em **Preparar sessão**. Comece com
um tabuleiro vazio ou escolha **Mapa → Importar fundo PNG**. Ajuste o formato
da grade, a distância entre os centros e a origem para alinhar a imagem.
A grade hexagonal começa com 1 jarda por célula.

- Selecione alguém do elenco, clique em **Colocar** e escolha a célula.
  Arraste o marcador para movê-lo. Use a roda para zoom e o botão do meio
  para deslocar a vista.
- Defina agente e alvo no menu **Marcador**. **Enviar a Tiro** preenche
  a distância, sem alterar arma, perícia, velocidade, cobertura ou visibilidade.
  A régua respeita o sistema de unidades escolhido; a regra de alcance recebe
  o valor exato em jardas. Se as posições mudarem, envie a nova distância.
- Abra **Visão dos jogadores** para compartilhar só essa janela ou movê-la
  a um segundo monitor. Ela acompanha as alterações do mestre e não exibe
  HP, FP, nomes de grupos, notas do mestre ou marcadores ocultos. A imagem
  do fundo é pública nessa janela; escolha um PNG sem segredos impressos.

O cenário salva a grade, posições, visibilidade e referência do fundo.
O PNG fica na pasta de dados local, fora do executável, e o arquivo
original não é alterado. O mapa é offline e não inclui neblina,
iluminação dinâmica ou controle remoto pelos jogadores.

### Testes

```bash
python3 -m unittest discover -v
```

### Gerar os executaveis

Os arquivos de empacotamento estao em `packaging/`:

- Linux: `packaging/build_linux.sh`
- Windows: `packaging/build_windows.bat`

Os scripts compilam e verificam o executável a partir da mesma cópia das fontes.
Os ZIPs e seus hashes ficam em `dist/releases/<tag>/<linux|windows>/`.
Veja o [guia de empacotamento e verificação](packaging/RELEASE.md) para requisitos,
teste de abertura e lista dos arquivos incluídos.

### Conversão de Unidades

Escolha **Métrico** ou **Imperial** no menu de unidades. A apresentação muda sem alterar a medida guardada; a conversão entre metros e jardas usa **1 jarda = 0,9144 metros**.

---

## Referências

Todos os cálculos são baseados no **GURPS 4th Edition Basic Set Revised**:

| Calculadora | Páginas de Referência |
|-------------|----------------------|
| Knockback | p. 378 |
| Slam | p. 371 |
| Falls | p. 430-431 |
| Collisions | p. 430-431 |
| Explosions | p. 414-415 |
| Falling Objects/Dropping | p. 189, 431 |
| Combat | p. 368-370, 374-376, 377-379, 381 |
| Ranged Combat | p. 364, 372-374, 407-410, 548-550 |
| Injury/Trauma | p. 377-424; Martial Arts p. 136-139 |
| Melee Combat/Grappling | p. 364-371, 374-377; Martial Arts p. 96-129 |
| Strength/Super-Effort | p. 15-17, 353-357, 365; Powers p. 58; Supers p. 24-25 |
| Magic/Powers/Psi | Magic p. 7-14; Thaumatology p. 19-214; Powers p. 7-13, 154-161 |
| Vehicles/Spaceships | p. 430-432, 466-470; Spaceships p. 37-39, 48-67 |
| Social/Mass Combat | Social Engineering p. 20-72; Mass Combat p. 30-42 |

O perfil Realista referencia regras selecionadas de **Martial Arts**, **High-Tech** e **Tactical Shooting**. O perfil Cinematográfico acrescenta opções de **Martial Arts** e **Gun Fu**. Estatísticas de armas e armaduras também são catalogadas de **Low-Tech** e **Ultra-Tech**; regras de outros perfis nunca são aplicadas silenciosamente ao perfil Basic Set.

---

## Arquitetura

- **Zero dependências externas** — usa apenas a biblioteca padrão do Python
- **Design modular** — cada calculadora é uma classe independente
- **Separação de responsabilidades** — lógica de cálculo separada da interface
- **Internacionalização** — chaves equivalentes em Português (Brasil) e Inglês, com terminologia do Basic Set
- **Interface escura** — tema escuro para melhor leitura

### Estatísticas

| Métrica | Valor |
|---------|-------|
| Armas catalogadas | 1.091 (732 à distância + 359 corpo a corpo) |
| Armaduras / técnicas / estilos | 296 / 113 / 104 |
| Ferramentas | 17 |
| Idiomas da interface | PT-BR e inglês |
| Dependências externas | 0 |

## Contribuindo

Contribuições são bem-vindas! Sinta-se livre para:
- Reportar bugs
- Sugerir novas funcionalidades
- Melhorar a tradução
- Otimizar cálculos

---

## Créditos

- **Steve Jackson Games** — Criadores do sistema GURPS
- **GURPS 4th Edition Basic Set Revised** — Referência para todos os cálculos
