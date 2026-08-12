"""
Calculadora de Colisões - GURPS 4e

Regras do Basic Set Revised (p. 430-431):
- Fórmula: (HP × velocidade) / 100
- Colisão frontal: soma das velocidades
- Colisão pelas costas: velocidade do mais rápido - mais lento
- Colisão de lado: velocidade do objeto em movimento
- Objetos imóveis: usar 2× HP para superfícies duras
- Superfícies macias: dano normal
- Objetos elásticos: DR 2-10
- Velocidade em jardas/segundo (2 mph = 1 jarda/seg)
"""
from typing import Dict, Any
from utils.dice_roller import calculate_collision_damage, roll_dice


class CollisionsCalculator:
    """Calculadora de Colisões do GURPS 4e."""
    
    def calculate_collision(
        self,
        object1_hp: int,
        object1_velocity: int,
        object2_hp: int,
        object2_velocity: int,
        collision_type: str = "head_on",
        surface_type: str = "normal",
        immovable_object: bool = False
    ) -> Dict[str, Any]:
        """
        Calcula dano de colisão.
        
        Args:
            object1_hp: HP do objeto 1
            object1_velocity: Velocidade do objeto 1
            object2_hp: HP do objeto 2
            object2_velocity: Velocidade do objeto 2
            collision_type: "head_on", "rear_end", ou "side_on"
            surface_type: "hard", "soft", "elastic"
            immovable_object: O objeto 2 é imóvel?
            
        Returns:
            Dict com resultados da colisão
        """
        result = {
            "object1_hp": object1_hp,
            "object1_velocity": object1_velocity,
            "object2_hp": object2_hp,
            "object2_velocity": object2_velocity,
            "collision_type": collision_type,
            "surface_type": surface_type,
            "immovable_object": immovable_object,
            "collision_velocity": 0,
            "object1_damage_dice": "",
            "object2_damage_dice": "",
            "object1_damage_total": 0,
            "object2_damage_total": 0,
            "object1_roll": 0,
            "object2_roll": 0,
            "valid": True,
            "message": ""
        }
        
        # Calcula velocidade de colisão
        collision_velocity = self._calculate_collision_velocity(
            object1_velocity, object2_velocity, collision_type, immovable_object
        )
        result["collision_velocity"] = collision_velocity
        
        if collision_velocity <= 0:
            result["valid"] = False
            result["message"] = "Velocidade de colisão inválida."
            return result
        
        # Calcula HP efetivos baseado no tipo de superfície
        effective_hp1 = object1_hp
        effective_hp2 = object2_hp
        
        if immovable_object:
            if surface_type == "hard":
                # Superfícies duras: 2× HP do objeto em movimento
                effective_hp2 = object2_hp * 2
            elif surface_type == "elastic":
                # Objetos elásticos: DR 2-10 (usamos 5 como padrão)
                effective_hp2 = max(0, object2_hp - 5)
        
        # Calcula dano do objeto 1 no objeto 2
        dice_count1, dice1 = calculate_collision_damage(effective_hp1, collision_velocity)
        roll1, _ = roll_dice(dice1)
        result["object1_damage_dice"] = dice1
        result["object1_damage_total"] = roll1
        
        # Calcula dano do objeto 2 no objeto 1
        dice_count2, dice2 = calculate_collision_damage(effective_hp2, collision_velocity)
        roll2, _ = roll_dice(dice2)
        result["object2_damage_dice"] = dice2
        result["object2_damage_total"] = roll2
        
        result["object1_roll"] = roll1
        result["object2_roll"] = roll2
        
        # Gera mensagem
        message_parts = [
            f"Tipo de colisão: {self._get_collision_type_name(collision_type)}",
            f"Velocidade de colisão: {collision_velocity} jardas/seg",
            f"Objeto 1 causa {roll1} de dano ({dice1})",
            f"Objeto 2 causa {roll2} de dano ({dice2})",
        ]
        
        if immovable_object:
            message_parts.append("Objeto 2 é imóvel!")
        
        result["message"] = "\n".join(message_parts)
        
        return result
    
    def _calculate_collision_velocity(
        self,
        velocity1: int,
        velocity2: int,
        collision_type: str,
        immovable_object: bool
    ) -> int:
        """
        Calcula velocidade de colisão.
        
        Args:
            velocity1: Velocidade do objeto 1
            velocity2: Velocidade do objeto 2
            collision_type: Tipo de colisão
            immovable_object: Objeto 2 é imóvel?
            
        Returns:
            Velocidade de colisão
        """
        if immovable_object:
            # Objeto imóvel: velocidade do objeto em movimento
            return velocity1
        
        if collision_type == "head_on":
            return velocity1 + velocity2
        elif collision_type == "rear_end":
            return abs(velocity1 - velocity2)
        elif collision_type == "side_on":
            return velocity1
        else:
            return velocity1
    
    def _get_collision_type_name(self, collision_type: str) -> str:
        """Retorna nome do tipo de colisão."""
        names = {
            "head_on": "Cabeça a Cabeça",
            "rear_end": "Pela Costas",
            "side_on": "De Lado"
        }
        return names.get(collision_type, "Desconhecido")
    
    def calculate_immovable_object(
        self,
        moving_hp: int,
        moving_velocity: int,
        obstacle_hp: int,
        obstacle_dr: int = 0,
        is_hard: bool = True,
        is_soft: bool = False,
        is_elastic: bool = False,
        elastic_dr: int = 5
    ) -> Dict[str, Any]:
        """
        Calcula colisão com objeto imóvel.
        
        Args:
            moving_hp: HP do objeto em movimento
            moving_velocity: Velocidade do objeto em movimento
            obstacle_hp: HP do obstáculo
            obstacle_dr: DR do obstáculo
            is_hard: É superfície dura?
            is_soft: É superfície macia?
            is_elastic: É elástico?
            elastic_dr: DR de objetos elásticos
            
        Returns:
            Dict com resultados
        """
        result = {
            "moving_hp": moving_hp,
            "moving_velocity": moving_velocity,
            "obstacle_hp": obstacle_hp,
            "obstacle_dr": obstacle_dr,
            "is_hard": is_hard,
            "is_soft": is_soft,
            "is_elastic": is_elastic,
            "collision_velocity": moving_velocity,
            "moving_damage_dice": "",
            "obstacle_damage_dice": "",
            "moving_damage_total": 0,
            "obstacle_damage_total": 0,
            "valid": True,
            "message": ""
        }
        
        # Calcula dano no objeto em movimento
        if is_hard:
            effective_hp = moving_hp * 2
        else:
            effective_hp = moving_hp
        
        damage, dice = calculate_collision_damage(effective_hp, moving_velocity)
        result["moving_damage_dice"] = dice
        result["moving_damage_total"] = damage
        
        # Dano no obstáculo (se quebrável)
        obstacle_damage = 0
        if obstacle_hp > 0:
            obstacle_damage, obstacle_dice = calculate_collision_damage(
                obstacle_hp, moving_velocity
            )
            result["obstacle_damage_dice"] = obstacle_dice
            result["obstacle_damage_total"] = obstacle_damage
        
        # Gera mensagem
        message_parts = [
            f"Velocidade: {moving_velocity} jardas/seg",
            f"Dano no objeto em movimento: {dice} = {damage}",
        ]
        
        if obstacle_damage > 0:
            message_parts.append(f"Dano no obstáculo: {obstacle_damage}")
        
        if is_hard:
            message_parts.append("Superfície dura: 2× HP aplicado")
        
        result["message"] = "\n".join(message_parts)
        
        return result