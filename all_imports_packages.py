from sc2_ids import *
from global_constants import *

import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer
from sc2.constants import *

import random
import numpy as np
from bisect import bisect_left