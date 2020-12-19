import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer

from sc2.constants import NEXUS, PROBE, PYLON

class SentdeBot(sc2.BotAI):
    async def on_step(self, iteration):
        # what to do every step
        await self.distribute_workers()  # in sc2/bot_ai.py
        await self.build_workers()  # workers bc obviously
        await self.build_pylons()  # pylons are protoss supply buildings
        await self.expand()

    async def build_workers(self):
        # nexus = command center
        for nexus in self.units(NEXUS).ready.noqueue:
            # we want at least 20 workers, otherwise let's allocate 70% of our supply to workers.
            # later we should use some sort of regression algo maybe for this?

            if self.can_afford(PROBE):
                await self.do(nexus.train(PROBE))

    async def build_pylons(self):
        if self.supply_left < 5 and not self.already_pending(PYLON):
            nexuses = self.units(NEXUS).ready
            if nexuses.exists:
                if self.can_afford(PYLON):
                    await self.build(PYLON, near=nexuses.first)

    async def expand(self):
        if self.units(NEXUS).amount < 2 and self.can_afford(NEXUS):
            await self.expand_now()


run_game(maps.get("AcropolisLE"), [
    Bot(Race.Protoss, SentdeBot()),
    Computer(Race.Terran, Difficulty.Easy)
], realtime=True)