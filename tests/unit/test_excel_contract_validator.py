import openpyxl

from api_quality_agent.parsers import ExcelContractParser, ExcelContractValidator

_HEADER_ROW = ["Sequencial", "Nome do campo", "Formato", "Tamanho", "Obrigatoriedade", "Regras (Domínio)"]


def _build_workbook(tmp_path, *, sheets: dict[str, list[list[object]]]):
    workbook = openpyxl.Workbook()
    default_sheet = workbook.active
    first = True
    for title, rows in sheets.items():
        sheet = default_sheet if first else workbook.create_sheet()
        sheet.title = title
        for row in rows:
            sheet.append(row)
        first = False
    path = tmp_path / "contrato.xlsx"
    workbook.save(path)
    return path


def _parse(tmp_path, rows, sheet_title="Planilha1"):
    path = _build_workbook(tmp_path, sheets={sheet_title: rows})
    return ExcelContractParser().parse(path)


def test_valid_contract_produces_no_issues(tmp_path):
    rows = [
        ["URI", "/teste/v1/ok"],
        ["Método", "GET"],
        ["Resposta caso HTTP Status code 200 - OK"],
        _HEADER_ROW,
        ["1", "dado", "Objeto", None, "SIM"],
        ["1.1", "id", "Alfanumerico", 10, "SIM"],
    ]
    result = _parse(tmp_path, rows)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert issues == ()


def test_unknown_type_is_an_error(tmp_path):
    rows = [
        ["URI", "/teste/v1/tipo-invalido"],
        ["Método", "GET"],
        ["Requisição(Body)"],
        _HEADER_ROW,
        [1, "campo", "TipoInexistente", 10, "SIM"],
    ]
    result = _parse(tmp_path, rows)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert any(issue.severity == "error" and issue.field == "Formato" for issue in issues)


def test_invalid_sequencial_is_an_error(tmp_path):
    rows = [
        ["URI", "/teste/v1/sequencial-invalido"],
        ["Método", "GET"],
        ["Requisição(Body)"],
        _HEADER_ROW,
        ["abc", "campo", "Alfanumerico", 10, "SIM"],
    ]
    result = _parse(tmp_path, rows)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert any(
        issue.severity == "error" and issue.field == "Sequencial" and "inválido" in issue.message
        for issue in issues
    )


def test_duplicate_sequencial_is_an_error(tmp_path):
    rows = [
        ["URI", "/teste/v1/sequencial-duplicado"],
        ["Método", "GET"],
        ["Requisição(Body)"],
        _HEADER_ROW,
        [1, "campoA", "Alfanumerico", 10, "SIM"],
        [1, "campoB", "Alfanumerico", 10, "SIM"],
    ]
    result = _parse(tmp_path, rows)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert any(issue.severity == "error" and "duplicado" in issue.message for issue in issues)


def test_orphan_child_is_an_error(tmp_path):
    rows = [
        ["URI", "/teste/v1/orfao"],
        ["Método", "GET"],
        ["Resposta caso HTTP Status code 200 - OK"],
        _HEADER_ROW,
        ["1.1", "campoOrfao", "Alfanumerico", 10, "SIM"],
    ]
    result = _parse(tmp_path, rows)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert any(issue.severity == "error" and "Pai não encontrado" in issue.message for issue in issues)


def test_array_without_children_is_a_warning(tmp_path):
    rows = [
        ["URI", "/teste/v1/array-vazio"],
        ["Método", "GET"],
        ["Resposta caso HTTP Status code 200 - OK"],
        _HEADER_ROW,
        ["1", "itens", "ArrayList", 5, "SIM"],
    ]
    result = _parse(tmp_path, rows)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert any(issue.severity == "warning" and "não tem nenhum filho" in issue.message for issue in issues)


def test_non_required_path_param_is_a_warning(tmp_path):
    rows = [
        ["URI", "/teste/v1/{origem}"],
        ["Método", "GET"],
        ["Requisição (Path Param)"],
        _HEADER_ROW,
        [1, "origem", "Alfanumerico", 40, "NÃO"],
    ]
    result = _parse(tmp_path, rows)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert any(issue.severity == "warning" and issue.field == "Obrigatoriedade" for issue in issues)


def test_other_status_sections_are_recognized_as_warnings(tmp_path):
    rows = [
        ["URI", "/teste/v1/status"],
        ["Método", "GET"],
        ["Resposta caso HTTP Status code 200 - OK"],
        _HEADER_ROW,
        ["1", "dado", "Alfanumerico", 10, "SIM"],
        ["Resposta caso HTTP Status code 400 - ERRO"],
        _HEADER_ROW,
        ["1", "erro", "Alfanumerico", 10, "SIM"],
    ]
    result = _parse(tmp_path, rows)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert any(
        issue.severity == "warning" and issue.section == "response_400" and "ignorada" in issue.message
        for issue in issues
    )


def test_duplicate_endpoint_across_sheets_is_an_error(tmp_path):
    shared_rows = [
        ["URI", "/teste/v1/duplicado"],
        ["Método", "GET"],
        ["Requisição(Body)"],
        _HEADER_ROW,
    ]
    path = _build_workbook(tmp_path, sheets={"Planilha1": shared_rows, "Planilha2": shared_rows})
    result = ExcelContractParser().parse(path)

    issues = ExcelContractValidator().validate(result.raw_rows, result.catalog)

    assert any(
        issue.severity == "error" and "Endpoint duplicado" in issue.message for issue in issues
    )


def test_validator_never_receives_or_needs_a_collection(tmp_path):
    # Garantia de escopo: o validador não conhece/importa nenhum tipo de
    # Collection Postman — sua assinatura só aceita raw_rows + catalog.
    import inspect

    signature = inspect.signature(ExcelContractValidator.validate)
    for name in signature.parameters:
        assert "collection" not in name.lower()
