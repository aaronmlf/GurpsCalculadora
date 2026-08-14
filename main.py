"""
Calculadora GURPS 4e - Interface Principal

Ferramenta multiuso para cálculos do GURPS 4th Edition (Basic Set Revised).
Inclui calculadoras para: Knockback, Investida, Quedas, Colisões,
Explosões, Queda de Objetos e Cálculos de Combate.

Unidades:
- Interface: metros (m) e metros por segundo (m/s)
- Cálculos internos: jardas (yards) e jardas por segundo (yd/s)
- Conversão: 1 jarda = 0.9144 metros

Referências do Basic Set Revised:
- Damage Table: p. 16
- Combat: p. 364-416
- Knockback: p. 378
- Collisions and Falls: p. 430-431
- Explosions: p. 414-415

Estrutura do projeto:
- main.py: Interface Tkinter (este arquivo)
- calculators/: Módulos de cálculo para cada regra
- utils/: Utilitários (rolagem de dados, i18n)
- i18n/: Arquivos de tradução (pt_BR.json, en_US.json)
"""
import tkinter as tk
from tkinter import ttk, messagebox
# typing imports not needed - no type annotations in this file

from calculators.knockback import KnockbackCalculator
from calculators.slam import SlamCalculator
from calculators.falls import FallsCalculator
from calculators.collisions import CollisionsCalculator
from calculators.explosions import ExplosionsCalculator
from calculators.falling_objects import FallingObjectsCalculator
from calculators.combat import CombatCalculator
from utils.i18n import get_i18n, t
from utils.dice_roller import roll_3d6

# ─── Constantes de conversão ────────────────────────────────────────
# 1 jarda = 0.9144 metros (definição internacional)
YARDS_TO_METERS = 0.9144
METERS_TO_YARDS = 1.0 / YARDS_TO_METERS  # ≈ 1.09361


class GURPSCalculator:
    """
    Classe principal da Calculadora GURPS 4e.
    
    Gerencia a interface gráfica e coordena as calculadoras.
    Usa Tkinter para a GUI com suporte completo a internacionalização.
    """

    def __init__(self):
        """Inicializa a aplicação e todos os componentes."""
        self.root = tk.Tk()
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Inicializa calculadoras (lógica de negócio)
        self.knockback_calc = KnockbackCalculator()
        self.slam_calc = SlamCalculator()
        self.falls_calc = FallsCalculator()
        self.collisions_calc = CollisionsCalculator()
        self.explosions_calc = ExplosionsCalculator()
        self.falling_objects_calc = FallingObjectsCalculator()
        self.combat_calc = CombatCalculator()

        # Inicializa sistema de internacionalização
        self.i18n = get_i18n()

        # Variáveis de entrada (preservadas entre rebuilds de UI)
        self._init_variables()

        # Configura tema visual
        self._setup_theme()

        # Cria menu e interface
        self._create_menu()
        self._rebuild_ui()

        # Atualiza título
        self._update_title()

    def _init_variables(self):
        """
        Inicializa todas as variáveis de entrada da interface.
        
        Cada variável tk.IntVar/tk.StringVar/tk.BooleanVar é preservada
        quando a UI é reconstruída (troca de idioma).
        """
        # ─── Knockback (p. 378) ─────────────────────────────────────
        self.kb_damage_type = tk.StringVar(value="crushing")
        self.kb_basic_damage = tk.IntVar(value=10)
        self.kb_target_st = tk.IntVar(value=10)
        self.kb_target_hp = tk.IntVar(value=10)
        self.kb_target_dr = tk.IntVar(value=0)
        self.kb_perfect_balance = tk.BooleanVar(value=False)
        self.kb_effective_skill = tk.IntVar(value=10)
        self.kb_roll_result = tk.IntVar(value=11)

        # ─── Slam/Investida (p. 371) ────────────────────────────────
        self.slam_attacker_hp = tk.IntVar(value=10)
        self.slam_attacker_velocity = tk.IntVar(value=5)  # m/s
        self.slam_defender_hp = tk.IntVar(value=10)
        self.slam_defender_velocity = tk.IntVar(value=0)  # m/s
        self.slam_collision_type = tk.StringVar(value="head_on")
        self.slam_attacker_damage_bonus = tk.IntVar(value=0)

        # ─── Quedas (p. 430-431) ────────────────────────────────────
        self.falls_distance = tk.IntVar(value=9)   # metros (~10 jardas)
        self.falls_hp = tk.IntVar(value=10)
        self.falls_dr = tk.IntVar(value=0)
        self.falls_surface = tk.StringVar(value="hard")
        self.falls_acrobatics = tk.BooleanVar(value=False)
        self.falls_swimming = tk.BooleanVar(value=False)

        # ─── Colisões (p. 430-431) ──────────────────────────────────
        self.coll_obj1_hp = tk.IntVar(value=60)
        self.coll_obj1_velocity = tk.IntVar(value=23)  # m/s (~25 yd/s)
        self.coll_obj2_hp = tk.IntVar(value=10)
        self.coll_obj2_dr = tk.IntVar(value=0)
        self.coll_obj2_velocity = tk.IntVar(value=5)
        self.coll_type = tk.StringVar(value="head_on")
        self.coll_surface = tk.StringVar(value="normal")
        self.coll_immovable = tk.BooleanVar(value=False)
        self.coll_breakable = tk.BooleanVar(value=False)

        # ─── Explosões (p. 414-415) ─────────────────────────────────
        self.exp_basic_damage = tk.IntVar(value=6)
        self.exp_fragmentation = tk.IntVar(value=0)
        self.exp_distance = tk.IntVar(value=9)   # metros (~10 jardas)
        self.exp_dr = tk.IntVar(value=0)
        self.exp_direct_hit = tk.BooleanVar(value=False)
        self.exp_target_sm = tk.IntVar(value=0)
        self.exp_posture_modifier = tk.IntVar(value=0)

        # ─── Queda de Objetos (p. 431) ──────────────────────────────
        self.fo_distance = tk.IntVar(value=9)
        self.fo_object_hp = tk.IntVar(value=10)
        self.fo_target_hp = tk.IntVar(value=10)
        self.fo_target_sm = tk.IntVar(value=0)
        self.fo_object_sm = tk.IntVar(value=0)
        self.fo_dropping_skill = tk.IntVar(value=15)
        self.fo_target_aware = tk.BooleanVar(value=False)
        self.fo_target_dodge = tk.IntVar(value=8)
        self.fo_aimed = tk.BooleanVar(value=False)

        # ─── Combate (p. 368-376) ───────────────────────────────────
        # Attack Skill: Habilidade usada para acertar (ex: Sword-15)
        # NÃO é o mesmo que ST - são valores separados
        self.combat_attack_skill = tk.IntVar(value=15)
        # Effective Defense: Dodge, Parry ou Block (p. 374-376)
        self.combat_defense = tk.IntVar(value=10)
        # ST: Força do personagem, determina dano (thrust/swing)
        # Referência: Damage Table, p. 16
        self.combat_st = tk.IntVar(value=10)

    def _setup_theme(self):
        """
        Configura tema visual da aplicação.
        
        Usa tema escuro para melhor leitura durante sessões de jogo.
        """
        style = ttk.Style()
        style.theme_use('clam')

        self.colors = {
            "bg": "#2b2b2b",      # Fundo principal
            "fg": "#ffffff",      # Texto principal
            "accent": "#4a9eff",  # Cor de destaque (títulos)
            "success": "#4caf50", # Verde (sucesso)
            "warning": "#ff9800", # Laranja (aviso)
            "error": "#f44336",   # Vermelho (erro)
            "panel": "#3c3c3c",   # Fundo de painéis
            "button": "#4a9eff",  # Cor dos botões
        }

        self.root.configure(bg=self.colors["bg"])
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["fg"])
        style.configure("TButton", background=self.colors["button"], foreground=self.colors["fg"])
        style.configure("TNotebook", background=self.colors["bg"])
        style.configure("TNotebook.Tab", background=self.colors["panel"],
                        foreground=self.colors["fg"], padding=[10, 5])
        style.configure("TNotebook.Tab:selected", background=self.colors["accent"])
        style.configure("TCheckbutton", background=self.colors["bg"], foreground=self.colors["fg"])
        style.configure("TRadiobutton", background=self.colors["bg"], foreground=self.colors["fg"])
        style.configure("Title.TLabel", font=("Arial", 14, "bold"),
                        foreground=self.colors["accent"])
        style.configure("Subtitle.TLabel", font=("Arial", 10))

    def _create_menu(self):
        """Cria menu principal da aplicação."""
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)
        self._build_menu()

    def _build_menu(self):
        """Reconstroi o menu com o idioma atual."""
        self.menubar.delete(0, tk.END)

        # Menu Arquivo
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t("menu_file"), menu=file_menu)
        file_menu.add_command(label=t("menu_exit"), command=self.root.quit)

        # Menu Idioma
        lang_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t("menu_language"), menu=lang_menu)
        lang_menu.add_command(label=t("menu_portuguese"),
                              command=lambda: self._change_language("pt_BR"))
        lang_menu.add_command(label=t("menu_english"),
                              command=lambda: self._change_language("en_US"))

    def _rebuild_ui(self):
        """
        Reconstrói toda a interface com o idioma atual.
        
        Chamado quando o usuário troca de idioma.
        Preserva valores das variáveis de entrada.
        """
        # Remove frame principal anterior (se existir)
        if hasattr(self, 'main_frame'):
            self.main_frame.destroy()

        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Cria todas as abas
        self._create_knockback_tab()
        self._create_slam_tab()
        self._create_falls_tab()
        self._create_collisions_tab()
        self._create_explosions_tab()
        self._create_falling_objects_tab()
        self._create_combat_tab()

    # ═════════════════════════════════════════════════════════════════
    # KNOCKBACK TAB (p. 378)
    # ═════════════════════════════════════════════════════════════════
    def _create_knockback_tab(self):
        """
        Cria aba de Knockback.
        
        Regra: Basic Set, p. 378
        - Apenas crushing e cutting causam knockback
        - Knockback = floor(dano / (ST-2))
        - Rolagem de equilíbrio: maior entre DX, Acrobatics, Judo
        """
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=t("tab_knockback"))

        ttk.Label(frame, text=t("knockback_title"), style="Title.TLabel").pack(pady=10)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Label(input_frame, text=t("knockback_damage_type")).grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("knockback_crushing"),
                         variable=self.kb_damage_type, value="crushing").grid(row=0, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("knockback_cutting"),
                         variable=self.kb_damage_type, value="cutting").grid(row=0, column=2, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("knockback_basic_damage")).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.kb_basic_damage, width=10).grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("knockback_target_st")).grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.kb_target_st, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("knockback_target_hp")).grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.kb_target_hp, width=10).grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("knockback_dr")).grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.kb_target_dr, width=10).grid(row=4, column=1, sticky=tk.W, pady=5)

        ttk.Checkbutton(input_frame, text=t("knockback_perfect_balance"),
                         variable=self.kb_perfect_balance).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("knockback_skill")).grid(row=6, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.kb_effective_skill, width=10).grid(row=6, column=1, sticky=tk.W, pady=5)

        ttk.Button(input_frame, text=t("knockback_calculate"),
                    command=self._calculate_knockback).grid(row=7, column=0, columnspan=3, pady=10)

        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        ttk.Label(result_frame, text=t("knockback_result"), style="Subtitle.TLabel").pack(anchor=tk.W)
        self.kb_result_text = tk.Text(result_frame, height=8, bg=self.colors["panel"],
                                       fg=self.colors["fg"], font=("Consolas", 10))
        self.kb_result_text.pack(fill=tk.BOTH, expand=True)

        roll_frame = ttk.Frame(result_frame)
        roll_frame.pack(fill=tk.X, pady=10)
        ttk.Label(roll_frame, text=t("knockback_roll_label")).pack(side=tk.LEFT, padx=5)
        ttk.Spinbox(roll_frame, from_=3, to=18,
                     textvariable=self.kb_roll_result, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Button(roll_frame, text=t("knockback_roll_button"),
                    command=self._roll_knockback).pack(side=tk.LEFT, padx=5)
        ttk.Button(roll_frame, text=t("knockback_check_button"),
                    command=self._check_knockback_roll).pack(side=tk.LEFT, padx=5)

    # ═════════════════════════════════════════════════════════════════
    # SLAM TAB (p. 371)
    # ═════════════════════════════════════════════════════════════════
    def _create_slam_tab(self):
        """
        Cria aba de Investida (Slam).
        
        Regra: Basic Set, p. 371
        - Dano = (HP × velocidade) / 100
        - Ambos levam dano
        - Se dano ≥ 2× oponente, oponente cai automaticamente
        """
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=t("tab_slam"))

        ttk.Label(frame, text=t("slam_title"), style="Title.TLabel").pack(pady=10)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=20, pady=10)

        # Atacante
        ttk.Label(input_frame, text=t("slam_attacker"),
                   style="Subtitle.TLabel").grid(row=0, column=0, columnspan=2, pady=5)
        ttk.Label(input_frame, text=t("slam_hp")).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.slam_attacker_hp, width=10).grid(row=1, column=1, sticky=tk.W, pady=5)
        ttk.Label(input_frame, text=t("slam_velocity")).grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.slam_attacker_velocity, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)

        # Defensor
        ttk.Label(input_frame, text=t("slam_defender"),
                   style="Subtitle.TLabel").grid(row=3, column=0, columnspan=2, pady=5)
        ttk.Label(input_frame, text=t("slam_hp")).grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.slam_defender_hp, width=10).grid(row=4, column=1, sticky=tk.W, pady=5)
        ttk.Label(input_frame, text=t("slam_velocity")).grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.slam_defender_velocity, width=10).grid(row=5, column=1, sticky=tk.W, pady=5)

        # Tipo de colisão
        ttk.Label(input_frame, text=t("slam_collision_type")).grid(row=6, column=0, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("slam_head_on"),
                         variable=self.slam_collision_type, value="head_on").grid(row=6, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("slam_rear_end"),
                         variable=self.slam_collision_type, value="rear_end").grid(row=7, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("slam_side_on"),
                         variable=self.slam_collision_type, value="side_on").grid(row=8, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("slam_attacker_damage_bonus")).grid(row=9, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=-100, to=100,
                     textvariable=self.slam_attacker_damage_bonus, width=10).grid(row=9, column=1, sticky=tk.W, pady=5)

        ttk.Button(input_frame, text=t("slam_calculate"),
                    command=self._calculate_slam).grid(row=10, column=0, columnspan=2, pady=10)

        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        ttk.Label(result_frame, text=t("slam_result"), style="Subtitle.TLabel").pack(anchor=tk.W)
        self.slam_result_text = tk.Text(result_frame, height=10, bg=self.colors["panel"],
                                         fg=self.colors["fg"], font=("Consolas", 10))
        self.slam_result_text.pack(fill=tk.BOTH, expand=True)

    # ═════════════════════════════════════════════════════════════════
    # FALLS TAB (p. 430-431)
    # ═════════════════════════════════════════════════════════════════
    def _create_falls_tab(self):
        """
        Cria aba de Quedas.
        
        Regra: Basic Set, p. 430-431
        - Velocidade da tabela de queda
        - Dano = (HP × velocidade) / 100
        - Superfícies duras: 2× HP
        """
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=t("tab_falls"))

        ttk.Label(frame, text=t("falls_title"), style="Title.TLabel").pack(pady=10)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Label(input_frame, text=t("falls_distance")).grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.falls_distance, width=10).grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falls_hp")).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.falls_hp, width=10).grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falls_dr")).grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.falls_dr, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falls_surface_type")).grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("falls_hard"),
                         variable=self.falls_surface, value="hard").grid(row=3, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("falls_soft"),
                         variable=self.falls_surface, value="soft").grid(row=4, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("falls_elastic"),
                         variable=self.falls_surface, value="elastic").grid(row=5, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("falls_water"),
                         variable=self.falls_surface, value="water").grid(row=6, column=1, sticky=tk.W, pady=5)

        ttk.Checkbutton(input_frame, text=t("falls_acrobatics"),
                         variable=self.falls_acrobatics).grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Checkbutton(input_frame, text=t("falls_swimming"),
                         variable=self.falls_swimming).grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Button(input_frame, text=t("falls_calculate"),
                    command=self._calculate_falls).grid(row=9, column=0, columnspan=2, pady=10)

        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        ttk.Label(result_frame, text=t("falls_result"), style="Subtitle.TLabel").pack(anchor=tk.W)
        self.falls_result_text = tk.Text(result_frame, height=10, bg=self.colors["panel"],
                                          fg=self.colors["fg"], font=("Consolas", 10))
        self.falls_result_text.pack(fill=tk.BOTH, expand=True)

    # ═════════════════════════════════════════════════════════════════
    # COLLISIONS TAB (p. 430-431)
    # ═════════════════════════════════════════════════════════════════
    def _create_collisions_tab(self):
        """
        Cria aba de Colisões.
        
        Regra: Basic Set, p. 430-431
        - Dano = (HP × velocidade) / 100
        - Colisão frontal: soma das velocidades
        - Colisão pelas costas: velocidade do mais rápido - mais lento
        """
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=t("tab_collisions"))

        ttk.Label(frame, text=t("collisions_title"), style="Title.TLabel").pack(pady=10)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=20, pady=10)

        # Objeto 1
        ttk.Label(input_frame, text=t("collisions_object1"),
                   style="Subtitle.TLabel").grid(row=0, column=0, columnspan=2, pady=5)
        ttk.Label(input_frame, text=t("collisions_hp")).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.coll_obj1_hp, width=10).grid(row=1, column=1, sticky=tk.W, pady=5)
        ttk.Label(input_frame, text=t("collisions_velocity")).grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.coll_obj1_velocity, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)

        # Objeto 2
        ttk.Label(input_frame, text=t("collisions_object2"),
                   style="Subtitle.TLabel").grid(row=0, column=2, columnspan=2, pady=5, padx=(30, 0))
        ttk.Label(input_frame, text=t("collisions_hp")).grid(row=1, column=2, sticky=tk.W, pady=5, padx=(30, 0))
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.coll_obj2_hp, width=10).grid(row=1, column=3, sticky=tk.W, pady=5)
        ttk.Label(input_frame, text=t("collisions_velocity")).grid(row=2, column=2, sticky=tk.W, pady=5, padx=(30, 0))
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.coll_obj2_velocity, width=10).grid(row=2, column=3, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("collisions_dr")).grid(row=3, column=2, sticky=tk.W, pady=5, padx=(30, 0))
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.coll_obj2_dr, width=10).grid(row=3, column=3, sticky=tk.W, pady=5)

        # Tipo de colisão
        ttk.Label(input_frame, text=t("collisions_type")).grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("collisions_head_on"),
                         variable=self.coll_type, value="head_on").grid(row=4, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("collisions_rear_end"),
                         variable=self.coll_type, value="rear_end").grid(row=4, column=2, sticky=tk.W, pady=5, padx=(30, 0))
        ttk.Radiobutton(input_frame, text=t("collisions_side_on"),
                         variable=self.coll_type, value="side_on").grid(row=4, column=3, sticky=tk.W, pady=5)

        # Tipo de superfície
        ttk.Label(input_frame, text=t("collisions_surface")).grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("collisions_surface_normal"),
                         variable=self.coll_surface, value="normal").grid(row=5, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(input_frame, text=t("collisions_surface_hard"),
                         variable=self.coll_surface, value="hard").grid(row=5, column=2, sticky=tk.W, pady=5, padx=(30, 0))
        ttk.Radiobutton(input_frame, text=t("collisions_surface_elastic"),
                         variable=self.coll_surface, value="elastic").grid(row=5, column=3, sticky=tk.W, pady=5)

        # Objeto imóvel
        ttk.Checkbutton(input_frame, text=t("collisions_immovable"),
                         variable=self.coll_immovable).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Checkbutton(input_frame, text=t("collisions_breakable"),
                         variable=self.coll_breakable).grid(row=6, column=2, columnspan=2, sticky=tk.W, pady=5, padx=(30, 0))

        ttk.Button(input_frame, text=t("collisions_calculate"),
                    command=self._calculate_collisions).grid(row=7, column=0, columnspan=4, pady=10)

        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        ttk.Label(result_frame, text=t("collisions_result"), style="Subtitle.TLabel").pack(anchor=tk.W)
        self.coll_result_text = tk.Text(result_frame, height=10, bg=self.colors["panel"],
                                         fg=self.colors["fg"], font=("Consolas", 10))
        self.coll_result_text.pack(fill=tk.BOTH, expand=True)

    # ═════════════════════════════════════════════════════════════════
    # EXPLOSIONS TAB (p. 414-415)
    # ═════════════════════════════════════════════════════════════════
    def _create_explosions_tab(self):
        """
        Cria aba de Explosões.
        
        Regra: Basic Set, p. 414-415
        - Raio = dados de dano × 2
        - Dano colateral = dano / (3 × distância)
        - Fragmentação: raio = dados × 5
        """
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=t("tab_explosions"))

        ttk.Label(frame, text=t("explosions_title"), style="Title.TLabel").pack(pady=10)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Label(input_frame, text=t("explosions_basic_damage")).grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.exp_basic_damage, width=10).grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("explosions_fragmentation")).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.exp_fragmentation, width=10).grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("explosions_distance")).grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.exp_distance, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("explosions_dr")).grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=0, to=10000,
                     textvariable=self.exp_dr, width=10).grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Checkbutton(input_frame, text=t("explosions_direct_hit"),
                         variable=self.exp_direct_hit).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("explosions_target_sm")).grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=-100, to=100,
                     textvariable=self.exp_target_sm, width=10).grid(row=5, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("explosions_posture_modifier")).grid(row=6, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=-10, to=10,
                     textvariable=self.exp_posture_modifier, width=10).grid(row=6, column=1, sticky=tk.W, pady=5)

        ttk.Button(input_frame, text=t("explosions_calculate"),
                    command=self._calculate_explosions).grid(row=7, column=0, columnspan=2, pady=10)

        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        ttk.Label(result_frame, text=t("explosions_result"), style="Subtitle.TLabel").pack(anchor=tk.W)
        self.exp_result_text = tk.Text(result_frame, height=10, bg=self.colors["panel"],
                                        fg=self.colors["fg"], font=("Consolas", 10))
        self.exp_result_text.pack(fill=tk.BOTH, expand=True)

    # ═════════════════════════════════════════════════════════════════
    # FALLING OBJECTS TAB (p. 431)
    # ═════════════════════════════════════════════════════════════════
    def _create_falling_objects_tab(self):
        """
        Cria aba de Queda de Objetos.
        
        Regra: Basic Set, p. 431
        - Mesma tabela de velocidade de queda
        - Dano = (HP × velocidade) / 100
        - SM do objeto afeta penalidades
        """
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=t("tab_falling_objects"))

        ttk.Label(frame, text=t("falling_objects_title"), style="Title.TLabel").pack(pady=10)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Label(input_frame, text=t("falling_objects_distance")).grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.fo_distance, width=10).grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falling_objects_object_hp")).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.fo_object_hp, width=10).grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falling_objects_target_hp")).grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.fo_target_hp, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falling_objects_target_sm")).grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=-100, to=100,
                     textvariable=self.fo_target_sm, width=10).grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falling_objects_object_sm")).grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=-100, to=100,
                     textvariable=self.fo_object_sm, width=10).grid(row=4, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falling_objects_dropping_skill")).grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=100,
                     textvariable=self.fo_dropping_skill, width=10).grid(row=5, column=1, sticky=tk.W, pady=5)

        ttk.Checkbutton(input_frame, text=t("falling_objects_target_aware"),
                         variable=self.fo_target_aware).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text=t("falling_objects_target_dodge")).grid(row=7, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=100,
                     textvariable=self.fo_target_dodge, width=10).grid(row=7, column=1, sticky=tk.W, pady=5)

        ttk.Checkbutton(input_frame, text=t("falling_objects_aimed"),
                         variable=self.fo_aimed).grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Button(input_frame, text=t("falling_objects_calculate"),
                    command=self._calculate_falling_objects).grid(row=9, column=0, columnspan=2, pady=10)

        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        ttk.Label(result_frame, text=t("falling_objects_result"), style="Subtitle.TLabel").pack(anchor=tk.W)
        self.fo_result_text = tk.Text(result_frame, height=10, bg=self.colors["panel"],
                                       fg=self.colors["fg"], font=("Consolas", 10))
        self.fo_result_text.pack(fill=tk.BOTH, expand=True)

    # ═════════════════════════════════════════════════════════════════
    # COMBAT TAB (p. 368-376)
    # ═════════════════════════════════════════════════════════════════
    def _create_combat_tab(self):
        """
        Cria aba de Cálculos de Combate.
        
        Regra: Basic Set, p. 368-376
        
        Três campos de entrada separados:
        1. Attack Skill: Habilidade de ataque (ex: Sword-15, Bow-14)
           Usada para rolar ataque. NÃO é o mesmo que ST.
        
        2. Effective Defense: Defesa efetiva (Dodge, Parry ou Block)
           Usada para rolar defesa.
        
        3. ST (Strength): Força do personagem
           Usada para determinar dano (thrust/swing) via Damage Table.
           Referência: p. 16 (Damage Table)
        """
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=t("tab_combat"))

        ttk.Label(frame, text=t("combat_title"), style="Title.TLabel").pack(pady=10)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=20, pady=10)

        # Attack Skill - Habilidade de Ataque (p. 368)
        ttk.Label(input_frame, text=t("combat_attack_skill")).grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.combat_attack_skill, width=10).grid(row=0, column=1, sticky=tk.W, pady=5)

        # Effective Defense - Defesa Efetiva (p. 374)
        ttk.Label(input_frame, text=t("combat_defense")).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.combat_defense, width=10).grid(row=1, column=1, sticky=tk.W, pady=5)

        # ST - Força (p. 16, Damage Table)
        ttk.Label(input_frame, text=t("combat_st")).grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(input_frame, from_=1, to=10000,
                     textvariable=self.combat_st, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)

        # Botões de ação
        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text=t("combat_roll_attack"),
                    command=self._roll_combat_attack).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text=t("combat_roll_defense"),
                    command=self._roll_combat_defense).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text=t("combat_roll_damage"),
                    command=self._roll_combat_damage).pack(side=tk.LEFT, padx=5)

        # Área de resultado
        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        ttk.Label(result_frame, text=t("combat_result"), style="Subtitle.TLabel").pack(anchor=tk.W)
        self.combat_result_text = tk.Text(result_frame, height=10, bg=self.colors["panel"],
                                           fg=self.colors["fg"], font=("Consolas", 10))
        self.combat_result_text.pack(fill=tk.BOTH, expand=True)

    # ═════════════════════════════════════════════════════════════════
    # MÉTODOS DE CONVERSÃO DE UNIDADES
    # ═════════════════════════════════════════════════════════════════
    def _meters_to_yards(self, meters: float) -> int:
        """
        Converte metros para jardas (arredonda para inteiro).
        
        GURPS usa jardas internamente, mas a interface usa metros.
        Arredondamento: GURPS arredonda para o inteiro mais próximo.
        """
        return round(meters * METERS_TO_YARDS)

    def _yards_to_meters(self, yards: int) -> float:
        """Converte jardas para metros (1 casa decimal)."""
        return round(yards * YARDS_TO_METERS, 1)

    def _format_meters(self, yards: int) -> str:
        """Formata jardas como metros para exibição."""
        meters = self._yards_to_meters(yards)
        return f"{meters}m"

    def _get_int_var(self, var: tk.IntVar, min_val: int = 0, max_val: int = 10000) -> int:
        """Obtém valor inteiro de IntVar com validação."""
        val = var.get()
        if val < min_val:
            return min_val
        if val > max_val:
            return max_val
        return val

    # ═════════════════════════════════════════════════════════════════
    # MÉTODOS DE CÁLCULO
    # ═════════════════════════════════════════════════════════════════

    # ─── Knockback ───────────────────────────────────────────────
    def _calculate_knockback(self):
        """Calcula knockback baseado nos inputs do usuário."""
        try:
            result = self.knockback_calc.calculate_knockback(
                damage_type=self.kb_damage_type.get(),
                basic_damage=self.kb_basic_damage.get(),
                target_st=self.kb_target_st.get(),
                target_hp=self.kb_target_hp.get(),
                target_dr=self.kb_target_dr.get(),
                perfect_balance=self.kb_perfect_balance.get()
            )

            self.kb_result_text.delete(1.0, tk.END)
            if not result["valid"]:
                self.kb_result_text.insert(tk.END, t("knockback_invalid"))
            elif result["yards_back"] == 0:
                self.kb_result_text.insert(tk.END, t("knockback_none"))
            else:
                self.kb_result_text.insert(tk.END, t(
                    "knockback_summary",
                    yards=result["yards_back"],
                    meters=self._format_meters(result["yards_back"]),
                ))

            if result["yards_back"] > 0:
                self.kb_result_text.insert(tk.END, f"\n\n{t('knockback_details')}")
                self.kb_result_text.insert(tk.END,
                    f"\n{t('knockback_damage_value', value=result['knockback_damage'])}")
                self.kb_result_text.insert(tk.END,
                    f"\n{t('knockback_meters_back', value=self._format_meters(result['yards_back']))}")
                self.kb_result_text.insert(tk.END,
                    f"\n{t('knockback_roll_modifier', value=result['roll_modifier'])}")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    def _roll_knockback(self):
        """Rola 3d6 para verificação de knockback."""
        roll, rolls = roll_3d6()
        self.kb_roll_result.set(roll)

    def _check_knockback_roll(self):
        """Verifica se o alvo resiste ao knockback."""
        try:
            kb_result = self.knockback_calc.calculate_knockback(
                damage_type=self.kb_damage_type.get(),
                basic_damage=self.kb_basic_damage.get(),
                target_st=self.kb_target_st.get(),
                target_hp=self.kb_target_hp.get(),
                target_dr=self.kb_target_dr.get(),
                perfect_balance=self.kb_perfect_balance.get()
            )

            if kb_result["yards_back"] == 0:
                self.kb_result_text.delete(1.0, tk.END)
                self.kb_result_text.insert(tk.END, t("knockback_none"))
                return

            roll_result = self.kb_roll_result.get()
            roll_check = self.knockback_calc.calculate_knockback_roll(
                yards_back=kb_result["yards_back"],
                effective_skill=self.kb_effective_skill.get(),
                roll_result=roll_result,
                perfect_balance=self.kb_perfect_balance.get()
            )

            self.kb_result_text.delete(1.0, tk.END)
            self.kb_result_text.insert(tk.END, t(
                "knockback_summary",
                yards=kb_result["yards_back"],
                meters=self._format_meters(kb_result["yards_back"]),
            ))
            self.kb_result_text.insert(tk.END,
                f"\n\n{t('knockback_verification')}")
            self.kb_result_text.insert(tk.END,
                f"\n{t('knockback_roll_result', value=roll_result)}")
            self.kb_result_text.insert(tk.END,
                f"\n{t('knockback_effective_skill', value=roll_check['effective_skill'])}")
            roll_message = t(
                "roll_success" if roll_check["success"] else "roll_failure",
                margin=roll_check["margin"],
            )
            self.kb_result_text.insert(tk.END,
                f"\n{t('combat_result_label', value=roll_message)}")

            if roll_check["fall_down"]:
                self.kb_result_text.insert(tk.END,
                    f"\n\n{t('knockback_fall_warning')}")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Slam/Investida ──────────────────────────────────────────
    def _calculate_slam(self):
        """Calcula dano de investida (slam)."""
        try:
            # Converter m/s para jardas/seg (cálculos usam jardas)
            att_vel_yd = self._meters_to_yards(self.slam_attacker_velocity.get())
            def_vel_yd = self._meters_to_yards(self.slam_defender_velocity.get())

            result = self.slam_calc.calculate_slam(
                attacker_hp=self.slam_attacker_hp.get(),
                attacker_velocity=att_vel_yd,
                defender_hp=self.slam_defender_hp.get(),
                defender_velocity=def_vel_yd,
                collision_type=self.slam_collision_type.get(),
                attacker_skill_bonus=self.slam_attacker_damage_bonus.get(),
            )

            self.slam_result_text.delete(1.0, tk.END)
            # Converter resultado de volta para metros
            collision_vel_m = round(result["collision_velocity"] * YARDS_TO_METERS, 1)
            self.slam_result_text.insert(tk.END,
                f"{t('result_collision_velocity', value=collision_vel_m)}\n")
            self.slam_result_text.insert(tk.END,
                f"{t('slam_attacker_damage', expression=result['attacker_damage_dice'], value=result['attacker_damage_total'])}\n")
            self.slam_result_text.insert(tk.END,
                f"{t('slam_defender_damage', expression=result['defender_damage_dice'], value=result['defender_damage_total'])}\n")
            self.slam_result_text.insert(
                tk.END, f"\n{t('slam_' + result['outcome'])}\n"
            )

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Quedas ──────────────────────────────────────────────────
    def _calculate_falls(self):
        """Calcula dano por queda."""
        try:
            # Converter metros para jardas
            distance_yards = self._meters_to_yards(self.falls_distance.get())

            result = self.falls_calc.calculate_fall(
                distance_yards=distance_yards,
                target_hp=self.falls_hp.get(),
                surface_type=self.falls_surface.get(),
                acrobatics_success=self.falls_acrobatics.get(),
                swimming_success=self.falls_swimming.get(),
                armor_dr=self.falls_dr.get(),
            )

            self.falls_result_text.delete(1.0, tk.END)
            velocity_m = round(result["velocity"] * YARDS_TO_METERS, 1)
            self.falls_result_text.insert(tk.END,
                f"{t('result_distance', meters=self.falls_distance.get(), yards=distance_yards)}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_impact_velocity', mps=velocity_m, yps=result['velocity'])}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_basic_damage', expression=result['damage_dice'], value=result['damage_total'])}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_penetrating_damage', value=result['penetrating_damage'])}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_blunt_trauma', value=result['blunt_trauma'])}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_total_injury', value=result['total_injury'])}\n")
            if result["surface_type"] == "water":
                self.falls_result_text.insert(tk.END,
                    f"{t('falls_swimming_modifier', value=result['swimming_modifier'])}\n")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Colisões ────────────────────────────────────────────────
    def _calculate_collisions(self):
        """Calcula dano de colisão entre objetos."""
        try:
            # Converter m/s para jardas/seg
            vel1_yd = self._meters_to_yards(self.coll_obj1_velocity.get())
            vel2_yd = self._meters_to_yards(self.coll_obj2_velocity.get())

            result = self.collisions_calc.calculate_collision(
                object1_hp=self.coll_obj1_hp.get(),
                object1_velocity=vel1_yd,
                object2_hp=self.coll_obj2_hp.get(),
                object2_velocity=vel2_yd,
                collision_type=self.coll_type.get(),
                surface_type=self.coll_surface.get(),
                immovable_object=self.coll_immovable.get(),
                object2_dr=self.coll_obj2_dr.get(),
                obstacle_breakable=self.coll_breakable.get(),
            )

            self.coll_result_text.delete(1.0, tk.END)
            collision_vel_m = round(result["collision_velocity"] * YARDS_TO_METERS, 1)
            self.coll_result_text.insert(tk.END,
                f"{t('result_collision_velocity', value=collision_vel_m)}\n")
            self.coll_result_text.insert(tk.END,
                f"{t('collisions_object1_damage', expression=result['object1_damage_dice'], value=result['object1_damage_total'])}\n")
            self.coll_result_text.insert(tk.END,
                f"{t('collisions_object2_damage', expression=result['object2_damage_dice'], value=result['object2_damage_total'])}\n")
            if result["damage_cap"] is not None:
                self.coll_result_text.insert(tk.END,
                    f"{t('collisions_damage_cap', value=result['damage_cap'])}\n")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Explosões ───────────────────────────────────────────────
    def _calculate_explosions(self):
        """Calcula dano de explosão."""
        try:
            # Converter metros para jardas
            distance_yards = self._meters_to_yards(self.exp_distance.get())

            result = self.explosions_calc.calculate_explosion(
                basic_damage_dice=self.exp_basic_damage.get(),
                fragmentation_dice=self.exp_fragmentation.get(),
                distance_yards=distance_yards,
                target_dr=self.exp_dr.get(),
                direct_hit=self.exp_direct_hit.get(),
                target_sm=self.exp_target_sm.get(),
                posture_modifier=self.exp_posture_modifier.get(),
            )

            self.exp_result_text.delete(1.0, tk.END)
            blast_radius_m = round(result["blast_radius"] * YARDS_TO_METERS, 1)
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_blast_radius', meters=blast_radius_m, yards=result['blast_radius'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_blast_damage', expression=result['collateral_damage_dice'], value=result['collateral_damage_total'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_blast_injury', value=result['blast_injury'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_fragment_hits', value=result['fragment_hits'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_fragment_injury', value=result['fragment_injury_total'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('result_total_injury', value=result['injury'])}\n")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Queda de Objetos ────────────────────────────────────────
    def _calculate_falling_objects(self):
        """Calcula dano por objeto caindo."""
        try:
            # Converter metros para jardas
            distance_yards = self._meters_to_yards(self.fo_distance.get())

            result = self.falling_objects_calc.calculate_falling_object(
                distance_yards=distance_yards,
                object_hp=self.fo_object_hp.get(),
                target_hp=self.fo_target_hp.get(),
                target_sm=self.fo_target_sm.get(),
                object_sm=self.fo_object_sm.get(),
                target_aware=self.fo_target_aware.get(),
                dropping_skill=self.fo_dropping_skill.get(),
                target_dodge=self.fo_target_dodge.get(),
                aimed=self.fo_aimed.get(),
            )

            self.fo_result_text.delete(1.0, tk.END)
            velocity_m = round(result["velocity"] * YARDS_TO_METERS, 1)
            self.fo_result_text.insert(tk.END,
                f"{t('result_distance', meters=self.fo_distance.get(), yards=distance_yards)}\n")
            self.fo_result_text.insert(tk.END,
                f"{t('result_impact_velocity', mps=velocity_m, yps=result['velocity'])}\n")
            self.fo_result_text.insert(tk.END,
                f"{t('falling_objects_attack_roll', roll=result['attack_roll'], skill=result['effective_skill'])}\n")
            if result["target_can_dodge"]:
                self.fo_result_text.insert(tk.END,
                    f"{t('falling_objects_dodge_roll', roll=result['dodge_roll'], defense=result['target_dodge'])}\n")
            self.fo_result_text.insert(tk.END,
                f"{t('falling_objects_outcome_' + result['outcome'])}\n")
            self.fo_result_text.insert(tk.END,
                f"{t('result_basic_damage', expression=result['damage_dice'], value=result['damage_total'])}\n")
            if result["move_penalty"] > 0:
                self.fo_result_text.insert(tk.END,
                    f"{t('falling_objects_move_limit')}\n")
            if result["defense_penalty"] > 0:
                self.fo_result_text.insert(tk.END,
                    f"{t('falling_objects_defense_penalty', value=result['defense_penalty'])}\n")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Combate ─────────────────────────────────────────────────
    def _roll_combat_attack(self):
        """
        Rola ataque usando Attack Skill (não ST).
        
        Attack Skill é a habilidade para acertar (ex: Sword-15).
        ST é separado e usado apenas para dano.
        """
        try:
            result = self.combat_calc.calculate_attack_roll(
                effective_skill=self.combat_attack_skill.get()
            )
            self.combat_result_text.delete(1.0, tk.END)
            self.combat_result_text.insert(tk.END,
                f"{t('combat_attack_header')}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_skill_label', value=result['effective_skill'])}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_roll_label', value=result['roll_result'])}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_result_label', value=t('combat_outcome_' + result['outcome'], margin=result['margin']))}\n")
        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    def _roll_combat_defense(self):
        """Rola defesa usando Effective Defense."""
        try:
            result = self.combat_calc.calculate_defense_roll(
                effective_defense=self.combat_defense.get()
            )
            self.combat_result_text.delete(1.0, tk.END)
            self.combat_result_text.insert(tk.END,
                f"{t('combat_defense_header')}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_defense_label', value=result['effective_defense'])}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_roll_label', value=result['roll_result'])}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_result_label', value=t('combat_outcome_' + result['outcome'], margin=result['margin']))}\n")
        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    def _roll_combat_damage(self):
        """
        Rola dano usando ST (Força), NÃO Attack Skill.
        
        ST determina thrust/swing via Damage Table (p. 16).
        Attack Skill é apenas para acertar.
        """
        try:
            # Usa o campo ST separado para dano
            st = self.combat_st.get()
            entry = self.combat_calc.get_damage_table_entry(st)
            from utils.dice_roller import roll_dice
            thrust_result, _ = roll_dice(entry["thrust"])
            swing_result, _ = roll_dice(entry["swing"])

            self.combat_result_text.delete(1.0, tk.END)
            self.combat_result_text.insert(tk.END,
                f"{t('combat_damage_header', st=st)}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_thrust_damage', expression=entry['thrust'], value=thrust_result)}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_swing_damage', expression=entry['swing'], value=swing_result)}\n")
        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ═════════════════════════════════════════════════════════════════
    # IDIOMA
    # ═════════════════════════════════════════════════════════════════
    def _change_language(self, language: str):
        """
        Muda idioma e reconstrói toda a interface.
        
        Todos os textos são traduzidos via sistema i18n.
        """
        self.i18n.set_language(language)
        self._rebuild_ui()
        self._build_menu()
        self._update_title()

    def _update_title(self):
        """Atualiza título da janela."""
        self.root.title(t("app_title"))

    def run(self):
        """Inicia o loop principal da aplicação."""
        self.root.mainloop()


def main():
    """Função principal - ponto de entrada da aplicação."""
    app = GURPSCalculator()
    app.run()


if __name__ == "__main__":
    main()
