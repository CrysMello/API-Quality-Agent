from api_quality_agent.generators.generated_test_script import GeneratedTestScript


def format_test_script_preview(generated: GeneratedTestScript, *, request_label: str) -> str:
    lines = [
        f"Request: {request_label}",
        "",
        f"Testes que serão gerados: {generated.test_count}",
        "",
    ]
    for index, item in enumerate(generated.summary, start=1):
        lines.append(f"{index}. {item.title}")
        lines.append(f"   {item.description}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
