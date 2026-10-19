"""Compatibility wrapper: python starter-kits/tools/local_runner.py bot_a bot_b --games 10."""
import sys
from ottv2.cli import main

sys.argv.insert(1, "play")
main()
