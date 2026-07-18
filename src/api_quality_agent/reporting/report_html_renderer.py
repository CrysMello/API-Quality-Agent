from html import escape

from api_quality_agent.reporting.report import Report


def render_report_html(report: Report) -> str:
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="pt-BR"><head><meta charset="utf-8">',
        f"<title>Relatório — {_e(report.collection_name or report.collection_id or '')}</title>",
        "</head><body>",
        "<h1>Relatório de execução</h1>",
        "<ul>",
        f"<li><strong>execution_id:</strong> {_e(report.execution_id)}</li>",
        f"<li><strong>Gerado em:</strong> {_e(report.generated_at.isoformat())}</li>",
        f"<li><strong>Duração (s):</strong> {_e(str(report.duration_seconds))}</li>",
        f"<li><strong>Modo:</strong> {_e(report.mode)}</li>",
        f"<li><strong>Origem:</strong> {_e(report.source)}</li>",
        f"<li><strong>Workspace:</strong> {_e(report.workspace_name or '')} "
        f"({_e(report.workspace_id or '')})</li>",
        f"<li><strong>Collection:</strong> {_e(report.collection_name or '')} "
        f"({_e(report.collection_id or '')})</li>",
        f"<li><strong>Seleção:</strong> {_e(report.selection_origin)}</li>",
        f"<li><strong>Versão do agente:</strong> {_e(report.agent_version)}</li>",
        "</ul>",
        _render_endpoints_section(report),
        _render_warnings_section(report),
        _render_diff_section(report),
        _render_update_section(report),
        _render_execution_section(report),
        _render_artifacts_section(report),
        "</body></html>",
    ]
    return "\n".join(parts)


def _render_endpoints_section(report: Report) -> str:
    if not report.endpoints:
        return "<h2>Endpoints analisados</h2><p>Nenhum endpoint processado.</p>"
    rows = "".join(
        "<tr>"
        f"<td>{_e(endpoint.source)}</td>"
        f"<td>{_e(str(endpoint.succeeded))}</td>"
        f"<td>{_e(str(endpoint.test_count))}</td>"
        f"<td>{_e(str(endpoint.schema_warning_count))}</td>"
        f"<td>{_e(str(endpoint.strategy_warning_count))}</td>"
        f"<td>{_e(endpoint.error or '')}</td>"
        "</tr>"
        for endpoint in report.endpoints
    )
    return (
        "<h2>Endpoints analisados</h2>"
        "<table><thead><tr>"
        "<th>Endpoint</th><th>Sucesso</th><th>Testes</th>"
        "<th>Avisos de schema</th><th>Avisos de estratégia</th><th>Erro</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _render_warnings_section(report: Report) -> str:
    items = "".join(f"<li>{_e(message)}</li>" for message in report.analysis_warnings)
    items += "".join(f"<li>{_e(message)}</li>" for message in report.execution_warnings)
    if not items:
        return "<h2>Avisos</h2><p>Nenhum aviso.</p>"
    return f"<h2>Avisos</h2><ul>{items}</ul>"


def _render_diff_section(report: Report) -> str:
    if not report.diff.entries:
        return "<h2>Diff</h2><p>Nenhuma alteração.</p>"
    rows = "".join(
        "<tr>"
        f"<td>{_e(entry.change_type)}</td>"
        f"<td>{_e(entry.category)}</td>"
        f"<td>{_e(entry.target)}</td>"
        f"<td>{_e(entry.risk)}</td>"
        f"<td>{_e(entry.description)}</td>"
        "</tr>"
        for entry in report.diff.entries
    )
    return (
        "<h2>Diff</h2>"
        "<table><thead><tr>"
        "<th>Tipo</th><th>Categoria</th><th>Alvo</th><th>Risco</th><th>Descrição</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _render_update_section(report: Report) -> str:
    update = report.update
    if not update.attempted:
        return "<h2>Atualização remota</h2><p>Não houve tentativa de atualização.</p>"
    if update.approved is False:
        return (
            "<h2>Atualização remota</h2>"
            f"<p>Negada. Motivo: {_e(update.denial_reason or '')}</p>"
        )
    return (
        "<h2>Atualização remota</h2><ul>"
        f"<li><strong>Aplicada:</strong> {_e(str(update.updated))}</li>"
        f"<li><strong>Dry-run:</strong> {_e(str(update.dry_run))}</li>"
        f"<li><strong>Backup criado:</strong> {_e(str(update.backup_created))}</li>"
        f"<li><strong>document_hash:</strong> {_e(update.document_hash or '')}</li>"
        f"<li><strong>status_code:</strong> {_e(str(update.status_code))}</li>"
        "</ul>"
    )


def _render_execution_section(report: Report) -> str:
    execution = report.execution
    if not execution.executed:
        return "<h2>Execução Newman</h2><p>Newman não foi executado.</p>"

    infra = ""
    if execution.infrastructure_failure is not None:
        infra = (
            "<p><strong>Falha de infraestrutura:</strong> "
            f"{_e(execution.infrastructure_failure.failure_type)} — "
            f"{_e(execution.infrastructure_failure.message)}</p>"
        )

    failures_rows = "".join(
        "<tr>"
        f"<td>{_e(failure.request_name or '')}</td>"
        f"<td>{_e(failure.test_name)}</td>"
        f"<td>{_e(failure.error_message)}</td>"
        "</tr>"
        for failure in execution.test_failures
    )
    failures_table = (
        "<table><thead><tr><th>Request</th><th>Teste</th><th>Mensagem</th></tr></thead>"
        f"<tbody>{failures_rows}</tbody></table>"
        if execution.test_failures
        else "<p>Nenhuma falha de teste.</p>"
    )

    return (
        "<h2>Execução Newman</h2><ul>"
        f"<li><strong>Sucesso:</strong> {_e(str(execution.success))}</li>"
        f"<li><strong>Exit code:</strong> {_e(str(execution.exit_code))}</li>"
        f"<li><strong>Duração (s):</strong> {_e(str(execution.duration_seconds))}</li>"
        f"<li><strong>Requests:</strong> {_e(str(execution.total_requests))}</li>"
        f"<li><strong>Assertions:</strong> {_e(str(execution.total_assertions))}</li>"
        f"<li><strong>Assertions falhas:</strong> {_e(str(execution.failed_assertions))}</li>"
        f"</ul>{infra}{failures_table}"
    )


def _render_artifacts_section(report: Report) -> str:
    if not report.artifacts:
        return "<h2>Artefatos</h2><p>Nenhum artefato gerado.</p>"
    items = "".join(f"<li>{_e(path)}</li>" for path in report.artifacts)
    return f"<h2>Artefatos</h2><ul>{items}</ul>"


def _e(value: str) -> str:
    return escape(value, quote=True)
