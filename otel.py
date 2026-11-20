import atexit
import json
import logging
import os
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from opentelemetry.instrumentation.ollama import OllamaInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("otel")

# Module-level provider references for lifecycle management (flush / shutdown)
_tracer_provider: Optional[TracerProvider] = None
_logger_provider: Optional[LoggerProvider] = None
_meter_provider: Optional[MeterProvider] = None
_requests_counter: Optional[metrics.Counter] = None


class JsonFormatter(logging.Formatter):
    def format(self, record) -> str:
        log_record = {
            "timestamp": record.created,
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "pathname": record.pathname,
            "lineno": record.lineno,
        }
        return json.dumps(log_record)


def _get_resource(service_name: str) -> Resource:
    instance_id = os.getenv("POD_NAME", "1")
    return Resource.create(
        {
            "service.name": service_name,
            "service.instance.id": f"{service_name}-{instance_id}",
            "k8s.pod.name": os.getenv("POD_NAME", "Undefined"),
            "k8s.namespace.name": os.getenv("POD_NAMESPACE", "Undefined"),
            "k8s.pod.ip": os.getenv("POD_IP", "Undefined"),
            "k8s.node.name": os.getenv("NODE_NAME", "Undefined"),
        }
    )


def setup_otel_instrumentation(
    tracer_provider: Optional[TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
    logger_provider: Optional[LoggerProvider] = None,
) -> None:
    tp = tracer_provider or _tracer_provider
    mp = meter_provider or _meter_provider
    lp = logger_provider or _logger_provider

    try:
        kwargs = {}
        if tp:
            kwargs["tracer_provider"] = tp
        if mp:
            kwargs["meter_provider"] = mp
        if lp:
            kwargs["logger_provider"] = lp
        OllamaInstrumentor().instrument(**kwargs)
        log.info("Ollama instrumentation ready")
    except Exception as error:
        log.error(f"Ollama instrumentation setup failed. Error: {error}")

    try:
        kwargs = {}
        if tp:
            kwargs["tracer_provider"] = tp
        if mp:
            kwargs["meter_provider"] = mp
        if lp:
            kwargs["logger_provider"] = lp
        LangchainInstrumentor().instrument(**kwargs)
        log.info("Langchain instrumentation ready")
    except Exception as error:
        log.error(f"Langchain instrumentation setup failed. Error: {error}")


def setup_otel_logging(otel_settings: dict) -> bool:
    global _logger_provider
    resource = _get_resource(otel_settings["service_name"])
    host = otel_settings["host"]
    port = otel_settings["port"]
    exporter = OTLPLogExporter(endpoint=f"{host}:{port}", insecure=True)
    _logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(_logger_provider)

    _logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    handler = LoggingHandler(level=logging.INFO, logger_provider=_logger_provider)

    try:
        logging.getLogger().addHandler(handler)
    except Exception:
        log.exception("Adding a handler for OTEL logging failed")
        return False
    return True


def setup_otel_tracing(otel_settings: dict) -> trace.Tracer:
    global _tracer_provider
    service_name = otel_settings["service_name"]
    resource = _get_resource(service_name)
    host = otel_settings["host"]
    port = otel_settings["port"]
    otlp_tracing_exporter = OTLPSpanExporter(
        endpoint=f"{host}:{port}",
        insecure=True,
    )
    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(
        SimpleSpanProcessor(otlp_tracing_exporter)
    )
    trace.set_tracer_provider(_tracer_provider)
    return trace.get_tracer(service_name)


def setup_otel_metrics(otel_settings: dict) -> metrics.Meter:
    global _meter_provider, _requests_counter
    service_name = otel_settings["service_name"]
    resource = _get_resource(service_name)
    host = otel_settings["host"]
    port = otel_settings["port"]
    metric_exporter = OTLPMetricExporter(
        endpoint=f"{host}:{port}",
        insecure=True,
    )
    reader = PeriodicExportingMetricReader(
        exporter=metric_exporter,
        export_interval_millis=3000.0,
        export_timeout_millis=5000.0,
    )
    _meter_provider = MeterProvider(metric_readers=[reader], resource=resource)
    metrics.set_meter_provider(_meter_provider)
    meter = metrics.get_meter(__name__)
    _requests_counter = meter.create_counter(
        name="requests",
        description="Number of requests",
        unit="1",
    )
    return meter


def get_requests_counter() -> Optional[metrics.Counter]:
    return _requests_counter


def flush_telemetry() -> None:
    """Explicitly flush all active providers."""
    if _logger_provider:
        try:
            _logger_provider.force_flush()
        except Exception as e:
            log.debug(f"Error flushing logs: {e}")
    if _meter_provider:
        try:
            _meter_provider.force_flush()
        except Exception as e:
            log.debug(f"Error flushing metrics: {e}")
    if _tracer_provider:
        try:
            _tracer_provider.force_flush()
        except Exception as e:
            log.debug(f"Error flushing traces: {e}")


def shutdown_telemetry() -> None:
    """Shutdown all active providers cleanly to guarantee no in-flight telemetry is lost."""
    global _tracer_provider, _logger_provider, _meter_provider
    if _logger_provider:
        try:
            _logger_provider.shutdown()
        except Exception as e:
            log.debug(f"Error shutting down logger provider: {e}")
        _logger_provider = None
    if _meter_provider:
        try:
            _meter_provider.shutdown()
        except Exception as e:
            log.debug(f"Error shutting down meter provider: {e}")
        _meter_provider = None
    if _tracer_provider:
        try:
            _tracer_provider.shutdown()
        except Exception as e:
            log.debug(f"Error shutting down tracer provider: {e}")
        _tracer_provider = None


# Automatically flush and shutdown on process termination
atexit.register(shutdown_telemetry)
