

target_file = "/Users/anzalks/PycharmProjects/Synaptipy/src/Synaptipy/application/gui/analysis_tabs/base.py"

with open(target_file, 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
preserved_indent = "        "

start_marker = "        # Get raw data from currently loaded recording (and selected channel)"
end_marker = "        except Exception as e:"

replacement = [
    "        # Get raw data from currently loaded recording (and selected channel)\n",
    "        try:\n",
    "            # FIX: Directly trigger re-plotting.\n",
    "            # This ensures we use the centralized `_plot_selected_data` logic, which:\n",
    "            # 1. Preserves Zoom (via our recent fix).\n",
    "            # 2. Applies settings to ALL traces (Context + Main) on-the-fly.\n",
    "            # 3. Respects trial selection.\n",
    "            self._plot_selected_data()\n",
    "            # Note: We return early or just let the method finish\n",
    "\n"
]

found_start = False
for i, line in enumerate(lines):
    if start_marker in line and not found_start:
        found_start = True
        skip = True
        new_lines.extend(replacement)

    if end_marker in line and skip:
        skip = False

    if not skip:
        new_lines.append(line)

with open(target_file, 'w') as f:
    f.writelines(new_lines)

print("Modification complete.")
