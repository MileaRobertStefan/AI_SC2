from all_imports_packages import *
from all_imports_ai import *


def test_game(AI, race, map, realtime=False):
    run_game(maps.get(map), [
        Bot(race, AI),
        Computer(Race.Terran, Difficulty.Hard)
    ], realtime=realtime)


if __name__ == "__main__":
    test_game(ZergAI(), Race.Zerg, MAP_NAME)
    # test_game(SentdeBot(), Race.Protoss, MAP_NAME, realtime=False)

