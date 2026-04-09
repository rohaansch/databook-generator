"""
API example: generate a Device Characterization Report with a custom
'Cell Library' chapter injected between 'Overview' and 'Measurements'.

Run from this directory:
    cd example/api_example
    python generate_report.py

The script uses DatabookBuilder programmatically instead of the CLI.
All config values are plain Python dicts — no config.json required,
though this example also shows how to load one.
"""

from pathlib import Path

from databook_generator import DatabookBuilder

# ---------------------------------------------------------------------------
# Cell data — in a real workflow these would come from a database, CSV,
# or Liberty/LEF parser.  Here they are hard-coded for illustration.
# ---------------------------------------------------------------------------

CELLS = [
    {
        "name": "NAND2_X1",
        "description": "2-input NAND gate",
        "function": "ZN = !(A & B)",
        "inputs": ["A", "B"],
        "output": "ZN",
        "drive_strength": 1,
        "area_um2": 0.42,
        "leakage_nw": 3.1,
        "cin_ff": 2.4,
        "schematic": "nand2_schematic.svg",
        "timing": [
            {"arc": "A → ZN (rise)", "rise_ps": 42, "fall_ps": 38, "constraint": "—"},
            {"arc": "A → ZN (fall)", "rise_ps": 38, "fall_ps": 44, "constraint": "—"},
            {"arc": "B → ZN (rise)", "rise_ps": 45, "fall_ps": 40, "constraint": "—"},
        ],
    },
    {
        "name": "INV_X1",
        "description": "Inverter, drive strength 1",
        "function": "ZN = !A",
        "inputs": ["A"],
        "output": "ZN",
        "drive_strength": 1,
        "area_um2": 0.21,
        "leakage_nw": 1.4,
        "cin_ff": 1.2,
        "schematic": "inv_schematic.svg",
        "timing": [
            {"arc": "A → ZN (rise)", "rise_ps": 28, "fall_ps": 25, "constraint": "—"},
            {"arc": "A → ZN (fall)", "rise_ps": 25, "fall_ps": 30, "constraint": "—"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Build the report
# ---------------------------------------------------------------------------

HERE = Path(__file__).parent

builder = DatabookBuilder(
    config=HERE / "config.json",      # load standard config from JSON …
    chapters_dir=HERE / "chapters",   # … standard chapters (overview, measurements)
    images_dir=HERE / "images",
    output=HERE / "Device_Characterization_Report_with_Cells.pdf",
)

# Inject the Cell Library chapter between 'overview' and 'measurements'
builder.add_chapter(
    template_path=HERE / "templates",
    template_file="cell_library.adoc",
    variables={"cells": CELLS},
    images=[
        HERE / "templates" / "images" / "nand2_schematic.svg",
        HERE / "templates" / "images" / "inv_schematic.svg",
    ],
    after="overview",
    name="cell_library",
)

print(f"Chapter order: {builder.chapter_names}")
# → ['overview', 'cell_library', 'measurements']

pdf_path = builder.build()
print(f"Done → {pdf_path}")
