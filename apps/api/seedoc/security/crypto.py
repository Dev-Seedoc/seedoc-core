import hashlib


def get_ip_hash(ip: str, pepper: str) -> str:
    """sha256(IP_HASH_PEPPER || ip) as hex. The raw IP is never stored or logged (BUSINESS_RULES §5)."""
    return hashlib.sha256(pepper.encode() + ip.encode()).hexdigest()
