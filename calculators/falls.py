"""
Calculadora de Quedas - GURPS 4e

Regras do Basic Set Revised (p. 430-431):
- Queda é uma colisão com objeto imóvel: o chão
- Velocidade ao impacto da tabela de velocidade de queda
- Dano: (HP × velocidade) / 100
- Superfícies duras: usar 2× HP
- Superfícies macias: dano normal
- Objetos elásticos: DR 2-10
- Água: rolagem de Swimming ou dano normal
- Toda armadura conta como "flexível" para trauma blunt
- Trauma blunt: 1 HP por 5 pontos de dano
- Acrobatics pode reduzir distância em 5 jardas
"""
from typing import Dict, Any
from utils.dice_roller import get_falling_velocity, calculate_collision_damage


class FallsCalculator:
    """Calculadora de Quedas do GURPS 4e."""
    
    def calculate_fall(
        self,
        distance_yards: int,
        target_hp: int,
        surface_type: str = "hard",
        acrobatics_success: bool = False,
        swimming_success: bool = False
    ) -> Dict[str, Any]:
        """
        Calcula dano de uma queda.
        
        Args:
            distance_yards: Distância da queda em jardas
            target_hp: HP do alvo
            surface_type: "hard", "soft", "elastic", ou "water"
            acrobatics_success: Rolagem de Acrobatics teve sucesso?
            swimming_success: Rolagem de Swimming teve sucesso? (para água)
            
        Returns:
            Dict com resultados da queda
        """
        result = {
            "distance_yards": distance_yards,
            "original_distance": distance_yards,
            "target_hp": target_hp,
            "surface_type": surface_type,
            "acrobatics_used": acrobatics_success,
            "swimming_used": swimming_success,
            "velocity": 0,
            "effective_hp": target_hp,
            "damage_dice": "",
            "damage_total": 0,
            "blunt_trauma": 0,
            "total_injury": 0,
            "dodge_drop_possible": True,
            "valid": True,
            "message": ""
        }
        
        # Aplica redução de Acrobatics
        if acrobatics_success and distance_yards > 5:
            distance_yards -= 5
            result["distance_yards"] = distance_yards
        
        # Calcula velocidade
        velocity = get_falling_velocity(distance_yards)
        result["velocity"] = velocity
        
        # Calcula HP efetivo baseado no tipo de superfície
        effective_hp = target_hp
        surface_dr = 0
        if surface_type == "hard":
            # Superfícies duras: 2× HP
            effective_hp = target_hp * 2
        elif surface_type == "elastic":
            # Superfícies elásticas: DR 5 (reduz dano)
            surface_dr = 5
        elif surface_type == "water":
            if swimming_success:
                # Sucesso em Swimming: sem dano
                result["damage_dice"] = "0d"
                result["damage_total"] = 0
                result["blunt_trauma"] = 0
                result["total_injury"] = 0
                result["message"] = "Mergulho limpo! Sem dano."
                return result
        
        result["effective_hp"] = effective_hp
        
        # Calcula dano
        damage, dice_expr = calculate_collision_damage(effective_hp, velocity)
        result["damage_dice"] = dice_expr
        result["damage_total"] = damage
        
        # Aplica DR da superfície elástica
        if surface_dr > 0:
            damage = max(0, damage - surface_dr)
        
        # Calcula trauma blunt (1 HP por 5 pontos de dano)
        blunt_trauma = damage // 5
        result["blunt_trauma"] = blunt_trauma
        
        # Lesão total
        total_injury = damage + blunt_trauma
        result["total_injury"] = total_injury
        
        # Gera mensagem
        message_parts = [
            f"Distância: {result['original_distance']} jardas",
            f"Velocidade: {velocity} jardas/seg",
            f"Dano: {dice_expr} = {damage}",
        ]
        
        if blunt_trauma > 0:
            message_parts.append(f"Trauma Blunt: {blunt_trauma} HP")
        
        message_parts.append(f"Lesão Total: {total_injury} HP")
        
        if surface_type == "water" and not swimming_success:
            message_parts.append("Rolagem de Swimming falhou! Dano normal.")
        
        result["message"] = "\n".join(message_parts)
        
        return result
    
    def get_falling_velocity_table(self) -> Dict[int, int]:
        """
        Retorna a tabela completa de velocidade de queda.
        
        Returns:
            Dict comdistância: velocidade
        """
        return {
            1: 5, 2: 7, 3: 8, 4: 9, 5: 10,
            6: 11, 7: 12, 8: 13, 9: 14, 10: 15,
            11: 15, 12: 16, 13: 17, 14: 17, 15: 18,
            16: 19, 17: 19, 18: 20, 19: 20, 20: 21,
            21: 21, 22: 22, 23: 22, 24: 23, 25: 23,
            26: 24, 27: 24, 28: 25, 29: 25, 30: 26,
            31: 26, 32: 26, 33: 27, 34: 27, 35: 28,
            36: 28, 37: 28, 38: 29, 39: 29, 40: 30,
            41: 30, 42: 30, 43: 31, 44: 31, 45: 31,
            46: 32, 47: 32, 48: 32, 49: 33, 50: 33,
        }
    
    def calculate_blunt_trauma(
        self,
        damage: int,
        is_flexible_armor: bool = True
    ) -> int:
        """
        Calcula trauma blunt de armadura flexível.
        
        Args:
            damage: Dano que atingiu a armadura
            is_flexible_armor: É armadura flexível?
            
        Returns:
            HP de trauma blunt
        """
        if not is_flexible_armor:
            return 0
        
        # 1 HP por 5 pontos de dano (crushing)
        # 1 HP por 10 pontos de dano (cutting/impaling/piercing)
        return damage // 5