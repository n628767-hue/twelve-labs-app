import os
from typing import Optional
from twelvelabs import TwelveLabs

_client: Optional[TwelveLabs] = None


def get_client() -> TwelveLabs:
    global _client
    if _client is None:
        api_key = os.environ.get("TWELVELABS_API_KEY")
        if not api_key:
            raise RuntimeError("TWELVELABS_API_KEY environment variable not set")
        _client = TwelveLabs(api_key=api_key)
    return _client
