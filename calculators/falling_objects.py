"""
Calculadora de Queda de Objetos - GURPS 4e

Regras do Basic Set Revised (p. 431):
- Usar mesma tabela de velocidade de queda
- Dano: (HP × velocidade) / 100
- Para acertar: Dropping skill (Habilidade 15 padrão)
- Alvo não pode esquivar se não souber que vem
- Se souber, pode fazer Dodge
- Objeto com SM ≥ SM do alvo: impede movimento
- Penalidade: -3 a defesas, Move 1 no próximo turno
- Penalidades resultam de volume, não massa (ST irrelevante)
"""
from typing import Dict, Any
from utils.dice_roller import get_falling_velocity, calculate_collision_damage


class FallingObjectsCalculator:
    """Calculadora de Queda de Objetos do GURPS 4e."""
    
    def calculate_falling_object(
        self,
        distance_yards: int,
        object_hp: int,
        target_hp: int,
        target_sm: int = 0,
        object_sm: int = 0,
        target_aware: bool = False,
        dropping_skill: int = 15
    ) -> Dict[str, Any]:
        """
        Calcula dano de objeto caindo.
        
        Args:
            distance_yards: Distância da queda em jardas
            object_hp: HP do objeto
            target_hp: HP do alvo
            target_sm: Size Modifier do alvo
            object_sm: Size Modifier do objeto
            target_aware: Alvo sabe que o objeto vem?
            dropping_skill: Habilidade Dropping (padrão: 15)
            
        Returns:
            Dict com resultados
        """
        result = {
            "distance_yards": distance_yards,
            "object_hp": object_hp,
            "target_hp": target_hp,
            "target_sm": target_sm,
            "object_sm": object_sm,
            "target_aware": target_aware,
            "dropping_skill": dropping_skill,
            "velocity": 0,
            "damage_dice": "",
            "damage_total": 0,
            "hit_automatically": False,
            "target_can_dodge": False,
            "move_penalty": 0,
            "defense_penalty": 0,
            "valid": True,
            "message": ""
        }
        
        # Calcula velocidade
        velocity = get_falling_velocity(distance_yards)
        result["velocity"] = velocity
        
        # Calcula dano
        damage, dice_expr = calculate_collision_damage(object_hp, velocity)
        result["damage_dice"] = dice_expr
        result["damage_total"] = damage
        
        # Verifica se atinge automaticamente
        # Acerto automático se o objeto atinge o alvo diretamente
        hit_automatically = True  # Simplificação
        result["hit_automatically"] = hit_automatically
        
        # Verifica se o alvo pode esquivar
        target_can_dodge = target_aware
        result["target_can_dodge"] = target_can_dodge
        
        # Verifica penalidades de movimento e defesa
        move_penalty = 0
        defense_penalty = 0
        
        if object_sm >= target_sm:
            # Objeto com SM ≥ SM do alvo impede movimento
            move_penalty = 1  # Move 1 no próximo turno
            defense_penalty = 3  # -3 a defesas
        
        result["move_penalty"] = move_penalty
        result["defense_penalty"] = defense_penalty
        
        # Gera mensagem
        message_parts = [
            f"Distância: {distance_yards} jardas",
            f"Velocidade: {velocity} jardas/seg",
            f"Dano: {dice_expr} = {damage}",
        ]
        
        if hit_automatically:
            message_parts.append("Acerto automático!")
        
        if target_can_dodge:
            message_parts.append("Alvo pode fazer Dodge!")
        else:
            message_parts.append("Alvo não sabe que o objeto vem!")
        
        if move_penalty > 0:
            message_parts.append(f"Penalidade de movimento: -{move_penalty} (Move 1)")
        
        if defense_penalty > 0:
            message_parts.append(f"Penalidade de defesa: -{defense_penalty}")
        
        result["message"] = "\n".join(message_parts)
        
        return result
    
    def calculate_drop_attack(
        self,
        distance_yards: int,
        object_hp: int,
        object_sm: int,
        target_sm: int,
        dropping_skill: int = 15,
        target_dodge: int = 10
    ) -> Dict[str, Any]:
        """
        Calcula ataque de objeto caindo (regras completas).
        
        Args:
            distance_yards: Distância da queda
            object_hp: HP do objeto
            object_sm: Size Modifier do objeto
            target_sm: Size Modifier do alvo
            dropping_skill: Habilidade Dropping
            target_dodge: Esquiva do alvo
            
        Returns:
            Dict com resultados
        """
        result = {
            "distance_yards": distance_yards,
            "object_hp": object_hp,
            "object_sm": object_sm,
            "target_sm": target_sm,
            "dropping_skill": dropping_skill,
            "target_dodge": target_dodge,
            "velocity": 0,
            "damage_dice": "",
            "damage_total": 0,
            "effective_skill": 0,
            "target_dodge_modified": 0,
            "valid": True,
            "message": ""
        }
        
        # Calcula velocidade e dano
        velocity = get_falling_velocity(distance_yards)
        result["velocity"] = velocity
        
        damage, dice_expr = calculate_collision_damage(object_hp, velocity)
        result["damage_dice"] = dice_expr
        result["damage_total"] = damage
        
        # Habilidade efetiva (Dropping + modificador de alcance)
        # Simplificação: assume alcance curto
        effective_skill = dropping_skill
        result["effective_skill"] = effective_skill
        
        # Modificador de defesa do alvo
        # Penalidade baseada no SM do objeto
        target_dodge_modified = target_dodge
        if object_sm >= target_sm:
            target_dodge_modified -= 3
        
        result["target_dodge_modified"] = target_dodge_modified
        
        # Gera mensagem
        result["message"] = (
            f"Ataque de objeto caindo!\n"
            f"Distância: {distance_yards} jardas\n"
            f"Velocidade: {velocity} jardas/seg\n"
            f"Dano: {dice_expr} = {damage}\n"
            f"Habilidade de ataque: {effective_skill}\n"
            f"Esquiva do alvo: {target_dodge_modified}"
        )
        
        return result