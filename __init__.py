# __init__.py
###
# Copyright (c) 2024 Your Name
# Licensed under the Supybot license
###

from . import config
from . import plugin
from importlib import reload

reload(plugin)

Class = plugin.GroqWithMemory
configure = config.configure
