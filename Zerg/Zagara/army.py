from all_imports_packages import *


class Army:
    def __init__(self):
        self.MORPH_FROM_IDS = [
            LARVA, ZERGLING, LARVA, ROACH, LARVA, LARVA, LARVA, HYDRALISK, LARVA, LARVA, CORRUPTOR, LARVA,
            LARVA, OVERLORD
        ]
        self.ARMY_IDS = [
            ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK, INFESTOR, SWARMHOSTMP, LURKERMP, MUTALISK, CORRUPTOR,
            BROODLORD, ULTRALISK, VIPER, OVERSEER
        ]
        self.ARMY_IDS_RANGED = [ROACH, RAVAGER, HYDRALISK, LURKERMP, MUTALISK, CORRUPTOR, BROODLORD]
        self.ARMY_IDS_COMBAT = [
            ZERGLING, BANELING, ROACH, RAVAGER, HYDRALISK, LURKERMP, MUTALISK, CORRUPTOR, BROODLORD, ULTRALISK, QUEEN
        ]
        self.ARMY_IDS_CASTER = [INFESTOR, SWARMHOSTMP, VIPER, OVERSEER]
        self.ARMY_IDS_SPAWNS = [BROODLING, LOCUSTMP, LOCUSTMPFLYING]

        self.ARMY_CASTER_MINIMUM_ENERGY = {
            INFESTOR: 75,
            SWARMHOSTMP: 0,
            VIPER: 75,
            OVERSEER: 0,
        }

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
            VIPER: 3,
            OVERSEER: 3,
        }

        self.FREQUENCES = {
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

        self.max_units = {
            ZERGLING: INFINITE,
            BANELING: INFINITE,
            ROACH: INFINITE,
            RAVAGER: INFINITE,
            HYDRALISK: INFINITE,
            INFESTOR: 5,
            SWARMHOSTMP: 4,
            LURKERMP: INFINITE,
            MUTALISK: 7,
            CORRUPTOR: INFINITE,
            BROODLORD: INFINITE,
            ULTRALISK: INFINITE,
            VIPER: 4,
            OVERSEER: 2,
        }

        self.unit_in_queue = False
        self.selected_unit_index_in_queue = None
