"""Runner mapping-to-dataclass adapter. No runner implementation imports."""
from . import GameConfig, run_game


class EngineAdapter:
    async def run_game(self, blue_io, red_io, config):
        return await run_game(blue_io, red_io, GameConfig(**config))


def make_engine():
    return EngineAdapter()
