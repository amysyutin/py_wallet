import logging
import re

from app import config

_SECRET_NAMES = [
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "ADDRESS_EVM",
    "RPC_URL_MAIN",
    "RPC_URL_BASE",
    "RPC_URL_BNB",
    "RPC_URL_ARB",
    "RPC_URL_LINEA",
]

_KEY_NAME_PATTERNS = [
    re.compile(
        r"(?i)(JWT_SECRET|jwt_secret|BINANCE_SECRET|BINANCE_API_KEY|Authorization)"
        r"\s*[=:]\s*\S+"
    ),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-_\.]+"),
]

_MASK = "***"
_MIN_SECRET_LEN = 6


def _build_patterns() -> list[re.Pattern]:
    patterns = list(_KEY_NAME_PATTERNS)
    for name in _SECRET_NAMES:
        val = getattr(config, name, "") or ""
        if len(val) >= _MIN_SECRET_LEN:
            patterns.append(re.compile(re.escape(val)))
    return patterns


_patterns = _build_patterns()


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._redact(a) for a in record.args)
        return True

    @classmethod
    def _redact(cls, value: object) -> object:
        if not isinstance(value, str):
            value = str(value)
        for pat in _patterns:
            value = pat.sub(_MASK, value)
        return value


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        handler.addFilter(SecretFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger
