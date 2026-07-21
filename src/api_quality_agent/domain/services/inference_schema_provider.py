import json

from api_quality_agent.domain.models import CollectionRequest, SchemaResolution
from api_quality_agent.domain.services.schema_inference_engine import SchemaInferenceEngine

# R2-05: InferenceSchemaProvider — implementação de SchemaProvider que
# replica o comportamento já existente hoje dentro do AgentOrchestrator
# (_infer_response_schema): infere o schema a partir dos Examples salvos na
# request. Duplica temporariamente essa lógica de "colagem" (extrair e
# desserializar os exemplos) — o AgentOrchestrator ainda não foi alterado
# pra usar esta classe (R2-05 é só a criação do provider; a substituição
# fica pra uma etapa posterior).


class InferenceSchemaProvider:
    def __init__(self, schema_inference_engine: SchemaInferenceEngine) -> None:
        self._schema_inference_engine = schema_inference_engine

    def resolve(self, request: CollectionRequest) -> SchemaResolution:
        parsed_examples = []
        for example in request.examples:
            if not example.body:
                continue
            try:
                parsed_examples.append(json.loads(example.body))
            except json.JSONDecodeError:
                continue

        if not parsed_examples:
            return SchemaResolution(schema=None)

        result = self._schema_inference_engine.infer(parsed_examples)
        return SchemaResolution(schema=result.schema, warnings=result.warnings)
