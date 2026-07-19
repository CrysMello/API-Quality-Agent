"""Helpers de confirmação/cancelamento compartilhados pelos comandos
interativos da CLI (generate, update, workspace select).

Centralizados aqui para que Ctrl+C/EOF em QUALQUER prompt — seleção ou
confirmação final — sempre resulte em cancelamento limpo (OperationCancelled,
nunca uma exceção não tratada escapando para o "Erro inesperado" genérico
de cli.main._dispatch).
"""

_CONFIRM_VALUES = frozenset({"s", "sim", "y", "yes"})
_CANCEL_VALUES = frozenset({"n", "nao", "não", "no"})


class OperationCancelled(Exception):
    pass


def read_line(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        raise OperationCancelled() from None


def confirm(prompt: str = "Deseja continuar? [S/n]: ", *, default: bool = True) -> bool:
    # default=True (padrão afirmativo, "[S/n]"): usado por generate/workspace
    # select, onde Enter vazio confirma — convenção já estabelecida no projeto.
    # default=False (padrão negativo, "[s/N]"): usado por update, por ser uma
    # operação que grava remotamente — Enter vazio cancela com segurança.
    raw = read_line(prompt)
    answer = raw.strip().lower()
    if not answer:
        return default
    if answer in _CANCEL_VALUES:
        return False
    if answer in _CONFIRM_VALUES:
        return True
    # Entrada não reconhecida: por segurança, nunca prossegue com uma
    # atualização/geração sem confirmação inequívoca.
    print("Entrada não reconhecida.")
    return False
