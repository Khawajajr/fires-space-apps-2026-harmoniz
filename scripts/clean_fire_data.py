"""Deprecated entry point: use `python -m godseye clean`."""
import sys

from godseye.cli import main

main(["clean", *sys.argv[1:]])
