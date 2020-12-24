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
        self.MAX_WORKERS = 60
        self.era = EARLY_GAME
        self.own_bases = []
        self.nr_bases = 0
        self.first_expansion_done = False
        self.save_for_first_expansion = False
        self.save_for_spawning_pool = False
        self.MORPH_FROM_IDS = [LARVA, ZERGLING, LARVA, ROACH, LARVA]
        self.ARMY_IDS = [ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK]
        self.ARMY_IDS_RANGED = [ROACH, RAVAGER, HYDRALISK]
        self.FREQUENCES = {
            ZERGLING: 0,
            BANELING: 1,
            ROACH: 20,
            RAVAGER: 3,
            HYDRALISK: 10
        }
        self.expansion_locations_list = []

        self.positions_with_creep = []
        self.positions_without_creep = []
        # self.FREQUENCES = [0, 0, 1, 100, 0]

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
        }

        self.unit_in_queue = False
        self.selected_unit_index_in_queue = None

        self.creep_target_distance = 15
        self.used_creep_tumors = set()

        self.unit_table = UnitTable()

    def get_priority(self, unit_id):
        chance = np.random.random_sample()
        required_chance = 2 ** (-self.build_priorities[unit_id])
        return chance < required_chance

    def on_start(self):
        self.expansion_locations_list = []
        for el in self.expansion_locations:
            self.expansion_locations_list.append(el)

    async def on_step(self, iteration):
        await self.update_state()

        await self.first_expand()
        await self.expand()
        if self.nr_bases:
            await self.distribute_workers()
            if not self.save_for_first_expansion and not self.save_for_spawning_pool:
                await self.build_overlords()
                await self.build_drones()
            await self.build_buildings()
            await self.build_queens()
            await self.build_units_probabilistic()
            await self.handle_micro()

    async def build_buildings(self):
        await self.build_extractors()
        await self.build_building(SPAWNINGPOOL, self.own_bases[0])
        if self.FREQUENCES[ZERGLING] != 0 and self.FREQUENCES[BANELING] != 0:
            await self.build_building(BANELINGNEST, self.own_bases[0], start_time=int(4.5 * 60))
        await self.build_building(ROACHWARREN, self.own_bases[0], start_time=int(1.5 * 60))
        await self.build_building(EVOLUTIONCHAMBER, self.own_bases[0], start_time=int(4.5 * 60),
                                  required_amount=self.era)
        await self.build_building(HYDRALISKDEN, self.own_bases[0], start_time=5 * 60)
        await self.all_upgrades(EVOLUTIONCHAMBER, exception_id_list=[RESEARCH_ZERGMELEEWEAPONSLEVEL1])
        await self.all_upgrades(ROACHWARREN)
        await self.build_building(LAIR, self.own_bases[0], start_time=5 * 60)
        await self.upgrade(self.own_bases[0], RESEARCH_BURROW)

    async def handle_micro(self):
        await self.queens_inject()
        await self.attack_enemy()
        await self.building_cancel_micro()
        await self.expand_creep_by_queen()
        await self.expand_creep_by_tumor()
        await self.micro_in_battle()
        await self.army_cast_skills()

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

        if self.era == EARLY_GAME:
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
                "UPGRADES": 4,
            }
        elif self.era == MID_GAME:
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
                "UPGRADES": 0,
            }
        else:
            self.build_priorities = {
                DRONE: 2,
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
            }

        if self.units(DRONE).amount < 50 and self.era >= MID_GAME:
            self.build_priorities[DRONE] = 0
            self.build_priorities["ARMY"] = 2

        # await self.chat_send(str(self.save_for_first_expansion) + " | " + str(self.save_for_spawning_pool))

    async def build_drones(self):
        if not self.get_priority(DRONE):
            return

        nr_drones = len(self.units(DRONE))

        nr_ideal_workers = 0
        for base in self.units(HATCHERY).ready | self.units(LAIR) | self.units(HIVE):
            nr_ideal_workers += base.ideal_harvesters

        if nr_drones + self.already_pending(DRONE) < nr_ideal_workers and nr_drones < self.MAX_WORKERS:
            larvae = self.units(LARVA).ready

            if self.can_afford(DRONE) and larvae.exists:
                await self.do(larvae.random.train(DRONE))

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
                await self.do(larvae.random.train(OVERLORD))

    async def build_building(self, building_id, chosen_base, required_amount=1, start_time=0):
        if not self.get_priority(building_id):
            return

        if not (self.already_pending(HATCHERY) or self.nr_bases >= 2):
            return

        if self.time < start_time:
            return

        if building_id == ROACHWARREN and self.units(SPAWNINGPOOL).ready.amount < 1:
            return

        if building_id == BANELINGNEST and self.units(SPAWNINGPOOL).ready.amount < 1:
            return

        if building_id == HYDRALISKDEN and self.units(LAIR).ready.amount < 1:
            return

        if self.can_afford(building_id) and self.already_pending(building_id) \
                + self.units(building_id).filter(
            lambda structure: structure.type_id == building_id and structure.is_ready
        ).amount < required_amount:
            map_center = self.game_info.map_center
            position_towards_map_center = chosen_base.position.towards(map_center, distance=5)

            if building_id == LAIR:
                await self.evolve_units(HATCHERY, LAIR)
            else:
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
        if not self.get_priority(QUEEN):
            return

        if len(self.units(SPAWNINGPOOL).ready) == 0:
            return

        nr_demanded_queens = [self.nr_bases + 1, self.nr_bases * 1 + 2, self.nr_bases * 1 + 2]
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
                await self.expand_now(max_distance=0)

    async def expand(self):
        if not self.get_priority("EXPAND"):
            return

        nr_drones = len(self.units(DRONE))

        nr_ideal_workers = 0
        for base in self.units(HATCHERY).ready | self.units(LAIR) | self.units(HIVE):
            nr_ideal_workers += base.ideal_harvesters
        nr_desired_drones = nr_ideal_workers * 0.7

        nr_bases = (self.units(HATCHERY) | self.units(LAIR) | self.units(HIVE)).amount

        if nr_bases > NR_EARLY_OPTIMAL_BASES and nr_drones < nr_desired_drones:
            return

        if nr_bases < (self.time / 80) and self.can_afford(HATCHERY):
            await self.expand_now(max_distance=0)

    async def evolve_units(self, from_id, morph_id, time=0):
        if self.time < time:
            return False

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

        if self.supply_army - self.units(QUEEN).amount * 2 < 1:
            target = self.known_enemy_units
            if len(target):
                target = target.random.position

                bases = self.units(HATCHERY).ready | self.units(LAIR) | self.units(HIVE)

                for base in bases:
                    if base.distance_to(target) <= 20:
                        for creature in army_units.idle:
                            await self.do(creature.attack(target))
                #
                # if self.start_location.distance2_to(target) <= \
                #   self.start_location.distance2_to(self.game_info.map_center):
                #     for creature in army_units.idle:
                #         await self.do(creature.attack(target))

            else:
                # If there are no threats
                target = self.game_info.map_center
                for creature in army_units.idle.further_than(10, self.game_info.map_center):
                    await self.do(creature.attack(target))

            return

        target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position

        for creature in army_units.idle:
            await self.do(creature.attack(target))

    async def build_units_probabilistic(self):
        if not self.get_priority("ARMY"):
            return

        if self.unit_in_queue:
            i = self.selected_unit_index_in_queue
            morph_from_id = self.MORPH_FROM_IDS[i]
            army_id = self.ARMY_IDS[i]
            if await self.evolve_units(morph_from_id, army_id):
                self.unit_in_queue = False
                self.selected_unit_index_in_queue = None

        else:
            # [ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK]

            can_make = dict()
            if self.units(SPAWNINGPOOL).ready.amount > 0:
                can_make[ZERGLING] = True

            if self.units(BANELINGNEST).ready.amount > 0 and self.units(ZERGLING).amount > 0:
                can_make[BANELING] = True

            if self.units(ROACHWARREN).ready.amount > 0:
                can_make[ROACH] = True
                if self.units(ROACH).amount > 0:
                    can_make[RAVAGER] = True

            if self.units(HYDRALISKDEN).ready.amount > 0:
                can_make[HYDRALISK] = True

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

    async def ravager_corrosive_bile(self):
        for ravager in self.units(RAVAGER):
            abilities = await self.get_available_abilities(ravager)
            if EFFECT_CORROSIVEBILE not in abilities:
                continue

            possible_targets = self.known_enemy_units.closer_than(9, ravager)
            if possible_targets.amount == 0:
                continue

            target = possible_targets.closest_to(ravager)
            if target is None:
                continue

            await self.do(ravager(EFFECT_CORROSIVEBILE, target.position))

    async def roach_burrow(self):
        for roach in self.units(ROACH):
            if roach.health_percentage > 2 / 5:
                continue

            abilities = await self.get_available_abilities(roach)
            if BURROWDOWN_ROACH not in abilities:
                continue

            await self.do(roach(BURROWDOWN_ROACH))

        for roach in self.units(ROACHBURROWED):
            abilities = await self.get_available_abilities(roach)
            if BURROWUP_ROACH not in abilities:
                continue

            if roach.health_percentage > 4 / 5:
                await self.do(roach(BURROWUP_ROACH))

    async def all_upgrades(self, building_id, time=0, exception_id_list=None):
        # useless_abilities = {CANCEL_BUILDINPROGRESS, CANCEL_QUEUE5, RALLY_HATCHERY_UNITS,
        #                      RALLY_HATCHERY_WORKERS, SMART, TRAINQUEEN_QUEEN}

        if exception_id_list is None:
            exception_id_list = []

        buildings = self.units(building_id).ready
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
                await self.do(building(research_id))
                await self.chat_send(f"Researching: {str(research_id)}")

    async def building_cancel_micro(self):
        for building in self.units.structure.not_ready.filter(
                lambda x: x.health_percentage + 0.05 < x.build_progress and x.health_percentage < 0.1
        ):
            await self.do(building(CANCEL))

    async def update_creep_overage(self, step_size=None):
        if step_size is None:
            step_size = self.creep_target_distance
        ability = self._game_data.abilities[ZERGBUILD_CREEPTUMOR.value]

        positions = [Point2((x, y)) \
                     for x in range(self._game_info.playable_area[0] + step_size,
                                    self._game_info.playable_area[0] + self._game_info.playable_area[2] - step_size,
                                    step_size) \
                     for y in range(self._game_info.playable_area[1] + step_size,
                                    self._game_info.playable_area[1] + self._game_info.playable_area[3] - step_size,
                                    step_size)]

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

        positions = [pos for pos in positions if get_closest_distance(self.expansion_locations_list, pos) > 4]

        valid_placements = await self._client.query_building_placement(ability, positions)

        valid_placements = [p for index, p in enumerate(positions) if valid_placements[index] == ActionResult.Success]

        all_tumors = self.units(CREEPTUMOR) | self.units(CREEPTUMORBURROWED) | self.units(CREEPTUMORQUEEN)
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

                await self.do(queen(BUILD_CREEPTUMOR_QUEEN, loc))
                break

    async def expand_creep_by_tumor(self):
        all_tumors = self.units(CREEPTUMOR) | self.units(CREEPTUMORBURROWED) | self.units(CREEPTUMORQUEEN)

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

                await self.do(tumor(BUILD_CREEPTUMOR_TUMOR, loc))
                new_tumors_positions.add((tumor.position.x, tumor.position.y))
                self.used_creep_tumors.add(tumor.tag)
                break

    def better_army(self, ally_army, enemy_army):
        score_ally = 0
        for ally in ally_army:
            if ally.type_id in self.unit_table.unit_power:
                score_ally += self.unit_table.unit_power[ally.type_id]

        score_enemy = 0
        for enemy in enemy_army:
            if enemy.type_id in self.unit_table.unit_power:
                score_enemy += self.unit_table.unit_power[enemy.type_id]

        return score_ally > score_enemy

    async def micro_in_battle(self):
        ally_units = self.units.of_type(self.ARMY_IDS)

        if ally_units.amount == 0:
            return

        enemies = self.known_enemy_units
        enemy_attackers = enemies.filter(lambda unit: unit.can_attack)

        if enemy_attackers.amount == 0:
            return

        for ally in ally_units:
            enemy_attackers_close = enemy_attackers.filter(
                lambda unit: unit.distance_to(ally) < 15
            )

            if enemy_attackers_close.amount == 0:
                continue

            ally_army_close = ally_units.filter(
                lambda unit: unit.distance_to(ally) < 15
            )

            # Retreat
            if not self.better_army(ally_army_close, enemy_attackers_close) and \
                    self.supply_army < 100 and self.minerals < 1000:

                retreat_points = neighbors_8(ally.position, distance=2) | neighbors_8(ally.position, distance=4)

                # Filter points that are pathable
                retreat_points = {x for x in retreat_points if self.in_pathing_grid(x)}

                if not retreat_points:
                    continue

                closest_enemy = enemy_attackers_close.closest_to(ally)
                retreat_point = closest_enemy.position.furthest(retreat_points)
                await self.do(ally.move(retreat_point))
                continue

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
                attackable_unit_targets = enemy_units_target.filter(lambda unit: unit.can_be_attacked)
                if attackable_unit_targets.amount != 0:
                    lowest_unit_target = attackable_unit_targets.sorted(
                        lambda unit: unit.health_percentage and unit.is_structure
                    )[0]
                    await self.do(ally.attack(lowest_unit_target))
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
                retreat_points = {x for x in retreat_points if self.in_pathing_grid(x)}

                if not retreat_points:
                    continue

                closest_enemy = enemy_attackers_very_close.closest_to(ally)
                retreat_point = max(
                    retreat_points, key=lambda x: x.distance_to(closest_enemy) - x.distance_to(ally)
                )
                await self.do(ally.move(retreat_point))
                continue

            # Return to close battle
            if enemy_units_target is not None and enemy_units_target.amount != 0:
                closest_enemy = enemy_units_target.closest_to(ally)
                await self.do(ally.move(closest_enemy.position))
                continue
