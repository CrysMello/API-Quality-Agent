from api_quality_agent.reporting.report import Report


def render_report_summary(report: Report) -> str:
    lines = [
        f"Execução {report.execution_id} ({report.mode}, origem: {report.source})",
        f"Workspace: {report.workspace_name or report.workspace_id or '<nenhum>'}",
        f"Collection: {report.collection_name or report.collection_id or '<nenhuma>'} "
        f"[{report.selection_origin}]",
        f"Gerado em {report.generated_at.isoformat()} "
        f"(duração: {report.duration_seconds:.2f}s)",
        "",
        f"Endpoints analisados: {len(report.endpoints)}",
    ]
    failed_endpoints = [endpoint for endpoint in report.endpoints if not endpoint.succeeded]
    if failed_endpoints:
        lines.append(f"  Com falha: {len(failed_endpoints)}")
    total_tests = sum(endpoint.test_count for endpoint in report.endpoints)
    lines.append(f"Testes gerados: {total_tests}")

    warning_count = len(report.analysis_warnings) + len(report.execution_warnings)
    lines.append(f"Avisos: {warning_count}")

    lines.append(
        f"Diff: {len(report.diff.entries)} alteração(ões)"
        f"{' (com remoções)' if report.diff.has_removals else ''}"
    )

    if not report.update.attempted:
        lines.append("Atualização remota: não tentada")
    elif report.update.approved is False:
        lines.append(f"Atualização remota: negada ({report.update.denial_reason})")
    else:
        lines.append(f"Atualização remota: aplicada={report.update.updated}")

    if not report.execution.executed:
        lines.append("Execução Newman: não executada")
    elif report.execution.infrastructure_failure is not None:
        lines.append(
            "Execução Newman: falha de infraestrutura "
            f"({report.execution.infrastructure_failure.failure_type})"
        )
    else:
        lines.append(
            "Execução Newman: "
            f"{'sucesso' if report.execution.success else 'com falhas'} "
            f"({report.execution.failed_assertions}/{report.execution.total_assertions} "
            "assertions falhas)"
        )

    lines.append(f"Artefatos gerados: {len(report.artifacts)}")
    lines.append(f"Versão do agente: {report.agent_version}")
    return "\n".join(lines)
