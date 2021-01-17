from all_imports_packages import *
from all_imports_ai import *

from Zerg.Zagara.zagara_ai import ZagaraAI


class Humanoid(sc2.BotAI):
    async def on_step(self, iteration: int):
        pass


# Difficulties:
#   VeryEasy
#   Easy
#   Medium
#   MediumHard
#   Hard
#   Harder
#   VeryHard
#   CheatVision
#   CheatMoney
#   CheatInsane


def test_game(AI, race, map, realtime=False):
    enemy_race = Race.Protoss
    difficulty = Difficulty.VeryHard

    replay_name = str(race)[str(race).rfind(".")+1] + "v" + str(enemy_race)[str(enemy_race).rfind(".")+1]

    current_directory = os.getcwd() + "\\Replays\\"

    with open(current_directory + "Matches.cnt", "r") as file:
        cnt = int(file.readline())

    replay_name = current_directory + "\\M" + str(cnt) + " " + replay_name + \
                  " " + str(difficulty)[str(difficulty).rfind(".")+1:]

    result = run_game(
        maps.get(map), [
            # Bot(Race.Zerg, Humanoid()),
            Bot(race, AI),
            Computer(enemy_race, difficulty)
        ],
        realtime=realtime,
        save_replay_as=replay_name
    )

    termination = " " + str(result)[str(result).rfind(".")+1:] + ".Sc2Replay"
    os.rename(replay_name, replay_name + termination)
    replay_name += termination
    shutil.copyfile(replay_name, current_directory + "Last Replay.Sc2Replay")

    with open(current_directory + "Matches.cnt", "w") as file:
        file.write(str(cnt+1))


if __name__ == "__main__":
    test_game(ZagaraAI(), Race.Zerg, "TritonLE")
