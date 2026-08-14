# GURPS 4e Calculadora

Calculadora multi-ferramentas para o sistema **GURPS 4th Edition** construída com Python e Tkinter.

Interface gráfica com suporte a **Português (BR)** e **Inglês**, sistema de unidades métricas (metros) e 7 calculadoras que implementam as regras do Basic Set Revised.

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-green)
![GURPS](https://img.shields.io/badge/System-GURPS_4e-red)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Funcionalidades

### 1. Knockback (Empurrão)
- Calcula a distância em jardas que um alvo é empurrado
- Tipos de dano: Crushing (sempre), Cutting (se DR não penetrado), Impaling/Piercing (não causa knockback)
- Fórmula: `jardas = dano / (ST do alvo - 2)`
- Verificação de equilíbrio com penalidades por jarda adicional
- Bônus de +4 para Equilíbrio Perfeito

### 2. Investida / Slam (Charge)
- Dano mútuo: `(HP × velocidade) / 100` para atacante e defensor
- Tipos de colisão: Cabeça a Cabeça, Pela Costas, De Lado
- Queda automática se dano ≥ 2× do oponente
- Rotação DX necessária se dano ≥ dano do oponente

### 3. Quedas (Falls)
- Tabela completa de velocidade de queda (1-50 jardas)
- 4 tipos de superfície: Dura, Macia, Elástica, Água
- Redução por Acrobatics (-5 jardas / -~4.5m)
- Redução por Swimming (dano zero na água)
- Trauma flexível: 1 HP por 5 de dano

### 4. Colisões (Collisions)
- Cálculo de velocidade de colisão (soma, diferença, unilateral)
- Modificadores por tipo de superfície
- Suporte a objetos imóveis (paredes, chão)
- Fórmula: `(HP × velocidade) / 100`

### 5. Explosões (Explosões)
- Raio da explosão: 2 × dados de dano
- Raio de fragmentação: 5 × dados de dano
- Dano colateral: `dados / (3 × distância)`
- Explosão interna: ignorar DR, modificadores por local do corpo
- Tabela REF completa (14 tipos de explosivos)

### 6. Queda de Objetos (Falling Objects)
- Dano baseado na distância de queda
- Interações com Size Modifier (SM)
- Penalidades de movimento/defesa para objetos grandes
- Regras de Drop Attack com habilidade Dropping (padrão 15)

### 7. Combate (Combat)
- Rolagem de ataque (3d6 vs habilidade)
- Rolagem de defesa (3d6 vs defesa efetiva)
- Tabela de dano completa (ST 1-100, thrust/swing)
- Cálculo de Dodge, Parry e Block
- Modificadores de ferimento para 11 tipos de dano
- Acertos e erros críticos

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
│   └── combat.py                    # Combate
├── utils/                           # Utilitários
│   ├── dice_roller.py               # Motor de rolagem de dados
│   └── i18n.py                      # Sistema de internacionalização
├── i18n/                            # Arquivos de tradução
│   ├── pt_BR.json                   # Português (Brasil)
│   └── en_US.json                   # Inglês
└── README.md
```

> **Nota:** O PDF de referência do GURPS 4e Basic Set Revised não está incluído no repositório por questões de direitos autorais.

---

## Requisitos

- **Python 3.8+**
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

### Conversão de Unidades

A interface exibe valores em **metros**, mas os cálculos internos usam **jardas** (padrão GURPS). A conversão é automática: **1 jarda = 0,9144 metros**.

---

## Referências

Todos os cálculos são baseados no **GURPS 4th Edition Basic Set Revised**:

| Calculadora | Páginas de Referência |
|-------------|----------------------|
| Knockback | p. 378 |
| Slam/Charge | p. 371 |
| Falls | p. 430-431 |
| Collisions | p. 430-431 |
| Explosions | p. 414-415 |
| Falling Objects | p. 431 |
| Combat | p. 368-370, 374-376, 377-379, 381 |

---

## Arquitetura

- **Zero dependências externas** — usa apenas a biblioteca padrão do Python
- **Design modular** — cada calculadora é uma classe independente
- **Separação de responsabilidades** — lógica de cálculo separada da interface
- **Internacionalização** — 111 chaves de tradução em 2 idiomas
- **Interface escura** — tema escuro para melhor leitura

### Estatísticas

| Métrica | Valor |
|---------|-------|
| Total de linhas (Python) | ~2.900 |
| Arquivos Python | 12 |
| Calculadoras | 7 |
| Chaves i18n | 111 (×2 idiomas) |
| Dipêndencias externas | 0 |

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
# GurpsCalculadora
# GurpsCalculadora
