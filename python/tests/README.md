Run with real files:

    FIVEM_OPTIMIZER_FIXTURES=/path/to/folder python -m pytest python/tests -q

The folder needs `fer49p2025.ytd` (a 51-texture vehicle dictionary, 86 MiB in game) and `formula.ytd`
(a small stock-vehicle dictionary). Tests that need them skip when the variable is unset. ImageMagick
(`magick` on PATH) enables the resample tests.
