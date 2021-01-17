from Zerg.Zagara.unit_table import *

from Zerg.Zagara.utility import *
from Zerg.Zagara.builder import *
from Zerg.Zagara.army import *


class ZagaraAI(sc2.BotAI):
    def __init__(self):
        self.MAX_WORKERS = 70
        self.era = EARLY_GAME

        self.own_bases = []
        self.own_bases_ready = []
        self.nr_bases = 0

        self.defending = False

        self.builder = Builder(self)
        self.army = Army()

        self.expansion_locations_list_own = []
        self.scouting_task_dict = {}

        self.positions_with_creep = []
        self.positions_without_creep = []

        self.creep_target_distance = 15
        self.used_creep_tumors = set()

        self.unit_table = UnitTable()

        self.cached_enemy_units = dict()  # {unit.tag : (unit.pos. unit.type_id)}
        self.enemy_units_not_visible = []

        self.throw_army = False
        self.throw_army_timer = 0

        self.units_task = dict()  # {unit.tag : role}

        # self.unit_command_uses_self_do = True

    def get_priority(self, unit_id):
        chance = np.random.random_sample()
        required_chance = 2 ** (-self.builder.priorities[unit_id])
        return chance < required_chance

    async def on_start(self):
        self.expansion_locations_list_own = []
        self.scouting_task_dict = {}

        for el in self.expansion_locations_list:
            self.expansion_locations_list_own.append(el)

    async def distribute_workers_by_case(self):
        if self.time < 7 * 60 or self.minerals / (self.vespene + EPSILON) < self.builder.resource_ratio:
            await self.distribute_workers()
        else:
            await self.distribute_workers_fav_gas()
            await self.manage_idle_drones()

    async def on_step(self, iteration):
        await self.update_state()
        await self.first_expand()
        await self.expand()

        if self.nr_bases:
            await self.distribute_workers_by_case()

            if not self.builder.save_for_first_expansion and not self.builder.save_for_spawning_pool:
                await self.build_drones()
                await self.build_overlords()

            await self.builder.build_buildings()

            await self.build_queens()
            await self.build_units_probabilistic()
            await self.handle_micro()

    async def handle_micro(self):
        await self.building_cancel_micro()

        await self.expand_creep_by_tumor()

        await self.defend()
        await self.attack_enemy()

        await self.expand_creep_by_queen()
        await self.queens_inject()

        await self.micro_in_battle_combat()
        await self.micro_in_battle_caster()
        await self.micro_in_battle_spawns()

        await self.micro_in_battle_scouts()
        await self.army_cast_skills()
        await self.scout()

    async def update_state(self):
        if self.time < 4 * 60:
            self.era = EARLY_GAME
        elif self.time < 9 * 60:
            self.era = MID_GAME
            self.unit_table.unit_power[ZERGLING] = 100
        else:
            self.era = LATE_GAME
            self.unit_table.unit_power[ZERGLING] = 150
            self.unit_table.unit_power[BANELING] = 150

        self.own_bases_ready = []
        for base in self.structures(HATCHERY).ready | self.structures(LAIR) | self.structures(HIVE):
            self.own_bases_ready.append(base)

        self.own_bases = []
        for base in self.structures(HATCHERY) | self.structures(LAIR) | self.structures(HIVE):
            self.own_bases.append(base)

        self.nr_bases = len(self.own_bases_ready)

        if self.nr_bases >= 1 and self.already_pending(HATCHERY) >= 1 and not self.builder.first_expansion_done:
            self.builder.first_expansion_done = True
            self.save_for_first_expansion = False
            self.builder.save_for_spawning_pool = True

        if self.already_pending(SPAWNINGPOOL) and self.builder.save_for_spawning_pool:
            self.builder.save_for_spawning_pool = False

        if self.era == EARLY_GAME:
            self.builder.resource_ratio = 2
            self.builder.priorities = {
                DRONE: 1,
                "ARMY": 2,
                SPAWNINGPOOL: 0,
                ROACHWARREN: 2,
                BANELINGNEST: 2,
                "EXPAND": 2,
                OVERLORD: 0,
                QUEEN: 0,
                EVOLUTIONCHAMBER: 3,
                LAIR: 5,
                HYDRALISKDEN: 9,
                INFESTATIONPIT: 9,
                "UPGRADES": 4,
                LURKERDENMP: 0,
                SPIRE: 0,
                NYDUSNETWORK: 0,
                HIVE: 0,
                ULTRALISKCAVERN: 0,
                GREATERSPIRE: 0,
            }
        elif self.era == MID_GAME:
            self.builder.resource_ratio = 1
            self.builder.priorities = {
                DRONE: 1,
                "ARMY": 2,
                SPAWNINGPOOL: 0,
                ROACHWARREN: 0,
                BANELINGNEST: 0,
                "EXPAND": 2,
                OVERLORD: 0,
                QUEEN: 2,
                EVOLUTIONCHAMBER: 1,
                LAIR: 0,
                HYDRALISKDEN: 0,
                INFESTATIONPIT: 1,
                "UPGRADES": 0,
                LURKERDENMP: 0,
                SPIRE: 0,
                NYDUSNETWORK: 0,
                HIVE: 0,
                ULTRALISKCAVERN: 0,
                GREATERSPIRE: 0,
            }

        else:
            self.builder.resource_ratio = 1
            self.builder.priorities = {
                DRONE: 1,
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
                INFESTATIONPIT: 0,
                "UPGRADES": 0,
                LURKERDENMP: 0,
                SPIRE: 0,
                NYDUSNETWORK: 0,
                HIVE: 0,
                ULTRALISKCAVERN: 0,
                GREATERSPIRE: 0,
            }

        if self.units(DRONE).amount < 50 and self.era >= MID_GAME and not self.defending:
            self.builder.priorities[DRONE] = 0
            self.builder.priorities["ARMY"] = 2

        if self.minerals > 1000 and self.vespene > 600 \
                and self.units(LARVA).ready.amount > 15 and self.supply_used > 180:
            self.throw_army = True
            self.throw_army_timer = self.time

        if self.throw_army and self.throw_army_timer + 30 < self.time:
            self.throw_army = False

        # Update positions
        for enemy in self.enemy_units:
            self.cached_enemy_units[enemy.tag] = (enemy.position, enemy.type_id)

        self.enemy_units_not_visible = []
        for enemy_tag in self.cached_enemy_units:
            if enemy_tag not in self.enemy_units.tags:
                self.enemy_units_not_visible.append(self.cached_enemy_units[enemy_tag])

        ally_units = self.units.of_type(self.army.ARMY_IDS)
        enemy_units = self.enemy_units - self.enemy_units({DRONE, SCV, PROBE})

        if enemy_units.amount and self.better_army(ally_units, enemy_units, self.enemy_units_not_visible) < 0.65:
            self.builder.priorities[DRONE] = 2
            self.builder.priorities["ARMY"] = 0

        countered_finish = self.enemy_race != Race.Terran
        if countered_finish:
            self.army.FREQUENCES = {
                ZERGLING: 1,
                BANELING: 0,
                ROACH: 2,
                RAVAGER: 1,
                HYDRALISK: 2,
                INFESTOR: 0,
                SWARMHOSTMP: 0,
                LURKERMP: 0,
                MUTALISK: 0,
                CORRUPTOR: 0,
                BROODLORD: 0,
                ULTRALISK: 0,
                VIPER: 0,
                OVERSEER: 0,
            }

            for enemy_tag in self.cached_enemy_units:
                unit_type = self.cached_enemy_units[enemy_tag][1]

                if unit_type not in self.unit_table.units_counter_by:
                    continue

                for unit_freq, freq in self.unit_table.units_counter_by[unit_type]:
                    desired_freq = freq + 0.0
                    if self.era == MID_GAME and unit_freq in [ZERGLING, BANELING]:
                        desired_freq /= 2

                    if self.era == MID_GAME and unit_freq in [ZERGLING, BANELING]:
                        desired_freq /= 8

                    self.army.FREQUENCES[unit_freq] += desired_freq

                    if unit_freq == BANELING:
                        self.army.FREQUENCES[ZERGLING] += desired_freq

                    if unit_freq == RAVAGER:
                        self.army.FREQUENCES[ROACH] += desired_freq

                    if unit_freq == LURKERMP:
                        self.army.FREQUENCES[HYDRALISK] += desired_freq

                    if unit_freq == BROODLORD:
                        self.army.FREQUENCES[CORRUPTOR] += desired_freq

        else:
            self.army.FREQUENCES = {
                ZERGLING: 2,
                BANELING: 1,
                ROACH: 20,
                RAVAGER: 4,
                HYDRALISK: 10,
                INFESTOR: 4,
                SWARMHOSTMP: 3,
                LURKERMP: 5,
                MUTALISK: 5,
                CORRUPTOR: 10,
                BROODLORD: 10,
                ULTRALISK: 4,
                VIPER: 3,
                OVERSEER: 3,
            }

        i = 0
        for unit_type in self.army.FREQUENCES:
            if self.army.FREQUENCES[unit_type]:
                print(unit_type, ":", self.army.FREQUENCES[unit_type], end="   |   ")
                i += 1

                if i % 4 == 0:
                    print()
        print()

    async def on_unit_destroyed(self, unit_tag: int):
        if unit_tag in self.cached_enemy_units:
            self.cached_enemy_units.pop(unit_tag)

        if unit_tag in self.scouting_task_dict.keys():
            self.scouting_task_dict.pop(unit_tag)

        if unit_tag in self.units_task.keys():
            self.units_task.pop(unit_tag)

    async def build_drones(self):
        if not self.get_priority(DRONE):
            return

        nr_drones = len(self.units(DRONE))

        nr_ideal_workers = 0
        for base in self.structures(HATCHERY).ready | self.structures(LAIR) | self.structures(HIVE):
            nr_ideal_workers += base.ideal_harvesters

        if nr_drones + self.already_pending(DRONE) < nr_ideal_workers and nr_drones + self.already_pending(
                DRONE) < self.MAX_WORKERS:
            larvae = self.units(LARVA)

            if self.can_afford(DRONE) and larvae.exists:
                larvae.random.train(DRONE)

    async def build_overlords(self):
        if not self.get_priority(OVERLORD):
            return

        supply_gap = [5, 12, 18]
        pending_ideal = [1, 2, 2]

        if self.supply_cap == 200:
            return

        if self.supply_left < supply_gap[self.era]:
            larvae = self.units(LARVA).ready
            if larvae.exists and self.already_pending(OVERLORD) < pending_ideal[self.era] and self.can_afford(OVERLORD):
                larvae.random.train(OVERLORD)

    async def manage_idle_drones(self):
        if not self.townhalls.exists:
            return

        mineral_fields_available = Units([], self)
        for townhall in self.townhalls:
            mineral_fields = self.mineral_field.closer_than(10, townhall)
            if mineral_fields.amount:
                mineral_fields_available.extend(mineral_fields)

        if mineral_fields_available.amount == 0:
            return

        for worker in self.workers.idle:
            mf = mineral_fields_available.closest_to(worker)
            worker.gather(mf)

    async def distribute_workers_fav_gas(self, performanceHeavy=True, only_saturate_gas=False):
        mineral_tags = [x.tag for x in self.mineral_field]
        geyser_tags = [x.tag for x in self.gas_buildings.ready]

        worker_pool = Units([], self)
        worker_pool_tags = set()

        # find all geysers that have surplus or deficit
        deficit_geysers = {}
        surplus_geysers = {}
        for g in self.gas_buildings.ready.filter(lambda x: x.vespene_contents > 0):
            # only loop over geysers that have still gas in them
            deficit = g.ideal_harvesters - g.assigned_harvesters
            if deficit > 0:
                deficit_geysers[g.tag] = {"unit": g, "deficit": deficit}
            elif deficit < 0:
                surplus_workers = self.workers.closer_than(10, g).filter(
                    lambda worker:
                    worker not in worker_pool_tags and len(worker.orders) == 1 and
                    worker.orders[0].ability.id in [AbilityId.HARVEST_GATHER] and
                    worker.orders[0].target in geyser_tags
                )
                # workerPool.extend(surplusWorkers)
                for i in range(-deficit):
                    if surplus_workers.amount > 0:
                        worker = surplus_workers.pop()
                        worker_pool.append(worker)
                        worker_pool_tags.add(worker.tag)
                surplus_geysers[g.tag] = {"unit": g, "deficit": deficit}

        # find all townhalls that have surplus or deficit
        deficit_townhalls = {}
        surplus_townhalls = {}
        if not only_saturate_gas:
            for townhall in self.townhalls:
                deficit = townhall.ideal_harvesters - townhall.assigned_harvesters
                if deficit > 0:
                    deficit_townhalls[townhall.tag] = {"unit": townhall, "deficit": deficit}
                elif deficit < 0:
                    surplus_workers = self.workers.closer_than(10, townhall).filter(
                        lambda worker: worker.tag not in worker_pool_tags and
                                       len(worker.orders) == 1 and worker.orders[0].ability.id in [
                                           AbilityId.HARVEST_GATHER] and worker.orders[0].target in mineral_tags)
                    # workerPool.extend(surplusWorkers)
                    for i in range(-deficit):
                        if surplus_workers.amount > 0:
                            worker = surplus_workers.pop()
                            worker_pool.append(worker)
                            worker_pool_tags.add(worker.tag)
                    surplus_townhalls[townhall.tag] = {"unit": townhall, "deficit": deficit}

            if all([len(deficit_geysers) == 0, len(surplus_geysers) == 0,
                    len(surplus_townhalls) == 0 or deficit_townhalls == 0]):
                # cancel early if there is nothing to balance
                return

        # check if deficit in gas less or equal than what we have in surplus, else grab some
        # more workers from surplus bases
        deficit_gas_count = sum(
            gas_info["deficit"] for gas_tag, gas_info in deficit_geysers.items() if gas_info["deficit"] > 0)
        surplus_count = sum(-gas_info["deficit"]
                            for gas_tag, gas_info in surplus_geysers.items() if gas_info["deficit"] < 0)
        surplus_count += sum(-th_info["deficit"]
                             for th_tag, th_info in surplus_townhalls.items() if th_info["deficit"] < 0)

        if deficit_gas_count - surplus_count > 0:
            # grab workers near the gas who are mining minerals
            for gather_tag, gather_info in deficit_geysers.items():
                if worker_pool.amount >= deficit_gas_count:
                    break
                workersNearGas = self.workers.closer_than(10, gather_info["unit"]).filter(
                    lambda w: w.tag not in worker_pool_tags and len(w.orders) == 1 and w.orders[0].ability.id in [
                        AbilityId.HARVEST_GATHER] and w.orders[0].target in mineral_tags)
                while workersNearGas.amount > 0 and worker_pool.amount < deficit_gas_count:
                    worker = workersNearGas.pop()
                    worker_pool.append(worker)
                    worker_pool_tags.add(worker.tag)

        # now we should have enough workers in the pool to saturate all gases, and if there are workers
        # left over, make them mine at townhalls that have mineral workers deficit
        for gather_tag, gather_info in deficit_geysers.items():
            if performanceHeavy:
                # sort furthest away to closest (as the pop() function will take the last element)
                worker_pool.sort(key=lambda x: x.distance_to(gather_info["unit"]), reverse=True)
            for i in range(gather_info["deficit"]):
                if worker_pool.amount > 0:
                    worker = worker_pool.pop()
                    if len(worker.orders) == 1 and worker.orders[0].ability.id in [AbilityId.HARVEST_RETURN]:
                        worker.gather(gather_info["unit"], queue=True)
                    else:
                        worker.gather(gather_info["unit"])

        if not only_saturate_gas:
            # if we now have left over workers, make them mine at bases with deficit in mineral workers
            for th_tag, th_info in deficit_townhalls.items():
                if performanceHeavy:
                    # sort furthest away to closest (as the pop() function will take the last element)
                    worker_pool.sort(key=lambda x: x.distance_to(th_info["unit"]), reverse=True)
                for i in range(th_info["deficit"]):
                    if worker_pool.amount > 0:
                        worker = worker_pool.pop()
                        mineral_field = self.mineral_field.closer_than(10, th_info["unit"]).closest_to(worker)
                        if len(worker.orders) == 1 and worker.orders[0].ability.id in [AbilityId.HARVEST_RETURN]:
                            worker.gather(mineral_field, queue=True)
                        else:
                            worker.gather(mineral_field)

    async def build_queens(self):
        if not self.get_priority(QUEEN):
            return

        if len(self.structures(SPAWNINGPOOL).ready) == 0:
            return

        nr_demanded_queens = [self.nr_bases + 1, self.nr_bases * 1 + 2, self.nr_bases * 1 + 2]
        nr_demanded_queens = [min(x, 6) for x in nr_demanded_queens]
        nr_queens = self.units(QUEEN).ready.amount

        for base in self.own_bases_ready:
            if self.can_afford(QUEEN) and nr_queens < nr_demanded_queens[self.era] and base.is_idle:
                base.train(QUEEN)

    async def queens_inject(self):
        for base in self.own_bases_ready:
            queens = self.units(QUEEN).idle
            if len(queens) == 0:
                return

            queen = self.units(QUEEN).closest_to(base)

            abilities = await self.get_available_abilities(queen)
            if EFFECT_INJECTLARVA in abilities:
                queen(EFFECT_INJECTLARVA, base)

    async def first_expand(self):
        if self.builder.first_expansion_done:
            return

        if self.time > 40:
            drones = self.units(DRONE)
            if len(drones) == 0:
                return

            position = await self.get_next_expansion()
            drone = self.units(DRONE).closest_to(position)

            if drone is None:
                return

            drone.move(position)
            self.save_for_first_expansion = True

            if self.can_afford(HATCHERY):
                await self.expand_now(max_distance=0)

    async def expand(self):
        # TO DO: REDUCE NR EXPANSIONS
        if not self.get_priority("EXPAND"):
            return

        if self.already_pending(HATCHERY):
            return

        nr_drones = len(self.units(DRONE))

        nr_ideal_workers = 0
        for base in self.structures(HATCHERY).ready | self.structures(LAIR) | self.structures(HIVE):
            nr_ideal_workers += base.ideal_harvesters
            if self.units(DRONE).closer_than(10, base).amount < 5:
                return

        nr_desired_drones = nr_ideal_workers * 0.7

        nr_bases = (self.structures(HATCHERY).ready | self.structures(LAIR) | self.structures(HIVE)).amount

        if nr_bases > NR_EARLY_OPTIMAL_BASES and nr_drones < nr_desired_drones:
            return

        if nr_bases < (self.time / 80) and self.can_afford(HATCHERY):
            await self.expand_now(max_distance=0)

    async def evolve_units(self, from_id, morph_id, time=0):
        if self.time < time:
            return False

        if self.nr_bases < 2:
            return False

        to_evolve_units = self.units(from_id) | self.structures(from_id)
        if to_evolve_units.amount == 0:
            return False

        if self.can_afford(morph_id) and to_evolve_units.exists:
            to_evolve_units.random.train(morph_id)
            return True

    async def attack_enemy(self):
        if self.time < 60 * 3:
            return

        # if self.defending:
        #     return

        army_units = self.units.of_type(self.army.ARMY_IDS)
        army_units.tags_not_in([x for x in self.units_task.keys() if self.units_task[x] != DEFENDING])

        if self.supply_army - self.units(QUEEN).amount * 2 < 1:
            target = self.enemy_units.visible
            if len(target):
                target = target.random.position

                bases = self.structures(HATCHERY).ready | self.structures(LAIR) | self.structures(HIVE)

                for base in bases:
                    if base.distance_to(target) <= 20:
                        for creature in army_units.idle:
                            creature.attack(target)

                # if self.start_location.distance2_to(target) <= \
                #   self.start_location.distance2_to(self.game_info.map_center):
                #     for creature in army_units.idle:
                #         creature.attack(target)

            else:
                # If there are no threats
                target = self.game_info.map_center
                for creature in army_units.idle.further_than(10, self.game_info.map_center):
                    creature.attack(target)

            return

        target = self.enemy_structures.random_or(self.enemy_start_locations[0]).position

        army_units_combat = self.units.of_type(self.army.ARMY_IDS_COMBAT)
        army_units_combat = army_units_combat.filter(lambda unit: unit.type_id != QUEEN)

        for creature in army_units.idle:
            if creature.type_id in self.army.ARMY_IDS_CASTER and army_units_combat.amount:
                closest_ally = army_units_combat.closest_to(creature)
                creature.move(closest_ally.position)
            else:
                creature.attack(target)

    async def build_units_probabilistic(self):
        if self.minerals < 100:
            return

        if not self.get_priority("ARMY"):
            return

        if self.army.unit_in_queue:
            i = self.army.selected_unit_index_in_queue
            morph_from_id = self.army.MORPH_FROM_IDS[i]

            if morph_from_id != LARVA and self.units(morph_from_id).amount == 0:
                self.army.unit_in_queue = False
                self.army.selected_unit_index_in_queue = None

            army_id = self.army.ARMY_IDS[i]
            if await self.evolve_units(morph_from_id, army_id):
                self.army.unit_in_queue = False
                self.army.selected_unit_index_in_queue = None

        else:
            can_make = dict()
            if self.structures(SPAWNINGPOOL).ready.amount:
                can_make[ZERGLING] = True

            if self.structures(BANELINGNEST).ready.amount and self.units(ZERGLING).amount:
                can_make[BANELING] = True

            if self.structures(ROACHWARREN).ready.amount:
                can_make[ROACH] = True
                if self.units(ROACH).amount:
                    can_make[RAVAGER] = True

            if self.structures(HYDRALISKDEN).ready.amount:
                can_make[HYDRALISK] = True

            if self.structures(INFESTATIONPIT).ready.amount:
                if self.units(INFESTOR).amount + self.units(INFESTORBURROWED).amount < self.army.max_units[INFESTOR]:
                    can_make[INFESTOR] = True

                if self.units(SWARMHOSTMP).amount + self.units(SWARMHOSTBURROWEDMP).amount < self.army.max_units[SWARMHOSTMP]:
                    can_make[SWARMHOSTMP] = True

            if self.structures(LURKERDENMP).ready.amount:
                can_make[LURKERMP] = True

            if self.structures(SPIRE).ready.amount or self.structures(GREATERSPIRE).amount:
                can_make[MUTALISK] = True
                can_make[CORRUPTOR] = True

            if self.structures(GREATERSPIRE).ready.amount and self.units(CORRUPTOR).amount:
                can_make[BROODLORD] = True

            if self.structures(ULTRALISKCAVERN).ready.amount:
                can_make[ULTRALISK] = True

            if self.structures(HIVE).ready.amount and self.units(VIPER).amount < self.army.max_units[VIPER]:
                can_make[VIPER] = True

            if self.structures(LAIR).ready.amount and self.units(OVERLORD).amount \
                    and self.units(OVERSEER).amount < self.army.max_units[OVERSEER]:
                can_make[OVERSEER] = True

            freq_sum = 0
            for unit in self.army.FREQUENCES:
                if unit in can_make:
                    freq_sum += self.army.FREQUENCES[unit]

            if freq_sum == 0:
                return

            probabilities = [0 for _ in self.army.FREQUENCES]

            for i, unit in enumerate(self.army.FREQUENCES):
                if unit in can_make:
                    probabilities[i] = self.army.FREQUENCES[unit] / freq_sum

            if np.sum(probabilities) == 0:
                return

            index = np.random.choice(np.arange(0, len(probabilities)), p=probabilities)

            self.army.unit_in_queue = True
            self.army.selected_unit_index_in_queue = index

    async def army_cast_skills(self):
        await self.ravager_corrosive_bile()
        await self.roach_burrow()
        await self.infestor_fungal_growth()
        await self.swarmhost_spawn_locusts()
        await self.lurker_borrow()
        await self.viper_abduct()

    async def ravager_corrosive_bile(self):
        for ravager in self.units(RAVAGER):
            abilities = await self.get_available_abilities(ravager)
            if EFFECT_CORROSIVEBILE not in abilities:
                continue

            possible_targets = self.enemy_units.closer_than(9, ravager)
            if possible_targets.amount == 0:
                continue

            target = possible_targets.random
            if target is None:
                continue

            ravager(EFFECT_CORROSIVEBILE, target.position)

    async def roach_burrow(self):
        for roach in self.units(ROACH):
            if roach.health_percentage > 2 / 5:
                continue

            abilities = await self.get_available_abilities(roach)
            if BURROWDOWN_ROACH not in abilities:
                continue

            roach(BURROWDOWN_ROACH)

        for roach in self.units(ROACHBURROWED):
            if roach.health_percentage < 4 / 5:
                continue

            abilities = await self.get_available_abilities(roach)
            if BURROWUP_ROACH not in abilities:
                continue

            roach(BURROWUP_ROACH)

    async def infestor_fungal_growth(self):
        for infestor in self.units(INFESTOR):
            abilities = await self.get_available_abilities(infestor)
            if FUNGALGROWTH_FUNGALGROWTH not in abilities:
                continue

            possible_targets = self.enemy_units.closer_than(10, infestor)
            if possible_targets.amount == 0:
                continue

            target = possible_targets.random
            infestor(FUNGALGROWTH_FUNGALGROWTH, target.position)

    async def swarmhost_spawn_locusts(self):
        for swarmhost in self.units(SWARMHOSTMP):
            abilities = await self.get_available_abilities(swarmhost)
            if EFFECT_SPAWNLOCUSTS not in abilities:
                continue

            possible_targets = self.enemy_units.closer_than(20, swarmhost)
            if possible_targets.amount == 0:
                continue

            target = possible_targets.random
            swarmhost(EFFECT_SPAWNLOCUSTS, target.position)

    async def lurker_borrow(self):
        for lurker in self.units(LURKERMP):
            enemies_local = self.enemy_units.closer_than(7, lurker) | self.enemy_structures.closer_than(7, lurker)

            enemy_ground_unit_targets = enemies_local.filter(
                lambda unit: lurker.distance_to(unit) <= 7 and not unit.is_flying
            )

            if enemy_ground_unit_targets.amount == 0:
                continue

            abilities = await self.get_available_abilities(lurker)

            if BURROWDOWN_LURKER not in abilities:
                continue

            lurker(BURROWDOWN_LURKER)

        for lurker in self.units(LURKERMPBURROWED):
            enemies_local = self.enemy_units.closer_than(10, lurker) | self.enemy_structures.closer_than(10, lurker)

            enemy_ground_unit_targets = enemies_local.filter(
                lambda unit: lurker.target_in_range(unit) and not unit.is_flying
            )

            if enemy_ground_unit_targets.amount:
                continue

            abilities = await self.get_available_abilities(lurker)
            if BURROWUP_LURKER not in abilities:
                continue

            lurker(BURROWUP_LURKER)

    async def viper_abduct(self):
        for viper in self.units(VIPER):
            abilities = await self.get_available_abilities(viper)
            if EFFECT_ABDUCT not in abilities:
                continue

            enemies_local = self.enemy_units.closer_than(11, viper)
            if enemies_local.amount == 0:
                continue

            enemies_local = enemies_local.filter(lambda unit: self.unit_table.unit_power[unit.type_id] >= 300)
            if enemies_local.amount == 0:
                continue

            enemies_local = enemies_local.sorted(lambda unit: self.unit_table.unit_power[unit.type_id], reverse=True)
            target = enemies_local[0]

            viper(EFFECT_ABDUCT, target)

    async def all_upgrades(self, building_id, time=0, exception_id_list=None):
        # useless_abilities = {CANCEL_BUILDINPROGRESS, CANCEL_QUEUE5, RALLY_HATCHERY_UNITS,
        #                      RALLY_HATCHERY_WORKERS, SMART, TRAINQUEEN_QUEEN}

        if exception_id_list is None:
            exception_id_list = []

        buildings = self.structures(building_id).ready
        for building in buildings:
            abilities = await self.get_available_abilities(building)

            for ability in abilities:
                if "RESEARCH" in str(ability) and ability not in exception_id_list:
                    # print(ability)
                    await self.upgrade(building, ability, time)

    async def upgrade(self, building, research_id, time=0):
        if self.time < time:
            return

        abilities = await self.get_available_abilities(building)
        if research_id in abilities:
            if self.can_afford(research_id) and building.is_idle:
                building(research_id)
                await self.chat_send(f"Researching: {str(research_id)}")

    async def building_cancel_micro(self):
        for building in self.structures.not_ready.filter(
                lambda x: x.health_percentage + 0.05 < x.build_progress and x.health_percentage < 0.1
        ):
            building(CANCEL)

    async def update_creep_overage(self, step_size=None):
        if step_size is None:
            step_size = self.creep_target_distance
        ability = self._game_data.abilities[ZERGBUILD_CREEPTUMOR.value]

        positions = [
            Point2((x, y))
            for x in range(self._game_info.playable_area[0] + step_size,
                           self._game_info.playable_area[0] + self._game_info.playable_area[2] - step_size,
                           step_size)
            for y in range(self._game_info.playable_area[1] + step_size,
                           self._game_info.playable_area[1] + self._game_info.playable_area[3] - step_size,
                           step_size)
        ]

        valid_placements = await self._client.query_building_placement(ability, positions)
        success_results = [
            ActionResult.Success,  # tumor can be placed there, so there must be creep
            ActionResult.CantBuildLocationInvalid,  # location is used up by another building or doodad,
            ActionResult.CantBuildTooFarFromCreepSource,  # - just outside of range of creep
        ]
        self.positions_with_creep = [p for valid, p in zip(valid_placements, positions) if
                                     valid in success_results]

        self.positions_without_creep = [p for index, p in enumerate(positions) if
                                        valid_placements[index] not in success_results]

        self.positions_without_creep = [p for valid, p in zip(valid_placements, positions) if
                                        valid not in success_results]

        return self.positions_with_creep, self.positions_without_creep

    async def find_creep_plant_locations(self, casting_unit, min_range=0, max_range=500, step_size=1,
                                         location_amount=32):

        ability = self._game_data.abilities[ZERGBUILD_CREEPTUMOR.value]

        positions = get_positions_around_unit(casting_unit, min_range, max_range,
                                              step_size, location_amount)

        positions = [pos for pos in positions if get_closest_distance(self.expansion_locations_list_own, pos) > 4]

        valid_placements = await self._client.query_building_placement(ability, positions)

        valid_placements = [p for index, p in enumerate(positions) if valid_placements[index] == ActionResult.Success]

        all_tumors = self.structures(CREEPTUMOR) | self.structures(CREEPTUMORBURROWED) | self.structures(
            CREEPTUMORQUEEN)
        unused_tumors = all_tumors.filter(lambda x: x.tag not in self.used_creep_tumors)
        if casting_unit in all_tumors:
            unused_tumors = unused_tumors.filter(lambda x: x.tag != casting_unit.tag)

        if len(unused_tumors) > 0:
            valid_placements = [x for x in valid_placements if x.distance_to(unused_tumors.closest_to(x)) >= 10]

        valid_placements.sort(key=lambda x: x.distance_to(x.closest(self.positions_without_creep)), reverse=False)

        if len(valid_placements) > 0:
            return valid_placements

        return None

    async def expand_creep_by_queen(self):
        queens = self.units(QUEEN).idle.filter(
            lambda q: q.energy >= 25 and q.is_idle
        )
        if queens.amount == 0:
            return

        await self.update_creep_overage()

        for queen in queens:
            locations = await self.find_creep_plant_locations(
                queen, min_range=3, max_range=30, step_size=2, location_amount=16
            )

            if locations is None:
                continue

            for loc in locations:

                ability = self._game_data.abilities[ZERGBUILD_CREEPTUMOR.value]
                valid_placements = await self._client.query_building_placement(ability, [loc])
                if valid_placements[0] != ActionResult.Success:
                    continue

                queen(BUILD_CREEPTUMOR_QUEEN, loc)
                break

    async def expand_creep_by_tumor(self):
        all_tumors = self.structures(CREEPTUMOR) | self.structures(CREEPTUMORBURROWED) | self.structures(
            CREEPTUMORQUEEN)

        if all_tumors.amount == 0:
            return

        unused_tumors = all_tumors.filter(lambda x: x.tag not in self.used_creep_tumors)

        if unused_tumors.amount == 0:
            return

        await self.update_creep_overage()

        new_tumors_positions = set()
        for tumor in unused_tumors:
            tumors_close_to_tumor = [x for x in new_tumors_positions if tumor.distance_to(Point2(x)) < 8]

            if len(tumors_close_to_tumor) > 0:
                continue

            abilities = await self.get_available_abilities(tumor)
            if AbilityId.BUILD_CREEPTUMOR_TUMOR not in abilities:
                continue

            locations = await self.find_creep_plant_locations(
                tumor, min_range=10, max_range=10, location_amount=32
            )

            if locations is None:
                continue

            for loc in locations:
                ability = self._game_data.abilities[ZERGBUILD_CREEPTUMOR.value]
                valid_placements = await self._client.query_building_placement(ability, [loc])
                if valid_placements[0] != ActionResult.Success:
                    continue

                tumor(BUILD_CREEPTUMOR_TUMOR, loc)
                new_tumors_positions.add((tumor.position.x, tumor.position.y))
                self.used_creep_tumors.add(tumor.tag)
                break

    def better_army(self, ally_army, enemy_army, enemy_army_not_visible):
        score_ally = 0
        for ally in ally_army:
            if ally.type_id in self.army.ARMY_IDS_CASTER and ally.energy < self.army.ARMY_CASTER_MINIMUM_ENERGY[
                ally.type_id]:
                continue

            if ally.type_id in self.unit_table.unit_power:
                score_ally += self.unit_table.unit_power[ally.type_id]

        score_enemy = 0
        for enemy in enemy_army:
            if enemy.type_id in self.unit_table.unit_power:
                score_enemy += self.unit_table.unit_power[enemy.type_id]

        for enemy in enemy_army_not_visible:
            enemy_type_id = enemy[1]
            if enemy_type_id in self.unit_table.unit_power:
                score_enemy += self.unit_table.unit_power[enemy_type_id]

        return score_ally / (score_enemy + EPSILON)

    async def unit_attack_list(self, ally, enemies=None, spawn=False):
        if enemies is None:
            enemies = self.enemy_units | self.enemy_structures

        if spawn == False:
            lambda_ground = lambda unit: ally.target_in_range(unit) and not unit.is_flying
            lambda_air = lambda unit: ally.target_in_range(unit) and unit.is_flying
        else:
            lambda_ground = lambda unit: not unit.is_flying
            lambda_air = lambda unit: unit.is_flying

        enemy_ground_unit_targets = enemies.filter(
            lambda_ground
        )

        enemy_flying_unit_targets = enemies.filter(
            lambda_air
        )

        if ally.can_attack_both:
            enemy_units_target = enemy_ground_unit_targets | enemy_flying_unit_targets
        elif ally.can_attack_ground:
            enemy_units_target = enemy_ground_unit_targets
        elif ally.can_attack_air:
            enemy_units_target = enemy_flying_unit_targets
        else:
            enemy_units_target = None

        return enemy_units_target

    async def unit_attack(self, ally, enemies=None):
        if enemies is None:
            enemies = self.enemy_units | self.enemy_structures

        enemy_units_target = await self.unit_attack_list(ally, enemies)
        # Can attack
        if ally.weapon_cooldown == 0 and enemy_units_target is not None and enemy_units_target.amount != 0:
            attackable_unit_targets = enemy_units_target.filter(
                lambda unit: unit.can_be_attacked
            )
            if attackable_unit_targets.amount != 0:
                lowest_unit_target = attackable_unit_targets.sorted(
                    lambda unit: unit.health_percentage and unit.is_structure
                )[0]
                ally.attack(lowest_unit_target)
                return True

        return False

    async def unit_retreat(self, ally, enemies=None, can_attack=True):
        if enemies is None:
            enemies = self.enemy_units | self.enemy_structures

        ally_units = self.units.of_type(self.army.ARMY_IDS) | self.units.of_type(self.army.ARMY_IDS_SPAWNS)
        enemy_attackers = enemies.filter(lambda unit: unit.can_attack)

        enemy_attackers_close = enemy_attackers.filter(
            lambda unit: unit.distance_to(ally) < 20
        )

        if enemy_attackers_close.amount == 0:
            return True

        ally_army_close = ally_units.filter(
            lambda unit: unit.distance_to(ally) < 20
        )

        enemy_attackers_not_visible = filter(
            lambda unit: unit[0].distance_to(ally.position) < 20,
            self.enemy_units_not_visible
        )

        unit_task_is_defending = False
        if ally.tag in self.units_task.keys():
            unit_task_is_defending = self.units_task[ally.tag] == DEFENDING and ally.health_percentage > 0.15

        if self.throw_army or unit_task_is_defending:
            pass

        elif self.better_army(ally_army_close, enemy_attackers_close, enemy_attackers_not_visible) <= 1:
            retreat_points = neighbors_8(ally.position, distance=2) | neighbors_8(ally.position, distance=4)

            if not ally.is_flying:
                retreat_points = {x for x in retreat_points if self.in_pathing_grid(x)}
            retreat_points = {
                x for x in retreat_points if enemy_attackers_close.closest_to(x).distance_to(x) > 3
            }

            if not retreat_points:
                closest_enemy = enemy_attackers_close.closest_to(ally)

                if can_attack:
                    ally.attack(closest_enemy.position)
                    return True

                return False

            closest_enemy = enemy_attackers_close.closest_to(ally)
            retreat_point = max(
                retreat_points, key=lambda x: x.distance_to(closest_enemy) - x.distance_to(ally)
            )

            if enemy_attackers_close.closest_to(retreat_point).distance_to(retreat_point) < 4 and can_attack:
                ally.attack(closest_enemy.position)
                return True
            else:
                ally.move(retreat_point)
                return True

        return False

    async def unit_kite_back(self, ally, enemies=None, can_attack=True):
        if enemies is None:
            enemies = self.enemy_units | self.enemy_structures

        if ally.is_flying:
            enemy_attackers_very_close = enemies.filter(
                lambda unit: unit.can_attack_air and ally.target_in_range(unit, bonus_distance=-1)
            )
        else:
            enemy_attackers_very_close = enemies.filter(
                lambda unit: unit.can_attack_ground and ally.target_in_range(unit, bonus_distance=-1)
            )

        if ally.weapon_cooldown != 0 and enemy_attackers_very_close.amount != 0:
            retreat_points = neighbors_8(ally.position, distance=2) | neighbors_8(ally.position, distance=4)
            if not ally.is_flying:
                retreat_points = {x for x in retreat_points if self.in_pathing_grid(x)}
            retreat_points = {
                x for x in retreat_points if enemy_attackers_very_close.closest_to(x).distance_to(x) > 3
            }

            if not retreat_points:
                closest_enemy = enemy_attackers_very_close.closest_to(ally)
                if can_attack:
                    ally.attack(closest_enemy.position)
                    return True
                return False

            closest_enemy = enemy_attackers_very_close.closest_to(ally)
            retreat_point = max(
                retreat_points, key=lambda x: x.distance_to(closest_enemy) - x.distance_to(ally)
            )

            if enemy_attackers_very_close.closest_to(retreat_point).distance_to(retreat_point) < 4 and can_attack:
                ally.attack(closest_enemy.position)
                return True
            else:
                ally.move(retreat_point)
                return True

        return False

    async def unit_kite_in(self, ally, enemies=None):
        if enemies is None:
            enemies = self.enemy_units | self.enemy_structures

        enemy_units_target = await self.unit_attack_list(ally, enemies)

        if enemy_units_target is not None and enemy_units_target.amount != 0:
            closest_enemy = enemy_units_target.closest_to(ally)
            ally.move(closest_enemy.position)
            return True

        return False

    async def micro_in_battle_combat(self):
        ally_units_controllable = self.units.of_type(self.army.ARMY_IDS_COMBAT)

        if ally_units_controllable.amount == 0:
            return

        enemies = self.enemy_units | self.enemy_structures
        enemy_attackers = enemies.filter(lambda unit: unit.can_attack)

        if enemy_attackers.amount == 0:
            return

        for ally in ally_units_controllable:
            if await self.unit_attack(ally, enemies):
                continue

            if await self.unit_retreat(ally, enemies):
                continue

            if await  self.unit_kite_back(ally, enemies):
                continue

            if await self.unit_kite_in(ally, enemies):
                continue

    async def micro_in_battle_caster(self):
        ally_units_controllable = self.units.of_type(self.army.ARMY_IDS_CASTER)

        if ally_units_controllable.amount == 0:
            return

        enemies = self.enemy_units
        enemy_attackers = enemies.filter(lambda unit: unit.can_attack)

        if enemy_attackers.amount == 0:
            return

        for ally in ally_units_controllable:
            if await self.unit_retreat(ally, enemies, can_attack=False):
                continue

            if await self.unit_kite_back(ally, enemies, can_attack=False):
                continue

            if await self.unit_kite_in(ally, enemies):
                continue

    async def micro_in_battle_spawns(self):
        ally_units_controllable = self.units.of_type(self.army.ARMY_IDS_SPAWNS)

        if ally_units_controllable.amount == 0:
            return

        enemies = self.enemy_units | self.enemy_structures
        enemy_attackers = enemies.filter(lambda unit: unit.can_attack)

        if enemy_attackers.amount == 0:
            return

        for ally in ally_units_controllable:
            if await self.unit_attack(ally, enemies):
                continue

            targets = await self.unit_attack_list(ally, enemies)

            if await self.unit_kite_in(ally, targets):
                continue

    async def scout(self):

        if self.time == 0:
            for el in self.enemy_start_locations:
                x, y = self.game_info.map_center.x, self.game_info.map_center.y
                el_x, el_y = el
                el = Point2((el_x + (x - el_x) * 0.15, el_y + (y - el_y) * 0.15))

                set_exp = set(self.expansion_locations_list)
                set_exp.remove(self.enemy_start_locations[0])
                pos = self.enemy_start_locations[0].closest(set_exp)
                await self.add_scout_task([el, pos])

        await self.scout_exec()

    async def add_scout_task(self, points, unit_type=OVERLORD):
        for unit in self.units(unit_type).closest_n_units(points[0], 10).filter(
                lambda unit: unit.health_percentage > 0.70
        ):
            if unit.tag not in self.scouting_task_dict.keys():
                self.scouting_task_dict[unit.tag] = points
                return

    async def scout_exec(self):

        free_task = []
        for tag, target_points in self.scouting_task_dict.items():
            unit = self.units.find_by_tag(tag)

            if unit is None or (unit.is_idle and len(target_points) == 0) or unit.health_percentage < 1 / 5:
                free_task.append(tag)
                continue

            if unit.is_idle:
                target_point = target_points[0]
                unit.move(target_point)
                self.scouting_task_dict[tag] = target_points[1:]

        for tag in free_task:
            self.units.find_by_tag(tag).move(self.own_bases[0])
            del self.scouting_task_dict[tag]

    async def micro_in_battle_scouts(self):
        ally_units_controllable = self.units.tags_in([k for k in self.scouting_task_dict.keys()])

        if ally_units_controllable.amount == 0:
            return

        enemies = self.enemy_units
        enemy_attackers = enemies.filter(lambda unit: unit.can_attack)

        if enemy_attackers.amount == 0:
            return

        for ally in ally_units_controllable:
            enemy_attackers_close = enemy_attackers.filter(
                lambda unit: unit.distance_to(ally) < 20
            )

            if enemy_attackers_close.amount == 0:
                continue

            if ally.is_flying:
                enemy_attackers_close = enemy_attackers_close.filter(
                    lambda unit: unit.can_attack_air
                )
            else:
                enemy_attackers_close = enemy_attackers_close.filter(
                    lambda unit: unit.can_attack_ground
                )

            # Retreat
            if enemy_attackers_close.amount:
                retreat_points = neighbors_8(ally.position, distance=2) | neighbors_8(ally.position, distance=4)
                if not ally.is_flying:
                    retreat_points = {x for x in retreat_points if self.in_pathing_grid(x)}

                if not retreat_points:
                    continue

                closest_enemy = enemy_attackers_close.closest_to(ally)
                retreat_point = closest_enemy.position.furthest(retreat_points)
                ally.move(retreat_point)
                continue

            # Return to close battle
            if enemy_attackers_close.amount != 0:
                closest_enemy = enemy_attackers_close.closest_to(ally)
                ally.move(closest_enemy.position)
                continue

    async def defend(self):
        # face urat daca e atack de air !
        under_attack = False

        detected_enemy = set()

        if self.time > 0:
            all_army = self.units(set(self.army.ARMY_IDS_COMBAT)).ready
            for base in self.own_bases_ready:
                pos = base.position
                target = self.enemy_units.closer_than(30, pos).tags_not_in(detected_enemy)
                detected_enemy |= {t.tag for t in target}

                if target.amount != 0:
                    under_attack = True
                    defensive_force = []
                    no_army_left = False
                    while self.better_army(defensive_force, target, []) <= 1.1 and not no_army_left:
                        if all_army.amount == 0:
                            no_army_left = True
                        else:
                            helpers = all_army.closest_n_units(pos, 5)
                            all_army = all_army.tags_not_in(
                                [x for x in self.units_task.keys() if self.units_task[x] == DEFENDING])
                            defensive_force += helpers

                    local_drones = self.units(DRONE).closer_than(10, pos)
                    if no_army_left:

                        for drone in local_drones:
                            if self.better_army(defensive_force, target, []) >= 1:
                                break
                            if drone.distance_to(target.first) <= 9:
                                defensive_force.append(drone)

                    if self.better_army(defensive_force, target, []) >= 0.50:
                        for unit in defensive_force:
                            unit.attack(target.first.position)
                            self.units_task[unit.tag] = DEFENDING
                    # else:
                    #     for drone in local_drones:
                    #         drone.move(self.game_info.player_start_location)

        self.defending = under_attack

        if not under_attack:
            for tag, task in self.units_task.items():
                if task == DEFENDING:
                    unit = self.units.find_by_tag(tag)
                    if unit is not None:
                        unit.stop()
                    self.units_task[tag] = IDLE
