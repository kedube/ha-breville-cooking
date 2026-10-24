"""Test helpers."""

from __future__ import annotations

import base64
import json
import time


def make_jwt(sub: str = "Salesforce|0051234", exp_in: float = 3600) -> str:
    def part(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{part({'alg': 'none'})}.{part({'sub': sub, 'exp': time.time() + exp_in})}.sig"
