import os


class Settings:

    PROMETHEUS_URL = os.getenv(
        "PROMETHEUS_URL",
        "http://prometheus.monitoring.svc:9090",
    )

    LOG_PROVIDER = os.getenv(
        "LOG_PROVIDER",
        "kubernetes",  # kubernetes | loki
    )

    LOKI_URL = os.getenv(
        "LOKI_URL",
        "http://loki.monitoring.svc:3100",
    )

    LOG_LINES = int(os.getenv("LOG_LINES", "200"))


settings = Settings()