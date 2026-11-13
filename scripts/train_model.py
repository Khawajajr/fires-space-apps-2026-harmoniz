"""Deprecated entry point: use `python -m godseye train`."""
import sys

from godseye.cli import main

main(["train", *sys.argv[1:]])
