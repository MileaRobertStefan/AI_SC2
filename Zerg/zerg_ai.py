from all_imports_packages import *


class ZergAI(sc2.BotAI):
    async def on_step(self, iteration):
        await self.distribute_workers()