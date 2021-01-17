from all_imports_packages import *

class Builder :
    def __init__(self,ai):
        self.ai = ai
        
        self.first_expansion_done = False
        self.save_for_first_expansion = False
        self.save_for_spawning_pool = False

        self.priorities = {
            DRONE: 0,
            "ARMY": 0,
            SPAWNINGPOOL: 0,
            ROACHWARREN: 0,
            BANELINGNEST: 0,
            "EXPAND": 0,
            OVERLORD: 0,
            QUEEN: 0,
            EVOLUTIONCHAMBER: 0,
            LAIR: 0,
            HYDRALISKDEN: 0,
            "UPGRADES": 0,
            LURKERDENMP: 0,
            SPIRE: 0,
            NYDUSNETWORK: 0,
            HIVE: 0,
            ULTRALISKCAVERN: 0,
            GREATERSPIRE: 0,
        }

        self.resource_ratio = 2  # Minerals / Gas

    async def build_buildings(self):
        # Essentials
        await self.build_extractors()
        await self.build_building(SPAWNINGPOOL, self.ai.own_bases_ready[0])

        await self.build_early_game()
        await self.build_mid_game()
        await self.build_late_game()


    async def build_early_game(self):
        if self.ai.army.FREQUENCES[ZERGLING] and self.ai.army.FREQUENCES[BANELING]:
            await self.build_building(BANELINGNEST, self.ai.own_bases_ready[0], start_time=int(3.5 * 60))

        if self.ai.army.FREQUENCES[ROACH]:
            await self.build_building(ROACHWARREN, self.ai.own_bases_ready[0])
            await self.ai.all_upgrades(ROACHWARREN)

        await self.build_building(EVOLUTIONCHAMBER, self.ai.own_bases_ready[0], required_amount=self.ai.era)
        if self.ai.time < 8 * 60:
            await self.ai.all_upgrades(EVOLUTIONCHAMBER, exception_id_list=[RESEARCH_ZERGMELEEWEAPONSLEVEL1])
        else:
            await self.ai.all_upgrades(EVOLUTIONCHAMBER)

        await self.ai.upgrade(self.ai.own_bases_ready[0], RESEARCH_BURROW, time=4 * 60)

    async def build_mid_game(self):
        await self.build_building(LAIR, self.ai.own_bases_ready[0])

        if self.ai.army.FREQUENCES[HYDRALISK]:
            await self.build_building(HYDRALISKDEN, self.ai.own_bases_ready[0])
            await self.ai.all_upgrades(HYDRALISKDEN)

        if self.ai.army.FREQUENCES[HYDRALISK] and self.ai.army.FREQUENCES[LURKERMP]:
            await self.build_building(LURKERDENMP, self.ai.own_bases_ready[0])
            await self.ai.all_upgrades(LURKERDENMP)

        # if self.ai.army.FREQUENCES[INFESTOR] or self.ai.army.FREQUENCES[SWARMHOSTMP]:
        await self.build_building(INFESTATIONPIT, self.ai.own_bases_ready[0])

        if self.ai.army.FREQUENCES[MUTALISK] or self.ai.army.FREQUENCES[CORRUPTOR]:
            await self.build_building(SPIRE, self.ai.own_bases_ready[0], required_amount=2)
            await self.ai.all_upgrades(SPIRE)

    async def build_late_game(self):
        await self.build_building(HIVE, self.ai.own_bases_ready[0])

        if self.ai.army.FREQUENCES[CORRUPTOR] and self.ai.army.FREQUENCES[BROODLORD]:
            await self.build_building(GREATERSPIRE, self.ai.own_bases_ready[0])
            await self.ai.all_upgrades(GREATERSPIRE)

        if self.ai.army.FREQUENCES[ULTRALISK]:
            await self.build_building(ULTRALISKCAVERN, self.ai.own_bases_ready[0])
            await self.ai.all_upgrades(ULTRALISKCAVERN)
    
    async def build_building(self, building_id, chosen_base, required_amount=1, start_time=0):
        if not self.ai.get_priority(building_id):
            return

        if not (self.ai.already_pending(HATCHERY) or self.ai.nr_bases >= 2):
            return

        if self.ai.time < start_time:
            return

        if building_id == ROACHWARREN and self.ai.structures(SPAWNINGPOOL).ready.amount < 1:
            return

        if building_id == BANELINGNEST and self.ai.structures(SPAWNINGPOOL).ready.amount < 1:
            return

        if building_id == LAIR and self.ai.structures(HATCHERY).ready.amount < 1:
            return

        if building_id == LAIR and self.ai.structures(HIVE).amount >= 1:
            return

        if building_id == HYDRALISKDEN and self.ai.structures(LAIR).ready.amount + self.ai.structures(HIVE).amount < 1:
            return

        if building_id == INFESTATIONPIT and self.ai.structures(LAIR).ready.amount + self.ai.structures(HIVE).amount < 1:
            return

        if building_id == LURKERDENMP and self.ai.structures(LAIR).ready.amount + self.ai.structures(HIVE).amount < 1:
            return

        if building_id == LURKERDENMP and self.ai.structures(HYDRALISKDEN).ready.amount < 1:
            return

        if building_id == SPIRE and self.ai.structures(LAIR).ready.amount + self.ai.structures(HIVE).amount < 1:
            return

        if building_id == SPIRE and self.ai.structures(GREATERSPIRE).amount + self.ai.structures(
                SPIRE).amount >= required_amount:
            return

        if building_id == HIVE and self.ai.structures(LAIR).ready.amount < 1:
            return

        if building_id == GREATERSPIRE and self.ai.structures(HIVE).ready.amount < 1:
            return

        if building_id == GREATERSPIRE and self.ai.structures(SPIRE).ready.amount < 1:
            return

        if building_id == ULTRALISKCAVERN and self.ai.structures(HIVE).ready.amount < 1:
            return

        if self.ai.can_afford(building_id) and self.ai.already_pending(building_id) \
                + self.ai.structures(building_id).filter(
            lambda structure: structure.type_id == building_id and structure.is_ready
        ).amount < required_amount:
            map_center = self.ai.game_info.map_center
            position_towards_map_center = chosen_base.position.towards(map_center, distance=5)

            if building_id == LAIR:
                await self.ai.evolve_units(HATCHERY, LAIR)
            elif building_id == HIVE:
                await self.ai.evolve_units(LAIR, HIVE)
            elif building_id == GREATERSPIRE:
                await self.ai.evolve_units(SPIRE, GREATERSPIRE)
            else:
                await self.ai.build(building_id, near=position_towards_map_center, placement_step=1)

    async def build_extractors(self):
        if len(self.ai.structures(SPAWNINGPOOL)) == 0:
            return

        for hatchery in self.ai.own_bases:
            drones = self.ai.units(DRONE)
            if len(drones) == 0:
                continue

            if self.ai.units(DRONE).closer_than(7, hatchery).amount < 8 and self.ai.time < 6 * 60:
                continue

            vespenes = self.ai.vespene_geyser.closer_than(10.0, hatchery)

            for vespene in vespenes:
                if not self.ai.can_afford(EXTRACTOR):
                    break

                if self.ai.structures(EXTRACTOR).closer_than(1.0, vespene).amount:
                    break

                if self.ai.already_pending(EXTRACTOR) >= 2:
                    break

                worker = self.ai.select_build_worker(vespene.position)
                if worker is None:
                    break

                worker.build_gas(vespene)
            


    pass

