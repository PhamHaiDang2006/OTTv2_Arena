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


def series(first, second, games, replay):
    """Play `games` games, the first bot BLUE in odd games and RED in even ones; return wins per bot."""
    commands = [bot_command(first), bot_command(second)]
    wins = [0, 0]
    for game in range(games):
        swapped = game % 2 == 1
        ordered = commands[::-1] if swapped else commands
        result = asyncio.run(play(*ordered, default_config(game + 1)))
        path = Path(replay)
        if games > 1:
            path = path.with_name(f"{path.stem}-{game + 1}{path.suffix}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        wins[(result.winner == "RED") != swapped] += 1
        print(f"{game + 1}: {result.winner} {result.reason} plies={result.plies} replay={path}")
    print(f"Total: {first} {wins[0]} - {wins[1]} {second}")
    return wins


def main():
    parser = argparse.ArgumentParser(description="Local trusted-bot matches, development rules dev-v1")
    sub = parser.add_subparsers(dest="command", required=True)
    play_parser = sub.add_parser("play", help="Two bots, colours alternating each game")
    play_parser.add_argument("blue", help="Bot directory or entry file, or a sample bot: random, greedy")
    play_parser.add_argument("red", help="Bot directory or entry file, or a sample bot: random, greedy")
    play_parser.add_argument("--replay", default="replay.json")
    play_parser.add_argument("--games", type=int, default=1)
    practice_parser = sub.add_parser("practice", help="Your bot against a sample bot or another local bot")
    practice_parser.add_argument("bot", help="Your bot directory or entry file")
    practice_parser.add_argument("--vs", default="greedy", help="random, greedy or another bot path (default greedy)")
    practice_parser.add_argument("--replay", default="practice/replay.json")
    practice_parser.add_argument("--games", type=int, default=10)
    args = parser.parse_args()
    if args.games < 1:
        parser.error("--games must be positive")
    if args.command == "play":
        series(args.blue, args.red, args.games, args.replay)
    else:
        series(args.bot, args.vs, args.games, args.replay)


if __name__ == "__main__":
    main()
