import json
import logging
import os

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
from opentelemetry.instrumentation.ollama import OllamaInstrumentor
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

#log = logging.getLogger(__name__)


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


def setup_otel_instrumentation() -> None:
    try:
        OllamaInstrumentor().instrument()
    except Exception as error:
        log.error(f"Instrumentation setup failed. Error: {error}")
    try:
            LangchainInstrumentor().instrument()
    except Exception as error:
        log.error(f"Instrumentation setup failed. Error: {error}")


def setup_otel_logging(otel_settings: dict) -> bool:
    instance_id = os.getenv("POD_NAME", "1")
    resource = Resource.create(
        {
            "service.name": otel_settings["service_name"],
            "service.instance.id": f"{otel_settings['service_name']}-{instance_id}",
        }
    )
    host = otel_settings["host"]
    port = otel_settings["port"]
    exporter = OTLPLogExporter(endpoint=f"{host}:{port}", insecure=True)
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)

    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

    try:
        logging.getLogger().addHandler(handler)
    except Exception:
        log.exception("Adding a handler for OTEL logging failed")
        return False
    return True


def setup_otel_tracing(otel_settings: dict) -> trace.Tracer:
    service_name = otel_settings["service_name"]
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.instance.id": os.getenv("POD_NAME", "Undefined"),
            "k8s.pod.name": os.getenv("POD_NAME", "Undefined"),
            "k8s.namespace.name": os.getenv("POD_NAMESPACE", "Undefined"),
            "k8s.pod.ip": os.getenv("POD_IP", "Undefined"),
            "k8s.node.name": os.getenv("NODE_NAME", "Undefined"),
        }
    )
    host = otel_settings["host"]
    port = otel_settings["port"]
    otlp_tracing_exporter = OTLPSpanExporter(
        endpoint=f"{host}:{port}",
        insecure=True,
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        SimpleSpanProcessor(otlp_tracing_exporter)
    )
    trace.set_tracer_provider(tracer_provider)
    return trace.get_tracer(service_name)


def setup_otel_metrics(otel_settings: dict) -> metrics.Meter:
    instance_id = os.getenv("POD_NAME", "Undefined")
    resource = Resource.create(
        {
            "service.name": otel_settings["service_name"],
            "service.instance.id": f"{otel_settings['service_name']}-{instance_id}",
        }
    )
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
    meter_provider = MeterProvider(metric_readers=[reader], resource=resource)
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter(__name__)
    meter.create_counter(name="requests", description="Number of requests", unit="1")
    return meter
