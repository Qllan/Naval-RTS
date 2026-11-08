"""Per-port guild reputation and trade-service perks."""

MAX_REPUTATION = 100
PARTNER_AT = 20
TRUSTED_AT = 50
REPUTATION_GAIN = {
    "salt": 5, "pirates": 5, "scout": 5,
    "escort": 8, "urgent": 8, "guild": 10,
}


def new_reputation():
    return {"port": 0, "platform": 0}


def valid_reputation(data):
    return (type(data) is dict and set(data) == {"port", "platform"}
            and all(type(v) is int and 0 <= v <= MAX_REPUTATION
                    for v in data.values()))


def rank(points):
    if points >= TRUSTED_AT:
        return "Доверенный партнёр"
    if points >= PARTNER_AT:
        return "Партнёр гильдии"
    return "Новичок"


def discount(points):
    """Tiered service discount, with a 10% maximum."""
    if points >= TRUSTED_AT:
        return 0.10
    if points >= PARTNER_AT:
        return 0.05
    return 0.0


def add_reputation(reputation, port, contract):
    points = REPUTATION_GAIN.get(contract, 0)
    if port not in reputation or points <= 0:
        return 0
    old = reputation[port]
    reputation[port] = min(MAX_REPUTATION, old + points)
    return reputation[port] - old
