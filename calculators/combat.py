"""
Calculadora de Combate - GURPS 4e

Este módulo implementa os cálculos de combate do GURPS 4th Edition,
conforme descrito no Basic Set Revised.

Regras de referência (Basic Set):
- Ataque: p. 368-370 (Attack Roll, Melee Attacks, Ranged Attacks)
- Defesa: p. 374-376 (Dodge, Parry, Block)
- Dano: p. 16 (Damage Table), p. 377-379 (Damage and Injury)
- Habilidades: p. 170-228 (Skills)

Conceitos importantes:
- Attack Skill (Habilidade de Ataque): A habilidade usada para acertar
  (ex: Sword-15, Bow-14). NÃO é o mesmo que ST.
- ST (Strength): Força do personagem, que determina o dano (thrust/swing).
- Effective Defense: Defesa efetiva (Dodge, Parry ou Block).

Referências de páginas do Basic Set Revised:
- Damage Table (Tabela de Dano): p. 16
- Knockback: p. 378
- Critical Hits: p. 381
- Active Defenses: p. 374-376
"""
from typing import Dict, Any, Tuple
from utils.dice_roller import evaluate_success_roll, roll_3d6, get_damage_dice
import math


class CombatCalculator:
    """
    Calculadora de Combate do GURPS 4e.
    
    Fornece métodos para:
    - Rolar ataques e defesas
    - Consultar tabela de dano por ST
    - Calcular modificadores de ferimento
    - Calcular defesas (Dodge, Parry, Block)
    
    Referência: Basic Set Revised, Capítulo 9 (Combat)
    """
    
    def __init__(self):
        """Inicializa a calculadora e constrói a tabela de dano."""
        self.damage_table = self._build_damage_table()
    
    def _build_damage_table(self) -> Dict[int, Tuple[str, str]]:
        """
        Constrói tabela de dano por ST (Força).
        
        Baseado na Damage Table do Basic Set Revised, p. 16.
        Cada entrada retorna (thrust_damage, swing_damage).
        
        Para ST acima de 100, acrescenta 1d a thrust e swing por
        10 pontos completos de ST, conforme a regra da p. 15.
        
        Returns:
            Dict mapeando ST para (thrust, swing)
        """
        table = {}
        for st in range(1, 101):
            table[st] = get_damage_dice(st)
        return table
    
    def calculate_attack_roll(
        self,
        effective_skill: int,
        roll_result: int = None
    ) -> Dict[str, Any]:
        """
        Calcula rolagem de ataque.
        
        Regra do Basic Set, p. 368:
        - Rola 3d6 contra a habilidade efetiva
        - ≤ habilidade = sucesso
        - 3 ou 4 = sempre sucesso (acerto crítico)
        - 17 ou 18 = sempre falha (erro crítico)
        
        Args:
            effective_skill: Habilidade efetiva de ataque (base + modificadores)
            roll_result: Resultado da rolagem (None para rolar automaticamente)
            
        Returns:
            Dict com resultado do ataque, incluindo:
            - success: True se acertou
            - critical_hit: True se acerto crítico
            - critical_miss: True se erro crítico
            - margin: Margem de sucesso/falha
            - message: Mensagem descritiva
        """
        if roll_result is None:
            roll_result, rolls = roll_3d6()
        else:
            rolls = None
        
        result = {
            "effective_skill": effective_skill,
            "roll_result": roll_result,
            "rolls": rolls,
            "success": False,
            "critical_hit": False,
            "critical_miss": False,
            "margin": 0,
            "message": ""
        }
        
        outcome = evaluate_success_roll(effective_skill, roll_result)
        result["success"] = outcome["success"]
        result["critical_hit"] = outcome["critical_success"]
        result["critical_miss"] = outcome["critical_failure"]
        result["margin"] = outcome["margin"]
        result["outcome"] = (
            "critical_hit" if outcome["critical_success"] else
            "critical_miss" if outcome["critical_failure"] else
            "hit" if outcome["success"] else "miss"
        )
        result["message"] = result["outcome"]
        
        return result
    
    def calculate_defense_roll(
        self,
        effective_defense: int,
        roll_result: int = None
    ) -> Dict[str, Any]:
        """
        Calcula rolagem de defesa ativa.
        
        Regra do Basic Set, p. 374:
        - Rola 3d6 contra a defesa efetiva
        - ≤ defesa = sucesso
        - 3 ou 4 = sempre sucesso (sucesso crítico)
        - 17 ou 18 = sempre falha (falha crítica)
        
        Args:
            effective_defense: Defesa efetiva (Dodge, Parry ou Block)
            roll_result: Resultado da rolagem (None para rolar)
            
        Returns:
            Dict com resultado da defesa
        """
        if roll_result is None:
            roll_result, rolls = roll_3d6()
        else:
            rolls = None
        
        result = {
            "effective_defense": effective_defense,
            "roll_result": roll_result,
            "rolls": rolls,
            "success": False,
            "critical_success": False,
            "critical_fail": False,
            "margin": 0,
            "message": ""
        }
        
        outcome = evaluate_success_roll(effective_defense, roll_result)
        result["success"] = outcome["success"]
        result["critical_success"] = outcome["critical_success"]
        result["critical_fail"] = outcome["critical_failure"]
        result["margin"] = outcome["margin"]
        result["outcome"] = (
            "critical_defense" if outcome["critical_success"] else
            "critical_defense_failure" if outcome["critical_failure"] else
            "defended" if outcome["success"] else "defense_failed"
        )
        result["message"] = result["outcome"]
        
        return result
    
    def calculate_dodge(
        self,
        basic_speed: float,
        encumbrance: int = 0,
        shield_db: int = 0
    ) -> Dict[str, Any]:
        """
        Calcula defesa Esquiva (Dodge).
        
        Regra do Basic Set, p. 374:
        - Dodge = Basic Speed + 3 (arredondado para baixo)
        - Modificado por Encumbrance e Defense Bonus de escudo
        
        Args:
            basic_speed: Velocidade básica do personagem
            encumbrance: Nível de Encumbrance (0-4)
            shield_db: Defense Bonus do escudo
            
        Returns:
            Dict com valor do Dodge
        """
        # Dodge = Basic Speed + 3, arredondado para baixo (p. 374)
        dodge = int(basic_speed) + 3
        
        # Penalidade de Encumbrance (p. 17)
        dodge -= encumbrance
        
        # Bônus de escudo (p. 375)
        dodge += shield_db
        
        return {
            "basic_speed": basic_speed,
            "encumbrance": encumbrance,
            "shield_db": shield_db,
            "dodge": dodge,
            "message": f"Esquiva: {dodge}"
        }
    
    def calculate_block(
        self,
        shield_skill: int,
        shield_db: int = 1
    ) -> Dict[str, Any]:
        """
        Calcula defesa Bloqueio (Block).
        
        Regra do Basic Set, p. 375:
        - Block = 3 + Shield/2 (arredondado para baixo)
        
        Args:
            shield_skill: Habilidade com Escudo
            shield_db: Defense Bonus do escudo
            
        Returns:
            Dict com valor do Block
        """
        # Block = 3 + Shield/2, arredondado para baixo (p. 375)
        block = 3 + (shield_skill // 2) + shield_db
        
        return {
            "shield_skill": shield_skill,
            "shield_db": shield_db,
            "block": block,
            "message": f"Bloqueio: {block}"
        }
    
    def calculate_parry(
        self,
        weapon_skill: int,
        weapon_parry: int = 0,
        is_fencing: bool = False,
        retreat: bool = False,
        shield_db: int = 0,
    ) -> Dict[str, Any]:
        """
        Calcula defesa Parry.
        
        Regra do Basic Set, p. 376:
        - Parry = Weapon Skill/2 + 3 (arredondado para baixo)
        - Armas de esgrima: +3 ao Parry quando recua
        
        Args:
            weapon_skill: Habilidade com a arma
            weapon_parry: Parry específico da arma (0 para usar cálculo padrão)
            is_fencing: É arma de esgrima?
            
        Returns:
            Dict com valor do Parry
        """
        # Parry padrão = Weapon Skill/2 + 3 (p. 376)
        parry = (weapon_skill // 2) + 3 + weapon_parry + shield_db
        if retreat:
            parry += 3 if is_fencing else 1
        
        return {
            "weapon_skill": weapon_skill,
            "weapon_parry": weapon_parry,
            "is_fencing": is_fencing,
            "retreat": retreat,
            "shield_db": shield_db,
            "parry": parry,
            "message": f"Parry: {parry}"
        }
    
    def get_damage_table_entry(self, st: int) -> Dict[str, str]:
        """
        Retorna entrada da tabela de dano para um ST (Força).
        
        A tabela de dano (Basic Set, p. 16) converte ST em dados
        de dano para thrust (empurrão) e swing (balanço).
        
        Args:
            st: Força do personagem (1-10000)
            
        Returns:
            Dict com st, thrust e swing
        """
        thrust, swing = get_damage_dice(st)
        return {
            "st": st,
            "thrust": thrust,
            "swing": swing
        }
    
    def calculate_wounding_modifier(
        self,
        damage_type: str
    ) -> float:
        """
        Retorna modificador de ferimento (wounding modifier) para tipo de dano.
        
        Referência: Basic Set, p. 379 (Wounding Modifiers)
        
        - pi- (small piercing): ×0.5
        - burn, cor, cr, fat, pi, tox: ×1
        - cut, pi+ (large piercing): ×1.5
        - imp, pi++ (huge piercing): ×2
        
        Args:
            damage_type: Tipo de dano (chave do dicionário)
            
        Returns:
            Modificador de ferimento (float)
        """
        modifiers = {
            "small_piercing": 0.5,  # pi- (p. 379)
            "burning": 1.0,         # burn
            "corrosion": 1.0,       # cor
            "crushing": 1.0,        # cr
            "fatigue": 1.0,         # fat
            "piercing": 1.0,        # pi
            "toxic": 1.0,           # tox
            "cutting": 1.5,         # cut (p. 379)
            "large_piercing": 1.5,  # pi+ (p. 379)
            "impaling": 2.0,        # imp (p. 379)
            "huge_piercing": 2.0    # pi++ (p. 379)
        }
        
        return modifiers.get(damage_type, 1.0)
    
    def calculate_injury(
        self,
        penetrating_damage: int,
        damage_type: str
    ) -> int:
        """
        Calcula lesão (injury) baseado no dano penetrante.
        
        Referência: Basic Set, p. 379
        Lesão = dano penetrante × modificador de ferimento
        
        Args:
            penetrating_damage: Dano que penetrou a armadura (após DR)
            damage_type: Tipo de dano
            
        Returns:
            Lesão em HP (inteiro)
        """
        wounding_mod = self.calculate_wounding_modifier(damage_type)
        if penetrating_damage <= 0:
            return 0
        return max(1, math.floor(penetrating_damage * wounding_mod))
