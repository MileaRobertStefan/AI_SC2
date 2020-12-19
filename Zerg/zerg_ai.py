from all_imports_packages import *


class ZergAI(sc2.BotAI):
    def __init__(self):
        self.MAX_WORKERS = 50
        self.era = EARLY_GAME
        self.own_bases = []
        self.nr_bases = 0
        self.first_expansion_done = False
        self.save_for_first_expansion = False
        self.save_for_spawning_pool = False
        self.MORPH_FROM_IDS = [LARVA, ZERGLING, LARVA, ROACH, LARVA]
        self.ARMY_IDS = [ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK]
        self.FREQUENCES = [20, 10, 15, 5, 10]

        self.unit_in_queue = False
        self.selected_unit_index_in_queue = None

    async def on_step(self, iteration):
        await self.update_state()

        await self.first_expand()
        await self.expand()
        if self.nr_bases:
            await self.distribute_workers()
            if not self.save_for_first_expansion and not self.save_for_spawning_pool:
                await self.build_overlords()
                await self.build_drones()
            await self.build_extractors()
            await self.build_building(SPAWNINGPOOL, self.own_bases[0])
            await self.build_building(BANELINGNEST, self.own_bases[0], start_time=4*60)
            await self.build_building(ROACHWARREN, self.own_bases[0], start_time=4*60)
            await self.build_queens()
            await self.queens_inject()
            await self.build_units_probabilistic()
            await self.attack_enemy()

    async def update_state(self):
        if self.time < 4 * 60:
            self.era = EARLY_GAME
        elif self.time < 9 * 60:
            self.era = MID_GAME
        else:
            self.era = LATE_GAME

        self.own_bases = []
        for base in self.units(HATCHERY).ready:
            self.own_bases.append(base)

        for base in self.units(LAIR):
            self.own_bases.append(base)

        for base in self.units(HIVE):
            self.own_bases.append(base)

        self.nr_bases = len(self.own_bases)

        if self.nr_bases == 1 and self.already_pending(HATCHERY) == 1 and not self.first_expansion_done:
            self.first_expansion_done = True
            self.save_for_first_expansion = False
            self.save_for_spawning_pool = True

        if self.already_pending(SPAWNINGPOOL) and self.save_for_spawning_pool:
            self.save_for_spawning_pool = False

        # await self.chat_send(str(self.save_for_first_expansion) + " | " + str(self.save_for_spawning_pool))

    async def build_drones(self):
        nr_bases = len(self.own_bases)
        nr_drones = len(self.units(DRONE))
        nr_workers_per_base = 8 * 2 + 2 * 3

        if nr_drones + self.already_pending(DRONE) < nr_bases * nr_workers_per_base and nr_drones < self.MAX_WORKERS:
            larvae = self.units(LARVA).ready

            if self.can_afford(DRONE) and larvae.exists:
                await self.do(larvae.random.train(DRONE))

    async def build_overlords(self):
        supply_gap = [5, 12, 18]
        pending_ideal = [1, 2, 2]

        if self.supply_cap == 200:
            return

        if self.supply_left < supply_gap[self.era]:
            larvae = self.units(LARVA).ready
            if larvae.exists and self.already_pending(OVERLORD) < pending_ideal[self.era] and self.can_afford(OVERLORD):
                await self.do(larvae.random.train(OVERLORD))

    async def build_building(self, building_id, chosen_base, required_amount=1, start_time=0):
        if not (self.already_pending(HATCHERY) or self.nr_bases >= 2):
            return

        if self.time < start_time:
            return

        if building_id == ROACHWARREN and self.units(SPAWNINGPOOL).ready.amount < 1:
            return

        if self.can_afford(building_id) and self.already_pending(building_id) \
                + self.units(building_id).filter(
            lambda structure: structure.type_id == building_id and structure.is_ready
        ).amount < required_amount:
            map_center = self.game_info.map_center
            position_towards_map_center = chosen_base.position.towards(map_center, distance=5)
            await self.build(building_id, near=position_towards_map_center, placement_step=1)

    async def build_extractors(self):
        if len(self.units(SPAWNINGPOOL)) == 0:
            return

        for hatchery in self.own_bases:
            drones = self.units(DRONE)
            if len(drones) == 0:
                continue

            if self.units(DRONE).closer_than(7, hatchery).amount < 8:
                continue

            vespenes = self.state.vespene_geyser.closer_than(10.0, hatchery)

            for vespene in vespenes:
                if not self.can_afford(EXTRACTOR):
                    break

                if self.units(EXTRACTOR).closer_than(1.0, vespene).exists:
                    break

                worker = self.select_build_worker(vespene.position)
                if worker is None:
                    break

                await self.do(worker.build(EXTRACTOR, vespene))

    async def build_queens(self):
        if len(self.units(SPAWNINGPOOL).ready) == 0:
            return

        nr_demanded_queens = [self.nr_bases, self.nr_bases + 2, self.nr_bases * 1.5 + 2]
        nr_queens = self.units(QUEEN).ready.amount

        for base in self.own_bases:
            if self.can_afford(QUEEN) and nr_queens < nr_demanded_queens[self.era] and base.is_idle:
                await self.do(base.train(QUEEN))

    async def queens_inject(self):
        for base in self.own_bases:
            queens = self.units(QUEEN).idle
            if len(queens) == 0:
                return

            queen = self.units(QUEEN).closest_to(base)

            abilities = await self.get_available_abilities(queen)
            if EFFECT_INJECTLARVA in abilities:
                await self.do(queen(EFFECT_INJECTLARVA, base))

    async def first_expand(self):
        if self.first_expansion_done:
            return

        if self.time > 40:
            drones = self.units(DRONE)
            if len(drones) == 0:
                return

            position = await self.get_next_expansion()
            drone = self.units(DRONE).closest_to(position)

            if drone is None:
                return

            await self.do(drone.move(position))
            self.save_for_first_expansion = True

            if self.can_afford(HATCHERY):
                await self.expand_now()

    async def expand(self):
        nr_drones = len(self.units(DRONE))
        nr_workers_per_base = 8 * 2 + 2 * 3
        nr_current_bases = self.nr_bases + self.already_pending(HATCHERY)
        nr_desired_drones = nr_current_bases * nr_workers_per_base * 0.7

        if NR_EARLY_OPTIMAL_BASES <= nr_current_bases and nr_drones < nr_desired_drones:
            return

        if nr_current_bases < (self.time / 30) and self.can_afford(HATCHERY):
            await self.expand_now()

    async def build_units(self, from_id, morph_id):
        if self.nr_bases < 2:
            return False

        to_evolve_units = self.units(from_id)
        if to_evolve_units.amount == 0:
            return False

        if self.can_afford(morph_id) and to_evolve_units.exists:
            await self.do(to_evolve_units.random.train(morph_id))
            return True

    async def attack_enemy(self):
        army_units = self.units.of_type(self.ARMY_IDS)

        if self.supply_army < 70:
            return

        target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position

        for creature in army_units.idle:
            await self.do(creature.attack(target))

    async def build_units_probabilistic(self):
        if self.unit_in_queue:
            i = self.selected_unit_index_in_queue
            morph_from_id = self.MORPH_FROM_IDS[i]
            army_id = self.ARMY_IDS[i]
            if await self.build_units(morph_from_id, army_id):
                self.unit_in_queue = False
                self.selected_unit_index_in_queue = None

        else:
            # [ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK]

            can_make = [False for x in self.FREQUENCES]
            if self.units(SPAWNINGPOOL).ready.amount > 0:
                can_make[0] = True

            if self.units(BANELINGNEST).ready.amount > 0 and self.units(ZERGLING).amount > 0:
                can_make[1] = True

            if self.units(ROACHWARREN).ready.amount > 0:
                can_make[2] = True
                if self.units(ROACH).amount > 0:
                    can_make[3] = True

            if self.units(HYDRALISKDEN).ready.amount > 0:
                can_make[4] = True

            freq_sum = 0
            for i, freq in enumerate(self.FREQUENCES):
                if can_make[i]:
                    freq_sum += freq

            probabilities = [0.0 for x in self.FREQUENCES]
            for i, freq in enumerate(self.FREQUENCES):
                if can_make[i]:
                    probabilities[i] = freq / freq_sum

            if np.sum(probabilities) == 0:
                return

            index = np.random.choice(np.arange(0, len(probabilities)), p=probabilities)

            self.unit_in_queue = True
            self.selected_unit_index_in_queue = index
