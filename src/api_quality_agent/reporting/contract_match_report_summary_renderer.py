from api_quality_agent.reporting.contract_match_report import ContractMatchReport


def render_contract_match_report_summary(report: ContractMatchReport) -> str:
    lines = [
        f"Contrato: {report.source_file}",
        f"Endpoints declarados: {report.summary.total}",
        f"Correspondências: {report.summary.matched}",
        f"Não encontrados: {report.summary.not_found}",
        f"Ambíguos: {report.summary.ambiguous}",
    ]
    return "\n".join(lines)
