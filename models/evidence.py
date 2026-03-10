from typing import Dict, Any


class Evidence:

    def __init__(
        self,
        kubernetes: Dict[str, Any] | None = None,
        logs: Dict[str, Any] | None = None,
        metrics: Dict[str, Any] | None = None,
        registry: Dict[str, Any] | None = None,
    ):
        self.kubernetes = kubernetes or {}
        self.logs = logs or {}
        self.metrics = metrics or {}
        self.registry = registry or {}

    def to_dict(self):

        return {
            "kubernetes": self.kubernetes,
            "logs": self.logs,
            "metrics": self.metrics,
            "registry": self.registry,
        }