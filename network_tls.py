"""Sertifika doğrulamasını kapatmadan güvenilir TLS bağlamı."""
import ssl

try:
    import certifi
except ImportError:  # pragma: no cover - sistem CA deposu kullanılabilir
    certifi = None


def verified_context():
    return ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()
