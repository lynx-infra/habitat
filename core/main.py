# Copyright 2024 TikTok Pte. Ltd. All rights reserved.
# Licensed under the Apache License Version 2.0 that can be found in the
# LICENSE file in the root directory of this source tree.

import asyncio
import copy
import logging
import platform
import sys
from argparse import ArgumentParser

import coloredlogs

from core import commands
from core.__version__ import __version__
from core.commands.command import Command
from core.settings import DEBUG
from core.utils import find_classes, print_all_exception

coloredlogs.install(logging.DEBUG if DEBUG else logging.INFO)


def load_commands(argument_parser: ArgumentParser, command_classes):
    sub_parsers = argument_parser.add_subparsers(title=argument_parser.prog.__str__())
    for c in command_classes:
        logging.debug(f'register command {c}')
        parser = sub_parsers.add_parser(c.name, help=c.help)

        for arg in c.args + copy.deepcopy(c.__base__.args):
            kw_args = {k: v for k, v in arg.items() if k != 'flags'}
            parser.add_argument(*arg.get('flags'), **kw_args)
        parser.set_defaults(command=c())
        if c.subcommands:
            load_commands(parser, c.subcommands)


def main():
    parser = ArgumentParser("hab")
    parser.add_argument('--debug', help='Show more detail in output', action='store_true', default=False)
    parser.add_argument(
        '-v', '--version', action='version', version=__version__
    )

    logging.info(f'Using habitat version {__version__}')

    def is_command(cls):
        return issubclass(cls, Command) and cls != Command

    command_classes = find_classes(commands, is_command, recursive=False)
    load_commands(parser, command_classes)

    args = parser.parse_args()
    if args.debug:
        coloredlogs.install(logging.DEBUG)

    if not hasattr(args, 'command'):
        parser.print_help()
        return 1
    else:
        try:
            if platform.system() == "Windows":
                # Working around "Asyncio Event Loop is Closed" on Windows
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

            asyncio.run(args.command.run_command(args))
        except Exception as e:
            if DEBUG:
                raise e
            else:
                print_all_exception(e)
                sys.exit(1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
