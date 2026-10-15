# Python imports
import ipaddress
import socket
from urllib.parse import urlparse


class BlockedURLError(ValueError):
    """Raised when an outbound URL points at a disallowed destination"""


class HostResolutionError(BlockedURLError):
    """Raised when the hostname cannot be resolved (may be temporary)"""


# NAT64 well-known prefix: the last 32 bits are an IPv4 address
NAT64_NETWORK = ipaddress.ip_network("64:ff9b::/96")


def is_blocked_ip(value):
    """
    Block every address that is not publicly routable: private, loopback,
    link-local (incl. cloud metadata 169.254.169.254), shared, reserved,
    unspecified and multicast ranges. IPv4-mapped IPv6 is checked as IPv4.
    """
    ip = ipaddress.ip_address(value)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    elif ip.version == 6 and ip in NAT64_NETWORK:
        ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return not ip.is_global or ip.is_multicast


def validate_outbound_url(url, blocked_domains=()):
    """
    Validate a user supplied URL before the server makes a request to it.
    Resolves the hostname and rejects it if any resolved address is blocked.
    Returns the hostname; raises BlockedURLError otherwise.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedURLError("Invalid schema. Only HTTP and HTTPS are allowed.")

    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not hostname:
        raise BlockedURLError("Invalid URL: No hostname found.")

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise BlockedURLError("Local URLs are not allowed.")

    if any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in blocked_domains
    ):
        raise BlockedURLError("URL domain or its subdomain is not allowed.")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(hostname, port)
    except (socket.gaierror, UnicodeError, ValueError):
        raise HostResolutionError("Hostname could not be resolved.")

    if not addresses:
        raise BlockedURLError("No IP addresses found for the hostname.")

    for address in addresses:
        if is_blocked_ip(address[4][0]):
            raise BlockedURLError("URL resolves to a blocked IP address.")

    return hostname
