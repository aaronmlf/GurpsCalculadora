"""Mass Combat pp. 35-38: battle victory is distinct from winning a round."""
def battle_end(data, margin, attacker_loss, defender_loss):
    a=data.attacker_casualties+attacker_loss
    d=data.defender_casualties+defender_loss
    if a>=100 or d>=100:
        return {'victor':'mutual' if a>=100 and d>=100 else 'defender' if a>=100 else 'attacker',
                'voluntary_retreat':False,'reason':'casualties'}
    ar=data.attacker_strategy=='full_retreat' or data.attacker_strategy=='fighting_retreat' and margin>=0
    dr=data.defender_strategy=='full_retreat' or data.defender_strategy=='fighting_retreat' and margin<=0
    if ar or dr:
        return {'victor':'neither' if ar and dr else 'defender' if ar else 'attacker',
                'voluntary_retreat':not(ar and dr),'reason':'retreat'}
    return {}
