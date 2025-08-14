#!/usr/bin/env python3

# Generates a set of highway colors to be stored in road-colors-generated.mss.

from colormath.color_conversions import convert_color
from colormath.color_objects import LabColor, LCHabColor, sRGBColor
from colormath.color_diff import delta_e_cie2000
import argparse
import sys
import yaml

from collections import OrderedDict, namedtuple

class Color:
    """A color in the CIE lch color space."""

    def __init__(self, lch_tuple):
        self.m_lch = LCHabColor(*lch_tuple)

    def lch(self):
        return "Lch({:.0f},{:.0f},{:.0f})".format(*(self.m_lch.get_value_tuple()))

    def rgb(self):
        rgb = convert_color(self.m_lch, sRGBColor)
        if (rgb.rgb_r != rgb.clamped_rgb_r or rgb.rgb_g != rgb.clamped_rgb_g or rgb.rgb_b != rgb.clamped_rgb_b):
            raise Exception("Colour {} is outside sRGB".format(self.lch()))
        return rgb.get_rgb_hex()

    def rgb_error(self):
        return delta_e_cie2000(convert_color(self.m_lch, LabColor),
                               convert_color(sRGBColor.new_from_rgb_hex(self.rgb()), LabColor))

def load_settings():
    """Read the settings from YAML."""
    return yaml.safe_load(open('road-colors.yaml', 'r'))

def generate_colours(settings, section):
    road_classes = settings['roads']
    # How many classes define the spacing
    lock_first = int(settings.get('lock_first', len(road_classes)))
    lock_first = max(2, min(lock_first, len(road_classes)))  # clamp

    min_h = settings['hue'][0]
    max_h = settings['hue'][1]

    # Use deltas from the locked-first range
    base_divisions = lock_first - 1
    base_delta_h = (max_h - min_h) / base_divisions

    # Build per-line (fill/casing/…) L/C deltas from locked range
    classes = settings['classes'][section]
    from collections import OrderedDict, namedtuple
    ColourInfo = namedtuple("ColourInfo", ["start_l", "end_l", "start_c", "end_c"])
    line_colour_infos = OrderedDict()
    for cls, params in sorted(classes.items()):
        l = params['lightness']
        c = params['chroma']
        line_colour_infos[cls] = ColourInfo(start_l=l[0], end_l=l[1], start_c=c[0], end_c=c[1])

    # Precompute step deltas (locked)
    def locked_step(value_start, value_end):
        return (value_end - value_start) / base_divisions

    step_info = {}
    for line_name, info in line_colour_infos.items():
        step_info[line_name] = {
            'L0': info.start_l,
            'C0': info.start_c,
            'dL': locked_step(info.start_l, info.end_l),
            'dC': locked_step(info.start_c, info.end_c),
        }

    # Now produce colours for all classes by extrapolating beyond lock_first
    from collections import OrderedDict
    hues = OrderedDict()
    for i, name in enumerate(road_classes):
        if i == 0:
            hues[name] = min_h
        elif i < lock_first:
            hues[name] = (min_h + i * base_delta_h) % 360
        else:
            # extend with the same step
            hues[name] = (hues[road_classes[i-1]] + base_delta_h) % 360

    colours = OrderedDict()
    for line_name, info in line_colour_infos.items():
        colours[line_name] = OrderedDict()
        for i, name in enumerate(road_classes):
            if i < lock_first:
                L = step_info[line_name]['L0'] + i * step_info[line_name]['dL']
                C = step_info[line_name]['C0'] + i * step_info[line_name]['dC']
            else:
                # extend with same step beyond the locked range
                L = step_info[line_name]['L0'] + (lock_first - 1) * step_info[line_name]['dL'] \
                    + (i - (lock_first - 1)) * step_info[line_name]['dL']
                C = step_info[line_name]['C0'] + (lock_first - 1) * step_info[line_name]['dC'] \
                    + (i - (lock_first - 1)) * step_info[line_name]['dC']

            # Optional: gently clamp L and C to valid ranges
            L = max(0, min(100, L))
            C = max(0, min(100, C))

            colour = Color((L, C, hues[name]))
            colours[line_name][name] = colour

    return colours

def main():
    parser = argparse.ArgumentParser(description='Generates road colours')
    parser.add_argument('-v', '--verbose', dest='verbose', help='Generates information about colour differences', action='store_true', default=False)
    args = parser.parse_args()

    settings = load_settings()
    road_classes = settings['roads']
    colour_divisions = len(road_classes) - 1
    colours = generate_colours(settings, 'mss')

    # Print a warning about the nature of these definitions.
    print("/* This is generated code, do not change this file manually.          */")
    print("/*                                                                    */")
    print("/* To change these definitions, alter road-colors.yaml and run:       */")
    print("/*                                                                    */")
    print("/* scripts/generate_road_colours.py > style/road-colors-generated.mss */")
    print("/*                                                                    */")

    for line_name, line_colours in colours.items():
        for name, colour in line_colours.items():
            if args.verbose:
                line = "@{name}-{line_name}: {rgb}; // {lch}, error {delta:.1f}"
            else:
                line = "@{name}-{line_name}: {rgb};"
            print(f"@{name}-{line_name}: {colour.rgb()};")

if __name__ == "__main__":
    main()
