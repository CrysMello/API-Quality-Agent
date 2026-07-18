import argparse

from api_quality_agent.application.use_cases import get_effective_configuration


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    config_parser = subparsers.add_parser("config", help="Gerencia a configuração do agente.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    show_parser = config_subparsers.add_parser(
        "show", help="Exibe a configuração efetiva (sem segredos)."
    )
    show_parser.set_defaults(handler=_handle_show)


def _handle_show(_args: argparse.Namespace) -> int:
    configuration = get_effective_configuration()
    print(f"Versão do pacote: {configuration.package_version}")
    print(f"Diretório de trabalho: {configuration.working_directory}")
    if configuration.postman_api_key_configured:
        print(f"POSTMAN_API_KEY: configurada ({configuration.postman_api_key_masked})")
    else:
        print("POSTMAN_API_KEY: não configurada")
    return 0
