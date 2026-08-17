"""Browser-runnable tooling for the BME 590 PyLabRobot workshops.

This package must stay importable with no side effects: ``import
plr_workshops`` does not import frontend (and therefore pylabrobot). Import the
submodule you need explicitly::

    from plr_workshops.inline import InlineVisualizer
    from plr_workshops.frontend import build_page
    from plr_workshops.jupyterlite_bridge import patch_visualizer

This keeps the namespace browser-safe (the kernel wheel ships only
``inline``/``jupyterlite_bridge``/``transport``) and lets utilities like
``vendor.py`` run without pylabrobot.
"""

__version__ = "0.1.0"
