"""
Calculadora de Slam/Investida - GURPS 4e

Regras do Basic Set Revised (p. 371):
- Ataque deliberado com o corpo
- Rolagem: DX, Brawling ou Sumo Wrestling
- Se acertar, ambos levam dano crushing: (HP × velocidade) / 100
- Velocidade = jardas movidas neste turno
- Colisão frontal: somar distância que o oponente moveu
- Frações: <1d = 1d-3, 1d-2, 1d-1
- Arredondar frações ≥ 0.5 para dado completo
- Adicionar bônus de habilidade (Brawling/Sumo Wrestling) ou All-Out Attack (Strong)
- Se dano ≥ dano do oponente, oponente rola DX ou cai
- Derrubamento automático se rolar 2× o dano do oponente
- Se oponente rolar 2× seu dano, você cai
"""
from typing import Dict, Any
from utils.dice_roller import calculate_collision_damage, roll_dice


class SlamCalculator:
    """Calculadora de Slam/Investida do GURPS 4e."""
    
    def calculate_slam(
        self,
        attacker_hp: int,
        attacker_velocity: int,
        defender_hp: int,
        defender_velocity: int,
        collision_type: str = "head_on",
        attacker_skill_bonus: int = 0,
        defender_skill_bonus: int = 0
    ) -> Dict[str, Any]:
        """
        Calcula dano e resultado de uma investida.
        
        Args:
            attacker_hp: HP do atacante
            attacker_velocity: Velocidade do atacante (jardas/seg)
            defender_hp: HP do defensor
            defender_velocity: Velocidade do defensor (jardas/seg)
            collision_type: "head_on", "rear_end", ou "side_on"
            attacker_skill_bonus: Bônus de habilidade do atacante
            defender_skill_bonus: Bônus de habilidade do defensor
            
        Returns:
            Dict com resultados da investida
        """
        result = {
            "collision_type": collision_type,
            "attacker_hp": attacker_hp,
            "attacker_velocity": attacker_velocity,
            "defender_hp": defender_hp,
            "defender_velocity": defender_velocity,
            "collision_velocity": 0,
            "attacker_damage_dice": "",
            "defender_damage_dice": "",
            "attacker_damage_total": 0,
            "defender_damage_total": 0,
            "attacker_roll": 0,
            "defender_roll": 0,
            "attacker_fall": False,
            "defender_fall": False,
            "result_text": "",
            "valid": True,
            "message": ""
        }
        
        # Calcula velocidade de colisão
        collision_velocity = self._calculate_collision_velocity(
            attacker_velocity, defender_velocity, collision_type
        )
        result["collision_velocity"] = collision_velocity
        
        if collision_velocity <= 0:
            result["valid"] = False
            result["message"] = "Velocidade de colisão inválida."
            return result
        
        # Calcula dano do atacante no defensor
        att_dice_count, att_dice = calculate_collision_damage(attacker_hp, collision_velocity)
        att_roll, _ = roll_dice(att_dice)
        # Adiciona bônus de habilidade do atacante ao resultado rolado
        att_damage = att_roll + attacker_skill_bonus
        result["attacker_damage_dice"] = att_dice
        result["attacker_damage_total"] = att_damage
        
        # Calcula dano do defensor no atacante
        def_dice_count, def_dice = calculate_collision_damage(defender_hp, collision_velocity)
        def_roll, _ = roll_dice(def_dice)
        # Adiciona bônus de habilidade do defensor (se aplicável)
        def_damage = def_roll + defender_skill_bonus
        result["defender_damage_dice"] = def_dice
        result["defender_damage_total"] = def_damage
        
        # Calcula rolagens de dano
        result["attacker_roll"] = att_roll
        result["defender_roll"] = def_roll
        
        # Verifica se cada um cai
        # Regra: Se dano ≥ 2× dano do oponente, oponente cai automaticamente
        # Se dano ≥ dano do oponente, oponente rola DX ou cai
        
        # Verifica defensor
        if att_damage >= def_damage * 2:
            result["defender_fall"] = True
            result["result_text"] = f"Defensor derrubado automaticamente! ({att_damage} ≥ {def_damage * 2})"
        elif att_damage >= def_damage:
            # Defensor precisa rolar DX ou cai
            result["result_text"] = f"Defensor precisa rolar DX ou cai! ({att_damage} ≥ {def_damage})"
        else:
            result["result_text"] = f"Defensor não é derrubado. ({att_damage} < {def_damage})"
        
        # Verifica atacante
        if def_damage >= att_damage * 2:
            result["attacker_fall"] = True
            result["result_text"] += f"\nAtacante derrubado automaticamente! ({def_damage} ≥ {att_damage * 2})"
        elif def_damage >= att_damage:
            result["result_text"] += f"\nAtacante precisa rolar DX ou cai! ({def_damage} ≥ {att_damage})"
        
        # Gera mensagem
        result["message"] = (
            f"Velocidade de colisão: {collision_velocity}\n"
            f"Atacante causa {att_damage} de dano no defensor\n"
            f"Defensor causa {def_damage} de dano no atacante"
        )
        
        return result
    
    def _calculate_collision_velocity(
        self,
        velocity1: int,
        velocity2: int,
        collision_type: str
    ) -> int:
        """
        Calcula velocidade de colisão baseado no tipo.
        
        Args:
            velocity1: Velocidade do objeto 1
            velocity2: Velocidade do objeto 2
            collision_type: Tipo de colisão
            
        Returns:
            Velocidade de colisão
        """
        if collision_type == "head_on":
            # Cabeça a cabeça: soma das velocidades
            return velocity1 + velocity2
        elif collision_type == "rear_end":
            # Pela costas: velocidade do mais rápido - mais lento
            return abs(velocity1 - velocity2)
        elif collision_type == "side_on":
            # De lado: velocidade do objeto em movimento
            return velocity1
        else:
            return velocity1
    
    def calculate_slam_attack_roll(
        self,
        skill: int,
        roll_result: int,
        is_move_and_attack: bool = False
    ) -> Dict[str, Any]:
        """
        Calcula rolagem de ataque para slam.
        
        Args:
            skill: Habilidade (DX, Brawling ou Sumo Wrestling)
            roll_result: Resultado da rolagem 3d6
            is_move_and_attack: É Move and Attack?
            
        Returns:
            Dict com resultado da rolagem
        """
        result = {
            "skill": skill,
            "roll_result": roll_result,
            "success": False,
            "critical_hit": False,
            "critical_miss": False,
            "margin": 0,
            "message": ""
        }
        
        # Verifica acerto/erro crítico
        if roll_result <= 4:
            result["critical_hit"] = True
            result["success"] = True
            result["message"] = "Acerto Crítico!"
        elif roll_result >= 17:
            result["critical_miss"] = True
            result["success"] = False
            result["message"] = "Erro Crítico!"
        elif roll_result <= skill:
            result["success"] = True
            result["margin"] = skill - roll_result
            result["message"] = f"Acertou! Margem: {result['margin']}"
        else:
            result["success"] = False
            result["margin"] = roll_result - skill
            result["message"] = f"Errou! Margem: {result['margin']}"
        
        return result