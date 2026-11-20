import logging
import os
import sys

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from opentelemetry import metrics, trace
from opentelemetry.trace import StatusCode
from otel import (
    get_requests_counter,
    setup_otel_instrumentation,
    setup_otel_logging,
    setup_otel_metrics,
    setup_otel_tracing,
    shutdown_telemetry,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("llm-check")


def evaluate_prompt(
    message: str,
    system_prompt: str,
    tracer: trace.Tracer | None = None,
    counter: metrics.Counter | None = None,
) -> str | None:
    t = tracer or trace.get_tracer("llm-check")
    with t.start_as_current_span("evaluate_prompt") as span:
        model = None
        result = {}
        output = None
        model_name = os.getenv("OLLAMA_MODEL", "gemma4")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://host.containers.internal:11434")

        span.set_attribute("gen_ai.request.model", model_name)

        try:
            model = ChatOllama(
                model=model_name,
                base_url=base_url,
                temperature=0,
            )
        except Exception as error:
            log.error(f"No model was created, error: {error}")
            span.record_exception(error)
            span.set_status(StatusCode.ERROR, str(error))
            if counter:
                counter.add(1, {"status": "error", "error_type": "model_init"})
            return None

        if model:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=message),
            ]
            try:
                result = model.invoke(messages)
            except Exception as error:
                log.error(f"No response was given, error: {error}")
                span.record_exception(error)
                span.set_status(StatusCode.ERROR, str(error))
                if counter:
                    counter.add(1, {"status": "error", "error_type": "invoke_failed"})
                return None

            if result and isinstance(result, AIMessage):
                try:
                    output = result.content
                    span.set_status(StatusCode.OK)
                    if counter:
                        counter.add(1, {"status": "success", "model": model_name})
                except AttributeError as error:
                    log.error(f"No AI message was received, error: {error}")
                    span.record_exception(error)
                    span.set_status(StatusCode.ERROR, str(error))
                    if counter:
                        counter.add(1, {"status": "error", "error_type": "attribute_error"})
            else:
                log.error(f"Malformed response was received: {result}")
                span.set_status(StatusCode.ERROR, "Malformed response")
                if counter:
                    counter.add(1, {"status": "error", "error_type": "malformed_response"})

        log.info(output)
        return output


if __name__ == "__main__":
    otel_settings = {
        "service_name": os.getenv("OTEL_SERVICE_NAME", "llm-checker"),
        "host": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT_HOST", "host.containers.internal"),
        "port": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT_PORT", "4317"),
    }

    tracer = setup_otel_tracing(otel_settings)
    setup_otel_logging(otel_settings)
    meter = setup_otel_metrics(otel_settings)
    setup_otel_instrumentation()

    counter = get_requests_counter()

    if len(sys.argv) < 2:
        log.error("No filename provided as argument")
        sys.exit(1)

    filename = sys.argv[1]

    # Resolve base prompt path relative to this script directory first
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_path = os.path.join(script_dir, "base_prompt.md")
    prompt_file = candidate_path if os.path.isfile(candidate_path) else "./base_prompt.md"

    try:
        with open(prompt_file) as b:
            base_prompt = b.read()
    except OSError as error:
        log.error(f"Could not read base prompt, error: {error}")
        base_prompt = "You are a useful expert"

    system_prompt = base_prompt
    try:
        with open(filename) as f:
            content = f.read()

        if content:
            message = (
                f"for the file {filename}, perform a spellcheck and validate its grammar on its content:\n"
                f"=START=\n{content}\n=END="
            )
            with tracer.start_as_current_span(
                "evaluate_file", attributes={"file.path": filename, "file.size": len(content)}
            ):
                response = evaluate_prompt(
                    message=message,
                    system_prompt=system_prompt,
                    tracer=tracer,
                    counter=counter,
                )
                if response:
                    print(response)
    except IOError:
        log.error(f"File {filename} could not be read")
    finally:
        shutdown_telemetry()
