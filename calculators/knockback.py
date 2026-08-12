"""
Calculadora de Knockback - GURPS 4e

Regras do Basic Set Revised (p. 378):
- Apenas ataques crushing e cutting causam knockback
- Crushing causa knockback independente de penetrar DR
- Cutting causa knockback apenas se NÃO penetrar DR
- Knockback baseado no dano básico antes de subtrair DR
- Por cada múltiplo completo de ST-2 do alvo, move 1 jarda
- Se ST ≤ 3, knockback é 1 jarda por ponto de dano
- Se não tem ST, usar HP
- Rolagem: maior entre DX, Acrobatics ou Judo
- Penalidade: -1 por jarda após a primeira
- Equilíbrio Perfeito: +4 na rolagem
"""
from typing import Dict, Any


class KnockbackCalculator:
    """Calculadora de Knockback do GURPS 4e."""
    
    def calculate_knockback(
        self,
        damage_type: str,
        basic_damage: int,
        target_st: int,
        target_dr: int = 0,
        target_hp: int = None,
        perfect_balance: bool = False
    ) -> Dict[str, Any]:
        """
        Calcula knockback e resultado.
        
        Args:
            damage_type: "crushing" ou "cutting"
            basic_damage: Dano básico rolado
            target_st: ST do alvo
            target_dr: DR do alvo
            target_hp: HP do alvo (usado se ST ≤ 3 ou sem ST)
            perfect_balance: Tem Equilíbrio Perfeito?
            
        Returns:
            Dict com resultados do knockback
        """
        result = {
            "damage_type": damage_type,
            "basic_damage": basic_damage,
            "target_st": target_st,
            "target_dr": target_dr,
            "knockback_damage": 0,
            "penetrating_damage": 0,
            "yards_back": 0,
            "knockback_roll_needed": 0,
            "roll_modifier": 0,
            "fall_down": False,
            "collision": False,
            "valid": True,
            "message": ""
        }
        
        # Verifica tipo de dano válido
        if damage_type not in ["crushing", "cutting"]:
            result["valid"] = False
            result["message"] = "Tipo de dano inválido. Use 'crushing' ou 'cutting'."
            return result
        
        # Calcula dano penetrante
        penetrating = max(0, basic_damage - target_dr)
        result["penetrating_damage"] = penetrating
        
        # Determina se causa knockback
        causes_knockback = False
        knockback_damage = 0
        
        if damage_type == "crushing":
            # Crushing sempre causa knockback (baseado no dano básico)
            causes_knockback = True
            knockback_damage = basic_damage
        elif damage_type == "cutting":
            # Cutting causa knockback apenas se NÃO penetrar DR
            if penetrating == 0 and basic_damage > 0:
                causes_knockback = True
                knockback_damage = basic_damage
        
        result["knockback_damage"] = knockback_damage
        
        if not causes_knockback:
            result["yards_back"] = 0
            result["message"] = "Sem knockback."
            return result
        
        # Calcula quantas jardas para trás
        # Usar HP se ST ≤ 3 ou se target_hp é fornecido e ST ≤ 3
        effective_st = target_st
        if target_st <= 3 and target_hp is not None:
            effective_st = target_hp
        
        if effective_st <= 3:
            # ST 3 ou menos: 1 jarda por ponto de dano
            yards_back = knockback_damage
        else:
            # Knockback = floor(basic_damage / (ST - 2))
            divisor = effective_st - 2
            yards_back = knockback_damage // divisor
        
        result["yards_back"] = yards_back
        
        # Calcula rolagem necessária
        # Maior entre DX, Acrobatics ou Judo
        # Usamos DX como padrão (seria necessário input do jogador)
        roll_needed = 10  # DX padrão
        result["knockback_roll_needed"] = roll_needed
        
        # Calcula modificador da rolagem
        roll_modifier = 0
        if yards_back > 1:
            roll_modifier = -(yards_back - 1)  # -1 por jarda após a primeira
        if perfect_balance:
            roll_modifier += 4
        result["roll_modifier"] = roll_modifier
        
        # Mensagem informativa
        if yards_back > 0:
            result["message"] = f"Knockback: {yards_back} jarda(s) para trás."
            if roll_modifier < 0:
                result["message"] += f" Modificador de rolagem: {roll_modifier}"
        else:
            result["message"] = "Sem knockback."
        
        return result
    
    def calculate_knockback_roll(
        self,
        yards_back: int,
        effective_skill: int,
        roll_result: int,
        perfect_balance: bool = False
    ) -> Dict[str, Any]:
        """
        Calcula se o alvo cai ou não após knockback.
        
        Args:
            yards_back: Jardas que o alvo foi empurrado
            effective_skill: Habilidade efetiva (DX, Acrobatics ou Judo)
            roll_result: Resultado da rolagem 3d6
            perfect_balance: Tem Equilíbrio Perfeito?
            
        Returns:
            Dict com resultado da rolagem
        """
        result = {
            "roll_needed": effective_skill,
            "roll_modifier": 0,
            "effective_skill": effective_skill,
            "roll_result": roll_result,
            "success": False,
            "fall_down": False,
            "margin": 0,
            "message": ""
        }
        
        # Calcula modificador
        modifier = 0
        if yards_back > 1:
            modifier = -(yards_back - 1)
        if perfect_balance:
            modifier += 4
        
        result["roll_modifier"] = modifier
        effective = effective_skill + modifier
        result["effective_skill"] = effective
        
        # Verifica sucesso
        if roll_result <= effective:
            result["success"] = True
            result["margin"] = effective - roll_result
            result["message"] = f"Sucesso! Margem: {result['margin']}"
        else:
            result["success"] = False
            result["fall_down"] = True
            result["margin"] = roll_result - effective
            result["message"] = f"Falhou! Cai no chão. Margem: {result['margin']}"
        
        return result