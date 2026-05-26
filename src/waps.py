# waps.py
# Copyright Matt Rienzo (C) 2026
# Make live changes to AP configuration in Meraki
#
# MIT License
#

import csv
import sys
import meraki
import argparse
import namespace
import traceback

from pprint import pprint

# Type hints to show reader intended use of variable
mutable_bool = bool
immutable_str = str

# Global vars for main logics
VERBOSE_MODE: mutable_bool = False
DEBUG_MODE: mutable_bool = False
EVAL_MODE: dict = {False}
EVAL_CLAIM: str = 'claim'
EVAL_SANITY: str = 'sanity'
EVAL_ADD: str = 'add'
EVAL_UPDATE: str = 'update'

##########################################
### Module versioning for my convention###
##########################################
class _MODULE__waps():
    _Version: immutable_str = "0.1.0-alpha"
    _VersionNum: immutable_str = "0.1.0.0"
    _VersionTuple = (0, 1, 0, 0)
    _CopyrightHeader: immutable_str = """

    Copyright Matt Rienzo (C) 2026
    Make live changes to AP configuration in Meraki
    
    MIT License

    """

    @classmethod
    def Version(cls) -> str:
        return cls._Version
    
    @classmethod
    def VersionNum(cls) -> str:
        return cls._VersionNum
    
    @classmethod
    def VersionTuple(cls) -> tuple[int, int, int, int]:
        return cls._VersionTuple
    
    @classmethod
    def Copyright(cls) -> str:
        return cls._CopyrightHeader


def checkArgs(parser: argparse) -> None:
    """
    Verify command line arguments that require companion options, and handle
    one-offs.
    """
    print(
        f"[D] checkArgs() - parser.debug = {parser.debug}\n"
        f"[D] checkArgs() - parser.verbose = {parser.verbose}\n"
        f"[D] checkArgs() - parser.printVersion = {parser.printVersion}\n"
        f"[D] checkArgs() - parser.claim = {parser.claim}\n"
        f"[D] checkArgs() - parser.add = {parser.add}\n"
        f"[D] checkArgs() - parser.update = {parser.update}\n"
        f"[D] checkArgs() - parser.sourceCSV = {parser.sourceCSV}\n"
        f"[D] checkArgs() - parser.token = {parser.token}\n"
    ) if DEBUG_MODE else next

    global EVAL_MODE
    one_arg = 2
    two_args = 3

    presence = {
        "debug": True if parser.debug else False,
        "verbose": True if parser.verbose else False,
        "version": True if parser.printVersion else False,
        "claim": True if parser.claim else False,
        "add": True if parser.add else False,
        "update": True if parser.update else False,
        "source": True if parser.sourceCSV else False,
        "token": True if parser.token else False
    }

    if presence['token'] and len(sys.argv) == one_arg:
        print("--token: requires more arguments")
        parser.parse_args(['--help']) 

    if presence['source'] and len(sys.argv) == one_arg:
        EVAL_MODE = {EVAL_SANITY}

    if ( 
        presence['source'] and 
        presence['claim'] and
        len(sys.argv) == two_args
    ):
        EVAL_MODE = {EVAL_CLAIM}

    if ( 
        presence['source'] and 
        presence['add'] and
        len(sys.argv) == two_args
    ):
        EVAL_MODE = {EVAL_ADD}

    if ( 
        presence['source'] and 
        presence['update'] and
        len(sys.argv) == two_args
    ):
        EVAL_MODE = {EVAL_UPDATE}

    if presence['claim'] and not presence['source']:
        print('--claim: requires --source and maybe --token')
        parser.parse_args(['--help']) 
    
    if presence['add'] and not presence['source']:
        print('--add: requires --source and maybe --token')
        parser.parse_args(['--help']) 
    
    if presence['update'] and not presence['source']:
        print('--update: requires --source and maybe --token')
        parser.parse_args(['--help']) 
    
def printVersion() -> None:
    """
    Print version and copyright
    """
    print(f"Script waps.py version {_MODULE__waps.Version()}")
    print(_MODULE__waps.Copyright())

    sys.exit(0)

def parseARGV() -> namespace:
    """
    Handle CLI arguments
    """ 
    parser = argparse.ArgumentParser()
    
    tokenArgs = ('-t', '--token')
    tokenOpts = {
        "help": 'API Token to use with Meraki',
        "type": str,
        "dest": 'token',
        "required": True
    }

    claimArgs = ('-c', '--claim')
    claimOpts = {
        "help": 'Claim APs listed without adding to networks',
        "dest": 'claim',
        "action": 'store_true'
    }

    addArgs = ('-a', '--add')
    addOpts = {
        "help": 'Claim and add new APs to networks',
        "dest": 'add',
        "action": "store_true"
    }

    updateArgs = ('-u', '--update')
    updateOpts = {
        "help": 'Update APs without claiming new APs',
        "dest": 'update',
        "action": "store_true"
    }

    sourceArgs = ('-s', '--source')
    sourceOpts = {
        "help": 'CSV file to base operations on',
        "dest": 'sourceCSV',
        "type": str
    }

    versionArgs = ('-v', '--version')
    versionOpts = {
        "help": 'Show version',
        "dest": 'printVersion',
        "action": 'store_true'
    }

    verboseArgs = ('-V', '--verbose')
    verboseOpts = {
        "help": "Run with verbose logging",
        "dest": 'verbose',
        "action": 'store_true'
    }

    debugArgs = ('-D', '--debug')
    debugOpts = {
        "help": "Run with debug logging",
        "dest": 'debug',
        "action": 'store_true'
    }

    parser.add_argument(*debugArgs, **debugOpts)
    parser.add_argument(*verboseArgs, **verboseOpts)
    parser.add_argument(*versionArgs, **versionOpts)
    parser.add_argument(*claimArgs, **claimOpts)
    parser.add_argument(*addArgs, **addOpts)
    parser.add_argument(*updateArgs, **updateOpts)
    parser.add_argument(*sourceArgs, **sourceOpts)
    parser.add_argument(*tokenArgs, **tokenOpts)
    
    return parser.parse_args(args=None if sys.argv[1:] else ['--help'])

def main() -> None:
    """
    Application logic steps:
        1) Parse command line arguments
        2) Parse CSV into arrays of dicts
        3) Make API requests based on CSV
    """
    argv: argparse = parseARGV()

    global VERBOSE_MODE, DEBUG_MODE
    VERBOSE_MODE = True if argv.debug else argv.verbose
    DEBUG_MODE = True if argv.debug else False

    checkArgs(argv)



if __name__ == "__main__":
    main()