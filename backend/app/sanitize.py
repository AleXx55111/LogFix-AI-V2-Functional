"""Redact before indexing, storage, display and AI calls."""
import re

_PATTERNS = [
    (re.compile(r'(?i)\b(bearer\s+)[a-z0-9._~+/-]{8,}'), r'\1[REDACTED]'),
    (re.compile(r'(?i)\b(authorization\s*[:=]\s*)([^\s,;]+)'), r'\1[REDACTED]'),
    (re.compile(r'(?i)\b(api[_-]?key|password|passwd|secret|token|access[_-]?key)\b\s*[:=]\s*["\']?([^\s,;"\']+)'), r'\1=[REDACTED]'),
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), '[REDACTED_AWS_KEY]'),
    (re.compile(r'(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.])'), '[REDACTED_EMAIL]'),
    (re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', re.S), '[REDACTED_PRIVATE_KEY]'),
]

def redact(value: str, max_length: int = 2000) -> str:
    result = str(value)
    for pattern, repl in _PATTERNS:
        result = pattern.sub(repl, result)
    return result[:max_length]
