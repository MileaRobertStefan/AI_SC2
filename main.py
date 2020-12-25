from all_imports_packages import *
from all_imports_ai import *


class Humanoid(sc2.BotAI):
    async def on_step(self, iteration: int):
        pass


def test_game(AI, race, map, realtime=False):
    run_game(maps.get(map), [
        # Bot(Race.Terran, Humanoid()),
        Bot(race, AI),
        Computer(Race.Terran, Difficulty.VeryHard)
    ], realtime=realtime)


if __name__ == "__main__":
    test_game(ZergAI(), Race.Zerg, "TritonLE")
    # test_game(SentdeBot(), Race.Protoss, MAP_NAME, realtime=False)

