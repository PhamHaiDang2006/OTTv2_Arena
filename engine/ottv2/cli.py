import argparse
import asyncio
import json
from pathlib import Path

from . import GameConfig, INITIAL_FEN, run_game
from .local import ProcessBot, bot_command


def default_config(seed=1):
    return GameConfig(engine_version="1.0.0", ruleset_id="dev-v1", map_id="standard", initial_fen=INITIAL_FEN,
                      players={"BLUE": {"team": "local-blue", "submission_id": "00000001-0000-4000-8000-000000000001"},
                               "RED": {"team": "local-red", "submission_id": "00000002-0000-4000-8000-000000000001"}}, seed=seed)


async def play(blue_command, red_command, config):
    bots = []
    try:
        for command in (blue_command, red_command):
            bots.append(await ProcessBot.start(command))
        return await run_game(*bots, config)
    finally:
        await asyncio.gather(*(bot.close() for bot in bots))


def main():
    parser = argparse.ArgumentParser(description="Local trusted-bot matches, development rules dev-v1")
    sub = parser.add_subparsers(dest="command", required=True)
    play_parser = sub.add_parser("play")
    play_parser.add_argument("blue")
    play_parser.add_argument("red")
    play_parser.add_argument("--replay", default="replay.json")
    play_parser.add_argument("--games", type=int, default=1)
    args = parser.parse_args()
    if args.games < 1:
        parser.error("--games must be positive")
    commands = [bot_command(args.blue), bot_command(args.red)]
    for game in range(args.games):
        ordered = commands if game % 2 == 0 else commands[::-1]
        result = asyncio.run(play(*ordered, default_config(game + 1)))
        path = Path(args.replay)
        if args.games > 1:
            path = path.with_name(f"{path.stem}-{game + 1}{path.suffix}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{game + 1}: {result.winner} {result.reason} plies={result.plies} replay={path}")


if __name__ == "__main__":
    main()
