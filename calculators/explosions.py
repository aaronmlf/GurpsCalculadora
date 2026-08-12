"""
Calculadora de Explosões - GURPS 4e

Regras do Basic Set Revised (p. 414-415):
- Dano colateral em (2 × dados de dano) jardas
- Dano para outros: rolar dano, dividir por (3 × distância em jardas)
- DR de múltiplas fontes é aditivo
- Fragmentação: (5 × dados de fragmentação) jardas de alcance
- Fragmentos atacam com habilidade 15
- Tabela de Força Relativa Explosiva (REF)
"""
from typing import Dict, Any
from utils.dice_roller import roll_dice


class ExplosionsCalculator:
    """Calculadora de Explosões do GURPS 4e."""
    
    def calculate_explosion(
        self,
        basic_damage_dice: int,
        fragmentation_dice: int,
        distance_yards: int,
        target_dr: int = 0,
        blast_radius_multiplier: int = 2,
        damage_divisor: int = 3
    ) -> Dict[str, Any]:
        """
        Calcula dano de explosão.
        
        Args:
            basic_damage_dice: Número de dados de dano básico
            fragmentation_dice: Número de dados de fragmentação
            distance_yards: Distância do epicentro em jardas
            target_dr: DR do alvo
            blast_radius_multiplier: Multiplicador do raio (padrão: 2)
            damage_divisor: Divisor de dano (padrão: 3)
            
        Returns:
            Dict com resultados da explosão
        """
        result = {
            "basic_damage_dice": basic_damage_dice,
            "fragmentation_dice": fragmentation_dice,
            "distance_yards": distance_yards,
            "target_dr": target_dr,
            "blast_radius": basic_damage_dice * blast_radius_multiplier,
            "fragment_radius": fragmentation_dice * 5,
            "collateral_damage_dice": "",
            "collateral_damage_total": 0,
            "fragment_damage_dice": "",
            "fragment_damage_total": 0,
            "total_damage": 0,
            "injury": 0,
            "in_danger_zone": False,
            "in_fragment_zone": False,
            "valid": True,
            "message": ""
        }
        
        # Verifica se está na zona de perigo
        in_danger_zone = distance_yards <= result["blast_radius"]
        result["in_danger_zone"] = in_danger_zone
        
        in_fragment_zone = fragmentation_dice > 0 and distance_yards <= result["fragment_radius"]
        result["in_fragment_zone"] = in_fragment_zone
        
        if not in_danger_zone and not in_fragment_zone:
            result["message"] = "Fora da zona de perigo."
            return result
        
        # Calcula dano colateral
        if in_danger_zone:
            # Rola o dano básico
            basic_damage, _ = roll_dice(f"{basic_damage_dice}d")
            
            # Divide por (3 × distância)
            divisor = damage_divisor * max(1, distance_yards)
            collateral_damage = basic_damage // divisor
            result["collateral_damage_dice"] = f"{basic_damage_dice}d/{divisor}"
            result["collateral_damage_total"] = collateral_damage
        
        # Calcula dano de fragmentação
        if in_fragment_zone:
            # Rola dados de fragmentação para cada fragmento
            # Simplificação: média de acertos
            fragment_damage_total = 0
            for _ in range(fragmentation_dice):
                # Cada dado de fragmentação = 1d-1 cutting (GURPS B414)
                fragment_damage, _ = roll_dice("1d-1")
                fragment_damage_total += fragment_damage
            
            result["fragment_damage_dice"] = f"{fragmentation_dice}d"
            result["fragment_damage_total"] = fragment_damage_total
        
        # Dano total
        total_damage = result["collateral_damage_total"] + result["fragment_damage_total"]
        result["total_damage"] = total_damage
        
        # Calcula lesão (subtraindo DR)
        injury = max(0, total_damage - target_dr)
        result["injury"] = injury
        
        # Gera mensagem
        message_parts = []
        
        if in_danger_zone:
            message_parts.append(f"Zona de explosão! Raio: {result['blast_radius']} jardas")
            message_parts.append(f"Dano colateral: {result['collateral_damage_total']}")
        
        if in_fragment_zone:
            message_parts.append(f"Zona de fragmentação! Raio: {result['fragment_radius']} jardas")
            message_parts.append(f"Dano de fragmentos: {result['fragment_damage_total']}")
        
        message_parts.append(f"Dano Total: {total_damage}")
        message_parts.append(f"DR: {target_dr}")
        message_parts.append(f"Lesão: {injury}")
        
        result["message"] = "\n".join(message_parts)
        
        return result
    
    def calculate_internal_explosion(
        self,
        damage_dice: int,
        target_hp: int,
        target_dr: int = 0,
        location: str = "vitals"
    ) -> Dict[str, Any]:
        """
        Calcula explosão interna (dentro de um alvo).
        
        Args:
            damage_dice: Dados de dano
            target_hp: HP do alvo
            target_dr: DR do alvo
            location: Local do impacto
            
        Returns:
            Dict com resultados
        """
        result = {
            "damage_dice": damage_dice,
            "target_hp": target_hp,
            "target_dr": target_dr,
            "location": location,
            "damage_total": 0,
            "wounding_modifier": 1.0,
            "injury": 0,
            "valid": True,
            "message": ""
        }
        
        # Explosão interna: DR não protege!
        damage, _ = roll_dice(f"{damage_dice}d")
        result["damage_total"] = damage
        
        # Modificador de ferimento baseado no local
        wounding_modifiers = {
            "vitals": 3.0,
            "skull": 3.0,
            "eye": 4.0,
            "neck": 2.0,     # GURPS B399
            "torso": 1.0,
            "limb": 0.5      # GURPS B399
        }
        wounding_modifier = wounding_modifiers.get(location, 1.0)
        result["wounding_modifier"] = wounding_modifier
        
        # Calcula lesão
        injury = int(damage * wounding_modifier)
        result["injury"] = injury
        
        # Gera mensagem
        result["message"] = (
            f"Explosão Interna! Local: {location}\n"
            f"Dano: {damage}\n"
            f"Modificador: ×{wounding_modifier}\n"
            f"Lesão: {injury} HP"
        )
        
        return result
    
    def calculate_demolition_charge(
        self,
        required_damage_dice: int,
        explosive_type: str = "tnt"
    ) -> Dict[str, Any]:
        """
        Calcula quantidade de explosivo necessária.
        
        Args:
            required_damage_dice: Dados de dano necessários (em múltiplos de 6d)
            explosive_type: Tipo de explosivo
            
        Returns:
            Dict com informações do explosivo
        """
        # Tabela de Força Relativa Explosiva (REF)
        ref_table = {
            "serpentine_powder": 0.3,
            "ammonium_nitrate": 0.4,
            "black_powder_early": 0.4,
            "black_powder_late": 0.5,
            "diesel_fertilizer": 0.5,
            "dynamite": 0.8,
            "tnt": 1.0,
            "amatol": 1.2,
            "nitroglycerine": 1.5,
            "tetryl": 1.3,
            "composition_b": 1.4,
            "c4": 1.4,
            "octanitrocubane": 4.0,
            "metallic_hydrogen": 6.0
        }
        
        ref = ref_table.get(explosive_type, 1.0)
        
        # Fórmula: (n × n) / 4 libras de TNT
        # Onde n = multiplicador de dano (6d×n)
        n = required_damage_dice / 6  # Converte dados para multiplicador
        weight_tnt = (n * n) / 4
        weight_actual = weight_tnt / ref
        
        result = {
            "required_damage": f"6d×{int(n)}" if n == int(n) else f"6d×{n:.1f}",
            "explosive_type": explosive_type,
            "ref": ref,
            "weight_tnt_lbs": weight_tnt,
            "weight_actual_lbs": weight_actual,
            "weight_actual_kg": weight_actual * 0.453592,
            "message": (
                f"Explosivo necessário: {explosive_type}\n"
                f"REF: {ref}\n"
                f"Peso em TNT: {weight_tnt:.2f} libras\n"
                f"Peso real: {weight_actual:.2f} libras ({weight_actual * 0.453592:.2f} kg)"
            )
        }
        
        return result
    
    def calculate_explosive_damage(
        self,
        weight_lbs: float,
        explosive_type: str = "tnt"
    ) -> Dict[str, Any]:
        """
        Calcula dano de uma quantidade de explosivo.
        
        Args:
            weight_lbs: Peso em libras
            explosive_type: Tipo de explosivo
            
        Returns:
            Dict com informações de dano
        """
        # REF
        ref_table = {
            "tnt": 1.0,
            "dynamite": 0.8,
            "c4": 1.4,
            "composition_b": 1.4,
            "amatol": 1.2,
            "nitroglycerine": 1.5,
            "black_powder_late": 0.5
        }
        
        ref = ref_table.get(explosive_type, 1.0)
        
        # Fórmula: dano = 6d × √(peso × 4 × REF) (GURPS B278)
        damage_multiplier = (weight_lbs * 4 * ref) ** 0.5
        
        # Total de dados = 6 × multiplicador (base sempre 6d)
        if damage_multiplier < 1:
            total_dice = 6
        else:
            total_dice = int(6 * damage_multiplier + 0.5)
        
        result = {
            "weight_lbs": weight_lbs,
            "weight_kg": weight_lbs * 0.453592,
            "explosive_type": explosive_type,
            "ref": ref,
            "damage_multiplier": damage_multiplier,
            "damage_dice": total_dice,
            "damage_expression": f"{total_dice}d",
            "message": (
                f"Explosivo: {explosive_type}\n"
                f"Peso: {weight_lbs:.2f} libras ({weight_lbs * 0.453592:.2f} kg)\n"
                f"Multiplicador: ×{damage_multiplier:.2f}\n"
                f"Dano: 6d × {damage_multiplier:.2f} = {total_dice}d"
            )
        }
        
        return result