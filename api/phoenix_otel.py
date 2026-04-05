"""Optional Phoenix (arize-phoenix-otel) export for LLM traces. No-op when PHOENIX_COLLECTOR_ENDPOINT is unset."""
import atexit
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_initialized = False
_tracer_provider = None


def _normalize_http_otlp_endpoint(raw: str) -> str:
    """OTLP HTTP/protobuf expects .../v1/traces on the Phoenix HTTP port (typically 6006)."""
    raw = raw.strip().rstrip("/")
    if not raw:
        return raw
    if raw.endswith("/v1/traces"):
        return raw
    return f"{raw}/v1/traces"


def _host_from_collector_url(raw: str) -> str:
    """Extract hostname from PHOENIX_COLLECTOR_ENDPOINT (any port/path)."""
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = parsed.hostname
    if not host:
        raise ValueError(f"cannot parse host from PHOENIX_COLLECTOR_ENDPOINT: {raw!r}")
    return host


def _resolve_otlp() -> tuple[str, str]:
    """
    Returns (endpoint, protocol) for phoenix.otel.register().

    Default: OTLP **gRPC** to :4317 (Phoenix chart exposes standard OTLP gRPC here).
    HTTP/protobuf to :6006/v1/traces often fails silently depending on routing; override with
    PHOENIX_OTLP_PROTOCOL=http/protobuf.
    """
    raw = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "").strip()
    if not raw:
        return "", ""

    proto = (os.getenv("PHOENIX_OTLP_PROTOCOL") or "grpc").strip().lower()
    if proto in ("http", "http/protobuf", "http-protobuf"):
        return _normalize_http_otlp_endpoint(raw), "http/protobuf"

    # gRPC: ignore path/port in URL; use standard OTLP gRPC port on same host as Phoenix
    host = _host_from_collector_url(raw)
    grpc_url = f"http://{host}:4317"
    return grpc_url, "grpc"


def _log_phoenix_http_reachable(host: str) -> None:
    """Best-effort GET to Phoenix UI port (does not prove OTLP, but catches DNS/network issues)."""
    try:
        import urllib.request

        url = f"http://{host}:6006/"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info("Phoenix HTTP check %s -> %s", url, resp.status)
    except Exception as e:
        logger.warning("Phoenix HTTP reachability check failed (non-fatal): %s", e)


def _emit_insomnia_project_bootstrap_trace(tracer_provider) -> None:
    """Send one span so Phoenix creates the project (resource carries openinference.project.name)."""
    if os.getenv("PHOENIX_SKIP_BOOTSTRAP_TRACE", "").strip().lower() in ("1", "true", "yes"):
        return
    try:
        tracer = tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span("insomnia-bootstrap-probe"):
            pass
        try:
            from opentelemetry import trace as trace_api

            prov = trace_api.get_tracer_provider()
            ff = getattr(prov, "force_flush", None)
            if callable(ff):
                ff(timeout_millis=5000)
        except Exception:
            pass
        logger.info("Phoenix bootstrap span sent (project should appear as %s)", os.getenv("PHOENIX_PROJECT_NAME", "default"))
    except Exception:
        logger.exception("Phoenix bootstrap trace failed")


def init_phoenix_otel() -> None:
    """Register Phoenix OTEL + OpenInference OpenAI instrumentation before any OpenAI() usage."""
    global _initialized, _tracer_provider
    if _initialized:
        return
    if not os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "").strip():
        return
    try:
        from openinference.instrumentation.openai import OpenAIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from phoenix.otel import PROJECT_NAME, register

        endpoint, protocol = _resolve_otlp()
        project_name = os.getenv("PHOENIX_PROJECT_NAME", "default")
        service_name = os.getenv("OTEL_SERVICE_NAME", "insomnia").strip() or "insomnia"
        # When Phoenix auth is disabled, a wrong Bearer token can reject OTLP; omit key if unset.
        api_key = (os.getenv("PHOENIX_API_KEY") or "").strip() or None

        # In-cluster gRPC without TLS: OTEL defaults insecure=true when scheme is http
        if protocol == "grpc" and not os.getenv("OTEL_EXPORTER_OTLP_INSECURE"):
            os.environ["OTEL_EXPORTER_OTLP_INSECURE"] = "true"

        try:
            host = _host_from_collector_url(os.getenv("PHOENIX_COLLECTOR_ENDPOINT", ""))
            _log_phoenix_http_reachable(host)
        except Exception:
            pass

        otel_resource = Resource.create(
            {
                PROJECT_NAME: project_name,
                "service.name": service_name,
            }
        )
        tp = register(
            endpoint=endpoint,
            project_name=project_name,
            auto_instrument=False,
            protocol=protocol,
            verbose=False,
            api_key=api_key,
            resource=otel_resource,
        )
        _tracer_provider = tp
        OpenAIInstrumentor().instrument(tracer_provider=tp)

        _emit_insomnia_project_bootstrap_trace(tp)

        def _shutdown_otel() -> None:
            try:
                from opentelemetry import trace as trace_api

                prov = trace_api.get_tracer_provider()
                if prov is not None and hasattr(prov, "shutdown"):
                    prov.shutdown()
            except Exception:
                pass

        atexit.register(_shutdown_otel)

        logger.info(
            "Phoenix OTEL enabled: project=%s endpoint=%s protocol=%s (OpenAI instrumented)",
            project_name,
            endpoint,
            protocol,
        )
        _initialized = True
    except Exception:
        logger.exception("Phoenix OTEL init failed; continuing without Phoenix export")


def get_tracer_provider():
    """Return the Phoenix/OpenInference TracerProvider after init, or None."""
    return _tracer_provider


def emit_debug_phoenix_chain_trace() -> bool:
    """Emit another @tracer.chain span (e.g. from GET /debug/phoenix-trace when enabled)."""
    tp = get_tracer_provider()
    if not tp:
        return False
    try:
        tracer = tp.get_tracer("api.phoenix_otel.debug")

        @tracer.chain
        def _debug_ping(input: str) -> str:
            return f"Processed: {input}"

        _debug_ping("debug")
        try:
            from opentelemetry import trace as trace_api

            prov = trace_api.get_tracer_provider()
            ff = getattr(prov, "force_flush", None)
            if callable(ff):
                ff(timeout_millis=5000)
        except Exception:
            pass
        return True
    except Exception:
        logger.exception("Phoenix debug chain trace failed")
        return False
