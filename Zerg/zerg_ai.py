from all_imports_packages import *
from Zerg.unit_table import *


def get_positions_around_unit(unit, min_range=0, max_range=500, step_size=1, location_amount=32):
    loc = unit.position.to2

    positions = []
    for alpha in range(location_amount):
        for distance in range(min_range, max_range + 1, step_size):
            positions.append(
                Point2(
                    (
                        loc.x + distance * math.cos(math.pi * 2 * alpha / location_amount),
                        loc.y + distance * math.sin(math.pi * 2 * alpha / location_amount)
                    )
                )
            )
    return positions


def get_closest_distance(locations, point):
    distances = []
    for loc in locations:
        distances.append(point.distance_to(loc))
    return min(distances)


def neighbors_4(position, distance=1):
    p = position
    d = distance
    return {Point2((p.x - d, p.y)), Point2((p.x + d, p.y)), Point2((p.x, p.y - d)), Point2((p.x, p.y + d))}


def neighbors_8(position, distance=1):
    p = position
    d = distance
    return neighbors_4(position, distance) | {
        Point2((p.x - d, p.y - d)),
        Point2((p.x - d, p.y + d)),
        Point2((p.x + d, p.y - d)),
        Point2((p.x + d, p.y + d)),
    }


class ZergAI(sc2.BotAI):
    def __init__(self):
        self.MAX_WORKERS = 70
        self.era = EARLY_GAME

        self.own_bases = []
        self.own_bases_ready = []
        self.nr_bases = 0

        self.first_expansion_done = False
        self.save_for_first_expansion = False
        self.save_for_spawning_pool = False

        self.MORPH_FROM_IDS = [
            LARVA, ZERGLING, LARVA, ROACH, LARVA, LARVA, LARVA, HYDRALISK, LARVA, LARVA, CORRUPTOR, LARVA
        ]
        self.ARMY_IDS = [
            ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK, INFESTOR, SWARMHOSTMP, LURKERMP, MUTALISK, CORRUPTOR,
            BROODLORD, ULTRALISK
        ]
        self.ARMY_IDS_RANGED = [ROACH, RAVAGER, HYDRALISK, LURKERMP, MUTALISK, CORRUPTOR, BROODLORD]
        self.ARMY_IDS_COMBAT = [
            ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK, LURKERMP, MUTALISK, CORRUPTOR, BROODLORD, ULTRALISK
        ]
        self.ARMY_IDS_CASTER = [INFESTOR, SWARMHOSTMP]
        self.ARMY_IDS_SPAWNS = [BROODLING, LOCUSTMP, LOCUSTMPFLYING]

        self.ARMY_CASTER_MINIMUM_ENERGY = {
            INFESTOR: 75,
            SWARMHOSTMP: 0,
        }

        self.UNTARGETABLE_IDS = {ADEPTPHASESHIFT}

        self.FREQUENCES = {
            ZERGLING: 2,
            BANELING: 1,
            ROACH: 20,
            RAVAGER: 4,
            HYDRALISK: 10,
            INFESTOR: 4,
            SWARMHOSTMP: 3,
            LURKERMP: 5,
            MUTALISK: 10,
            CORRUPTOR: 10,
            BROODLORD: 10,
            ULTRALISK: 4,
        }

        self.expansion_locations_list_own = []

        self.positions_with_creep = []
        self.positions_without_creep = []

        self.build_priorities = {
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

        self.unit_in_queue = False
        self.selected_unit_index_in_queue = None

        self.creep_target_distance = 15
        self.used_creep_tumors = set()

        self.unit_table = UnitTable()

        self.cached_enemy_units = dict()  # {init.tag : (unit.pos. unit.type_id)}
        self.enemy_units_not_visible = []

        self.throw_army = False
        self.throw_army_timer = 0

        self.resource_ratio = 2  # Minerals / Gas

        # self.unit_command_uses_self_do = True

    def get_priority(self, unit_id):
        chance = np.random.random_sample()
        required_chance = 2 ** (-self.build_priorities[unit_id])
        return chance < required_chance

    async def on_start(self):
        self.expansion_locations_list_own = []
        for el in self.expansion_locations_list:
            self.expansion_locations_list_own.append(el)

    async def on_step(self, iteration):
        await self.update_state()
        await self.first_expand()
        await self.expand()
        if self.nr_bases:
            if self.time < 7 * 60 or self.minerals / (self.vespene + EPSILON) < self.resource_ratio:
                await self.distribute_workers()
            else:
                await self.distribute_workers_fav_gas()
                await self.manage_idle_drones()
            if not self.save_for_first_expansion and not self.save_for_spawning_pool:
                await self.build_drones()
                await self.build_overlords()
            await self.build_buildings()
            await self.build_queens()
            await self.build_units_probabilistic()
            await self.handle_micro()

    async def build_buildings(self):
        # Essentials
        await self.build_extractors()
        await self.build_building(SPAWNINGPOOL, self.own_bases_ready[0])

        # Early Game
        if self.FREQUENCES[ZERGLING] and self.FREQUENCES[BANELING]:
            await self.build_building(BANELINGNEST, self.own_bases_ready[0], start_time=int(3.5 * 60))

        if self.FREQUENCES[ROACH]:
            await self.build_building(ROACHWARREN, self.own_bases_ready[0])
            await self.all_upgrades(ROACHWARREN)

        await self.build_building(EVOLUTIONCHAMBER, self.own_bases_ready[0], required_amount=self.era)
        if self.time < 8*60:
            await self.all_upgrades(EVOLUTIONCHAMBER, exception_id_list=[RESEARCH_ZERGMELEEWEAPONSLEVEL1])
        else:
            await self.all_upgrades(EVOLUTIONCHAMBER)

        await self.upgrade(self.own_bases_ready[0], RESEARCH_BURROW, time=4 * 60)

        # Mid Game
        await self.build_building(LAIR, self.own_bases_ready[0])

        if self.FREQUENCES[HYDRALISK]:
            await self.build_building(HYDRALISKDEN, self.own_bases_ready[0])
            await self.all_upgrades(HYDRALISKDEN)

        if self.FREQUENCES[HYDRALISK] and self.FREQUENCES[LURKERMP]:
            await self.build_building(LURKERDENMP, self.own_bases_ready[0])
            await self.all_upgrades(LURKERDENMP)

        # if self.FREQUENCES[INFESTOR] or self.FREQUENCES[SWARMHOSTMP]:
        await self.build_building(INFESTATIONPIT, self.own_bases_ready[0])

        if self.FREQUENCES[MUTALISK] or self.FREQUENCES[CORRUPTOR]:
            await self.build_building(SPIRE, self.own_bases_ready[0], required_amount=2)
            await self.all_upgrades(SPIRE)

        # Late Game
        await self.build_building(HIVE, self.own_bases_ready[0])

        if self.FREQUENCES[CORRUPTOR] and self.FREQUENCES[BROODLORD]:
            await self.build_building(GREATERSPIRE, self.own_bases_ready[0])
            await self.all_upgrades(GREATERSPIRE)

        if self.FREQUENCES[ULTRALISK]:
            await self.build_building(ULTRALISKCAVERN, self.own_bases_ready[0])
            await self.all_upgrades(ULTRALISKCAVERN)

    async def handle_micro(self):
        await self.queens_inject()
        await self.attack_enemy()
        await self.building_cancel_micro()
        await self.expand_creep_by_queen()
        await self.expand_creep_by_tumor()
        await self.micro_in_battle_combat()
        await self.micro_in_battle_caster()
        await self.micro_in_battle_spawns()
        await self.army_cast_skills()

    async def update_state(self):
        if self.time < 4 * 60:
            self.era = EARLY_GAME
        elif self.time < 9 * 60:
            self.era = MID_GAME
        else:
            self.era = LATE_GAME

        self.own_bases_ready = []
        for base in self.structures(HATCHERY).ready | self.structures(LAIR) | self.structures(HIVE):
            self.own_bases_ready.append(base)

        self.own_bases = []
        for base in self.structures(HATCHERY) | self.structures(LAIR) | self.structures(HIVE):
            self.own_bases.append(base)

        self.nr_bases = len(self.own_bases_ready)

        if self.nr_bases >= 1 and self.already_pending(HATCHERY) >= 1 and not self.first_expansion_done:
            self.first_expansion_done = True
            self.save_for_first_expansion = False
            self.save_for_spawning_pool = True

        if self.already_pending(SPAWNINGPOOL) and self.save_for_spawning_pool:
            self.save_for_spawning_pool = False

        if self.era == EARLY_GAME:
            self.resource_ratio = 2
            self.build_priorities = {
                DRONE: 0,
                "ARMY": 4,
                SPAWNINGPOOL: 0,
                ROACHWARREN: 2,
                BANELINGNEST: 2,
                "EXPAND": 2,
                OVERLORD: 0,
                QUEEN: 1,
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
            self.resource_ratio = 1
            self.build_priorities = {
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
            self.resource_ratio = 1
            self.build_priorities = {
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

        if self.units(DRONE).amount < 50 and self.era >= MID_GAME:
            self.build_priorities[DRONE] = 0
            self.build_priorities["ARMY"] = 2

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

    async def on_unit_destroyed(self, unit_tag: int):
        if unit_tag in self.cached_enemy_units:
            self.cached_enemy_units.pop(unit_tag)

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

    async def build_building(self, building_id, chosen_base, required_amount=1, start_time=0):
        if not self.get_priority(building_id):
            return

        if not (self.already_pending(HATCHERY) or self.nr_bases >= 2):
            return

        if self.time < start_time:
            return

        if building_id == ROACHWARREN and self.structures(SPAWNINGPOOL).ready.amount < 1:
            return

        if building_id == BANELINGNEST and self.structures(SPAWNINGPOOL).ready.amount < 1:
            return

        if building_id == LAIR and self.structures(HATCHERY).ready.amount < 1:
            return

        if building_id == LAIR and self.structures(HIVE).amount >= 1:
            return

        if building_id == HYDRALISKDEN and self.structures(LAIR).ready.amount + self.structures(HIVE).amount < 1:
            return

        if building_id == INFESTATIONPIT and self.structures(LAIR).ready.amount + self.structures(HIVE).amount < 1:
            return

        if building_id == LURKERDENMP and self.structures(LAIR).ready.amount + self.structures(HIVE).amount < 1:
            return

        if building_id == LURKERDENMP and self.structures(HYDRALISKDEN).ready.amount < 1:
            return

        if building_id == SPIRE and self.structures(LAIR).ready.amount + self.structures(HIVE).amount < 1:
            return

        if building_id == SPIRE and self.structures(GREATERSPIRE).amount + self.structures(SPIRE).amount >= required_amount:
            return

        if building_id == HIVE and self.structures(LAIR).ready.amount < 1:
            return

        if building_id == GREATERSPIRE and self.structures(HIVE).ready.amount < 1:
            return

        if building_id == GREATERSPIRE and self.structures(SPIRE).ready.amount < 1:
            return

        if building_id == ULTRALISKCAVERN and self.structures(HIVE).ready.amount < 1:
            return

        if self.can_afford(building_id) and self.already_pending(building_id) \
                + self.structures(building_id).filter(
            lambda structure: structure.type_id == building_id and structure.is_ready
        ).amount < required_amount:
            map_center = self.game_info.map_center
            position_towards_map_center = chosen_base.position.towards(map_center, distance=5)

            if building_id == LAIR:
                await self.evolve_units(HATCHERY, LAIR)
            elif building_id == HIVE:
                await self.evolve_units(LAIR, HIVE)
            elif building_id == GREATERSPIRE:
                await self.evolve_units(SPIRE, GREATERSPIRE)
            else:
                await self.build(building_id, near=position_towards_map_center, placement_step=1)

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

    async def build_extractors(self):
        if len(self.structures(SPAWNINGPOOL)) == 0:
            return

        for hatchery in self.own_bases:
            drones = self.units(DRONE)
            if len(drones) == 0:
                continue

            if self.units(DRONE).closer_than(7, hatchery).amount < 8 and self.time < 6 * 60:
                continue

            vespenes = self.vespene_geyser.closer_than(10.0, hatchery)

            for vespene in vespenes:
                if not self.can_afford(EXTRACTOR):
                    break

                if self.structures(EXTRACTOR).closer_than(1.0, vespene).amount:
                    break

                if self.already_pending(EXTRACTOR) >= 2:
                    break

                worker = self.select_build_worker(vespene.position)
                if worker is None:
                    break

                worker.build_gas(vespene)

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
        army_units = self.units.of_type(self.ARMY_IDS)

        if self.supply_army - self.units(QUEEN).amount * 2 < 1:
            target = self.enemy_units
            if len(target):
                target = target.random.position

                bases = self.structures(HATCHERY).ready | self.structures(LAIR) | self.structures(HIVE)

                for base in bases:
                    if base.distance_to(target) <= 20:
                        for creature in army_units.idle:
                            creature.attack(target)
                #
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

        for creature in army_units.idle:
            creature.attack(target)

    async def build_units_probabilistic(self):
        if self.minerals < 100:
            return

        if not self.get_priority("ARMY"):
            return

        if self.unit_in_queue:
            i = self.selected_unit_index_in_queue
            morph_from_id = self.MORPH_FROM_IDS[i]

            if morph_from_id != LARVA and self.units(morph_from_id).amount == 0:
                self.unit_in_queue = False
                self.selected_unit_index_in_queue = None

            army_id = self.ARMY_IDS[i]
            if await self.evolve_units(morph_from_id, army_id):
                self.unit_in_queue = False
                self.selected_unit_index_in_queue = None

        else:
            # [ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK, INFESTOR, SWARMHOST]

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
                can_make[INFESTOR] = True
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

            freq_sum = 0
            for unit in self.FREQUENCES:
                if unit in can_make:
                    freq_sum += self.FREQUENCES[unit]

            if freq_sum == 0:
                return

            probabilities = [0 for x in self.FREQUENCES]
            for i, unit in enumerate(self.FREQUENCES):
                if unit in can_make:
                    probabilities[i] = self.FREQUENCES[unit] / freq_sum

            if np.sum(probabilities) == 0:
                return

            index = np.random.choice(np.arange(0, len(probabilities)), p=probabilities)

            self.unit_in_queue = True
            self.selected_unit_index_in_queue = index

    async def army_cast_skills(self):
        await self.ravager_corrosive_bile()
        await self.roach_burrow()
        await self.infestor_fungal_growth()
        await self.swarmhost_spawn_locusts()
        await self.lurker_borrow()

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
            if ally.type_id in self.ARMY_IDS_CASTER and ally.energy < self.ARMY_CASTER_MINIMUM_ENERGY[ally.type_id]:
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

        return score_ally > score_enemy

    async def micro_in_battle_combat(self):
        ally_units = self.units.of_type(self.ARMY_IDS) | self.units.of_type(self.ARMY_IDS_SPAWNS)
        ally_units_controllable = self.units.of_type(self.ARMY_IDS_COMBAT)

        if ally_units_controllable.amount == 0:
            return

        enemies = self.enemy_units | self.enemy_structures
        enemy_attackers = enemies.filter(lambda unit: unit.can_attack)

        if enemy_attackers.amount == 0:
            return

        for ally in ally_units_controllable:
            # Attack
            enemy_ground_unit_targets = enemies.filter(
                lambda unit: ally.target_in_range(unit) and not unit.is_flying
            )

            enemy_flying_unit_targets = enemies.filter(
                lambda unit: ally.target_in_range(unit) and unit.is_flying
            )

            if ally.can_attack_both:
                enemy_units_target = enemy_ground_unit_targets | enemy_flying_unit_targets
            elif ally.can_attack_ground:
                enemy_units_target = enemy_ground_unit_targets
            elif ally.can_attack_air:
                enemy_units_target = enemy_flying_unit_targets
            else:
                enemy_units_target = None

            # Can attack
            if ally.weapon_cooldown == 0 and enemy_units_target is not None and enemy_units_target.amount != 0:
                attackable_unit_targets = enemy_units_target.filter(
                    lambda unit: unit.can_be_attacked and unit.type_id not in self.UNTARGETABLE_IDS
                )
                if attackable_unit_targets.amount != 0:
                    lowest_unit_target = attackable_unit_targets.sorted(
                        lambda unit: unit.health_percentage and unit.is_structure
                    )[0]
                    ally.attack(lowest_unit_target)
                    continue

            # Retreat
            enemy_attackers_close = enemy_attackers.filter(
                lambda unit: unit.distance_to(ally) < 20
            )

            if enemy_attackers_close.amount == 0:
                continue

            ally_army_close = ally_units.filter(
                lambda unit: unit.distance_to(ally) < 20
            )

            enemy_attackers_not_visible = filter(
                lambda unit: unit[0].distance_to(ally.position) < 20,
                self.enemy_units_not_visible
            )

            if self.throw_army:
                pass

            elif not self.better_army(ally_army_close, enemy_attackers_close, enemy_attackers_not_visible):
                retreat_points = neighbors_8(ally.position, distance=2) | neighbors_8(ally.position, distance=4)
                if not ally.is_flying:
                    retreat_points = {x for x in retreat_points if self.in_pathing_grid(x)}
                retreat_points = {
                    x for x in retreat_points if enemy_attackers_close.closest_to(x).distance_to(x) > 3
                }

                if not retreat_points:
                    closest_enemy = enemy_attackers_close.closest_to(ally)
                    ally.attack(closest_enemy.position)
                    continue

                closest_enemy = enemy_attackers_close.closest_to(ally)
                retreat_point = max(
                    retreat_points, key=lambda x: x.distance_to(closest_enemy) - x.distance_to(ally)
                )

                if enemy_attackers_close.closest_to(retreat_point).distance_to(retreat_point) < 4:
                    ally.attack(closest_enemy.position)
                    continue
                else:
                    ally.move(retreat_point)
                    continue

            # Kite Back
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
                    ally.attack(closest_enemy.position)
                    continue

                closest_enemy = enemy_attackers_very_close.closest_to(ally)
                retreat_point = max(
                    retreat_points, key=lambda x: x.distance_to(closest_enemy) - x.distance_to(ally)
                )

                if enemy_attackers_very_close.closest_to(retreat_point).distance_to(retreat_point) < 4:
                    ally.attack(closest_enemy.position)
                    continue
                else:
                    ally.move(retreat_point)
                    continue

            # Return to close battle
            if enemy_units_target is not None and enemy_units_target.amount != 0:
                closest_enemy = enemy_units_target.closest_to(ally)
                ally.move(closest_enemy.position)
                continue

    async def micro_in_battle_caster(self):
        ally_units = self.units.of_type(self.ARMY_IDS) | self.units.of_type(self.ARMY_IDS_SPAWNS)
        ally_units_controllable = self.units.of_type(self.ARMY_IDS_CASTER)

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

            ally_army_close = ally_units.filter(
                lambda unit: unit.distance_to(ally) < 20
            )

            enemy_attackers_not_visible = filter(
                lambda unit: unit[0].distance_to(ally.position) < 20,
                self.enemy_units_not_visible
            )

            # Retreat
            if not self.better_army(ally_army_close, enemy_attackers_close, enemy_attackers_not_visible):
                retreat_points = neighbors_8(ally.position, distance=2) | neighbors_8(ally.position, distance=4)
                if not ally.is_flying:
                    retreat_points = {x for x in retreat_points if self.in_pathing_grid(x)}

                if not retreat_points:
                    continue

                closest_enemy = enemy_attackers_close.closest_to(ally)
                retreat_point = closest_enemy.position.furthest(retreat_points)
                ally.move(retreat_point)
                continue

            # Kite Back
            kite_distance = 9
            if ally.is_flying:
                enemy_attackers_very_close = enemies.filter(
                    lambda unit: unit.can_attack_air and unit.distance_to(ally) < kite_distance
                )
            else:
                enemy_attackers_very_close = enemies.filter(
                    lambda unit: unit.can_attack_ground and unit.distance_to(ally) < kite_distance
                )

            if enemy_attackers_very_close.amount != 0:
                retreat_points = neighbors_8(ally.position, distance=2) | neighbors_8(ally.position, distance=4)
                if not ally.is_flying:
                    retreat_points = {x for x in retreat_points if self.in_pathing_grid(x)}

                if not retreat_points:
                    continue

                closest_enemy = enemy_attackers_very_close.closest_to(ally)
                retreat_point = max(
                    retreat_points, key=lambda x: x.distance_to(closest_enemy) - x.distance_to(ally)
                )
                ally.move(retreat_point)
                continue

            # Return to close battle
            if enemy_attackers_close.amount != 0:
                closest_enemy = enemy_attackers_close.closest_to(ally)
                ally.move(closest_enemy.position)
                continue

    async def micro_in_battle_spawns(self):
        ally_units_controllable = self.units.of_type(self.ARMY_IDS_SPAWNS)

        if ally_units_controllable.amount == 0:
            return

        enemies = self.enemy_units | self.enemy_structures
        enemy_attackers = enemies.filter(lambda unit: unit.can_attack)

        if enemy_attackers.amount == 0:
            return

        for ally in ally_units_controllable:
            # Attack
            enemy_ground_unit_targets = enemies.filter(
                lambda unit: ally.target_in_range(unit) and not unit.is_flying
            )

            enemy_flying_unit_targets = enemies.filter(
                lambda unit: ally.target_in_range(unit) and unit.is_flying
            )

            if ally.can_attack_both:
                enemy_units_target = enemy_ground_unit_targets | enemy_flying_unit_targets
            elif ally.can_attack_ground:
                enemy_units_target = enemy_ground_unit_targets
            elif ally.can_attack_air:
                enemy_units_target = enemy_flying_unit_targets
            else:
                enemy_units_target = None

            # Can attack
            if ally.weapon_cooldown == 0 and enemy_units_target is not None and enemy_units_target.amount != 0:
                attackable_unit_targets = enemy_units_target.filter(
                    lambda unit: unit.can_be_attacked and unit.type_id not in self.UNTARGETABLE_IDS
                )
                if attackable_unit_targets.amount != 0:
                    lowest_unit_target = attackable_unit_targets.sorted(
                        lambda unit: unit.health_percentage and unit.is_structure
                    )[0]
                    ally.attack(lowest_unit_target)
                    continue

            # Search nearest attackable target
            enemy_ground_unit_targets = enemies.filter(
                lambda unit: not unit.is_flying
            )

            enemy_flying_unit_targets = enemies.filter(
                lambda unit: unit.is_flying
            )

            if ally.can_attack_both:
                enemy_units_target = enemy_ground_unit_targets | enemy_flying_unit_targets
            elif ally.can_attack_ground:
                enemy_units_target = enemy_ground_unit_targets
            elif ally.can_attack_air:
                enemy_units_target = enemy_flying_unit_targets
            else:
                enemy_units_target = None

            # Return to close battle
            if enemy_units_target is not None and enemy_units_target.amount != 0:
                closest_enemy = enemy_units_target.closest_to(ally)
                ally.move(closest_enemy.position)
                continue
