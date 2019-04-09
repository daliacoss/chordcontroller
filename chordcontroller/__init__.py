# ChordController
# Copyright (C) 2019 Decky Coss
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import math, os, shlex
import pygame, rtmidi, rtmidi.midiutil
from collections import namedtuple
from pygame.locals import *

MAJOR = 0
MINOR = 1
DIMINISHED = 2

DIMINISHED_SEVENTH = 9
MINOR_SEVENTH = 10
MAJOR_NINTH = 14

BASS_NONE = 0
BASS_ROOT = 1       # add an extra voice an octave below the root
BASS_INVERSION = 2  # add an extra voice an octave below the loLEFT note

BUTTON_A = 0
BUTTON_B = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_LB = 4
BUTTON_RB = 5
BUTTON_BACK = 6
BUTTON_START = 7
BUTTON_XBOX = 8
BUTTON_LTHUMB = 9
BUTTON_RTHUMB = 10
AXIS_RTHUMBY = 3
AXIS_RTRIGGER = 4
AXIS_LTRIGGER = 5
HAT_DPAD = 0

# MIN_TRIGGER = -1.0
# MAX_TRIGGER = 1.0
# MIN_THUMB = -1.0
# MAX_THUMB = 1.0


ScalePositionDatum = namedtuple("ScalePositionDatum", ("root_pitch", "quality"))
scale_position_data = [
    ScalePositionDatum(0, MAJOR),
    ScalePositionDatum(2, MINOR),
    ScalePositionDatum(4, MINOR),
    ScalePositionDatum(5, MAJOR),
    ScalePositionDatum(7, MAJOR),
    ScalePositionDatum(9, MINOR),
    ScalePositionDatum(11, DIMINISHED),
]

NoteOn = lambda pitch, velocity=127, channel=0: (144 + channel, pitch, velocity)
ModWheel = lambda value, channel=0: (176 + channel, 1, value)

def Chord(root, quality=MAJOR, extensions=tuple(), voicing=0):

    if quality == MINOR:
        triad = (root, root+3, root+7)
    elif quality == DIMINISHED:
        triad = (root, root+3, root+6)
    else:
        triad = (root, root+4, root+7)

    chord = triad + tuple(root + x for x in extensions)

    if voicing == 0:
        return chord

    inversion = tuple()
    for i, v in enumerate(chord):
        k = i + voicing
        octave = k // len(chord)
        inversion += (chord[k % len(chord)] + octave * 12,)

    return inversion

Vector = namedtuple("Vector", ("x", "y"))
Vector.DOWN = Vector(0,-1)
Vector.UP = Vector(0,1)
Vector.RIGHT = Vector(1,0)
Vector.LEFT = Vector(-1,0)
Vector.DOWNRIGHT = Vector(1,-1)
Vector.DOWNLEFT = Vector(-1,-1)
Vector.UPRIGHT = Vector(1,1)
Vector.UPLEFT = Vector(-1,1)
Vector.NEUTRAL = Vector(0,0)

class Instrument(object):

    def __init__(self, octave=5):
        self.octave = octave

        self._midi_device = rtmidi.MidiOut(
            name="Chord Controller",
            rtapi=rtmidi.midiutil.get_api_from_environment())
        self._midi_device.open_virtual_port()

        self._most_recent_chord = tuple()
        self._tonic = 0
        self._bass = 0

    @property
    def octave(self):
        return self._octave

    @octave.setter
    def octave(self, o):
        self._octave = int(o) % 9

    @property
    def bass(self):
        return self._bass

    @bass.setter
    def bass(self, b):
        self._bass = int(b) % 3

    @property
    def tonic(self):
        return self._tonic

    @tonic.setter
    def tonic(self, t):
        self._tonic = t

    def set_next(self, key, value):
        self._next[key] = value

    def set_next_tonic_from_sp(self, scale_position, flatten_by=0):
        spd = scale_position_data[scale_position]
        self.set_next("tonic", (self._tonic + spd.root_pitch - flatten_by) % 12)

    def commit(self, key):

        try:
            next_value = self._next[key]
        except KeyError:
            next_value = getattr(self, key)

        setattr(self, key, next_value)

    def construct_chord(self, scale_position, **modifiers):
        spd = scale_position_data[scale_position]
        root = self.tonic + (self.octave * 12) + spd.root_pitch - modifiers.get("do_flatten", 0)

        if modifiers.get("do_alter_quality_1"):
            quality = not spd.quality
        elif modifiers.get("do_alter_quality_2"):
            quality = DIMINISHED if spd.quality != DIMINISHED else MINOR
        else:
            quality = spd.quality

        e = modifiers.get("do_extension_1", 0) + modifiers.get("do_extension_2", 0)
        if e == 1:
            extensions = (MINOR_SEVENTH,)
        elif e == 2:
            if quality == DIMINISHED:
                extensions = (DIMINISHED_SEVENTH,)
            else:
                extensions = (MINOR_SEVENTH, MAJOR_NINTH)
        else:
            extensions = tuple()

        chord = Chord(root, quality, extensions=extensions, voicing=modifiers.get("voicing", 0))
        if self.bass == BASS_ROOT:
            chord += (root - 12,)
        elif self.bass == BASS_INVERSION:
            chord += (chord[0] - 12,)

        return chord

    def play_chord(self, scale_position, **modifiers):

        self.release_chord()

        chord = self.construct_chord(scale_position, **modifiers)
        velocity = 0x70 - round(modifiers.get("velocity", 0)**1.7 * 0x70)

        for voice in chord:
            self._midi_device.send_message(NoteOn(voice, velocity=velocity))
        self._most_recent_chord = chord

    def release_chord(self):
        for voice in self._most_recent_chord:
            self._midi_device.send_message(NoteOn(voice, velocity=0))

    def send_mod_wheel(self, mod_wheel):
        self._midi_device.send_message(ModWheel(int(mod_wheel * 127)))

class InputHandler(object):

    def __init__(self, mappings, axis_calibration):
        # self._instrument = instrument

        # self._joysticks = []
        self._joystick_index = -1
        self._most_recent_hat_vector = {0: Vector(0,0)}

        self.axis_calibration = axis_calibration
        self.mappings = mappings
        self.mode = "mode_default"

        self._uncalibrated_axes = set()
        for k, settings in axis_calibration.items():
            if settings.get("uncalibrated_at_start"):
                self._uncalibrated_axes.add(k)

    @property
    def joystick_index(self):
        return self._joystick_index

    def are_adjacent(self, a, b):
        
        """
        return True if vector directions are diagonally 'adjacent' to each other
        (e.g., (0,1) and (1,1))
        if vectors are equal, return False.
        if either vector is (0,0), return False.
        """

        if (0,0) in (a, b):
            return False

        diff = sorted((abs(a.x-b.x), abs(a.y-b.y)))
        return diff[0] == 0 and diff[1] == 1

    def is_cardinal(self, v):
        return 0 in v
    # 
    # def read_modifier_inputs(self):
    #     joystick = self._joysticks[self._joystick_index]
    #     min_trigger, max_trigger = self.calibration["min_trigger"], self.calibration["max_trigger"]
    # 
    #     items = tuple()
    #     for k, axis in self.mappings["axes"].items():
    #         if axis in self._uncalibrated_axes:
    #             value = 0
    #         else:
    #             value = (joystick.get_axis(axis) - min_trigger) / (max_trigger - min_trigger)
    #         items += ((k, value),)
    # 
    #     items += tuple( (k, joystick.get_button(v)) for k, v in self.mappings["momentary"].items() )
    # 
    #     return dict(items)
    # 
    # def handle_voicing_slider(self, voicing_input):
    #     for i, r in enumerate(self.mappings["voicing_ranges"]):
    #         if voicing_input <= r:
    #             break
    #     return i

    def handle_hat_motion(self, vector, modifier_inputs):
        """
        maps d-pad event to the correct Instrument method and returns that
        method, along with appropriate args and kwargs, without calling it.

        if no Instrument method should be called for this vector, returns None
        and empty arg collections.
        """

        method = None
        kwargs = {}

        if vector != (0,0):
            # don't register a d-pad press in any of the cardinal directions
            # if the most recent d-pad event was a diagonal press
            # (prevent accidentally playing the wrong chord)
            if not (self.is_cardinal(vector) and self.are_adjacent(vector, self._most_recent_hat_vector)):

                kwargs = dict(scale_position=self.mappings["scale_positions"][vector])

                if modifier_inputs["do_change_tonic"]:
                    method = self._instrument.set_next_tonic_from_sp
                    kwargs.update(flatten_by=modifier_inputs["do_flatten"])
                # elif modifier_inputs["do_change_harmony"]:
                    # method = self._instrument.set_next_
                else:
                    modifier_inputs["voicing"] = self.handle_voicing_slider(modifier_inputs["voicing"])
                    method = self._instrument.play_chord
                    kwargs.update(**modifier_inputs)
        elif not modifier_inputs["do_change_tonic"]:
            method = self._instrument.release_chord
        return method, kwargs

    def map_float_to_range(self, input_value, value_at_min, value_at_max, **data):

        if input_value < 0 or input_value > 1:
            raise ValueError("input_value must be between 0 and 1")

        if data.get("steps"):
            x = (value_at_max - value_at_min) / len(data["steps"])
            for step in steps:
                if input_value <= step:
                    return x * step + value_at_min
        else:
            return (value_at_max - value_at_min) * input_value + value_at_min

    def clamp_axis_value(self, axis_id, raw_axis_value):
        calibration = self.axis_calibration[axis_id]
        return (raw_axis_value - calibration.min) / (calibration.max - calibration.min)

    def update(self, events):
        # modifier_inputs = self.read_modifier_inputs()

        for event in events:

            try:
                joy_index = getattr(event, "joy")
            # this event does not spark joy
            except AttributeError:
                continue

            # if we're not tracking any joystick, start tracking the one for
            # this event.
            # else if we're already tracking a joystick other than this one,
            # do nothing and go to next event
            if joy_index != self._joystick_index:
                if self._joystick_index < 0 and event.type == JOYBUTTONDOWN:
                    self._joystick_index = joy_index
                continue

            # joystick = self._joysticks[self._joystick_index]
            keymap = self.mappings[self.mode]
            to_do = []
            to_undo = []

            if event.type in [JOYBUTTONDOWN, JOYBUTTONUP]:
                for data in keymap.get("buttons", {}).get(event.button, []):
                    action = data.get("action", "momentary")
                    if event.type == JOYBUTTONDOWN and action in ["momentary", "latch"]:
                        to_do.append(shlex.split(data["do"]))
                    elif event.type == JOYBUTTONUP and action == "momentary":
                        to_undo.append(shlex.split(data["do"]))

            elif event.type == JOYHATMOTION:
                most_recent_hat_vector = self._most_recent_hat_vector.get(event.hat)
                is_neutral = (event.value == Vector.NEUTRAL)
                if is_neutral:
                    if not most_recent_hat_vector:
                        self._most_recent_hat_vector[event.hat] = Vector.NEUTRAL
                        continue
                    key_vector = most_recent_hat_vector
                else:
                    key_vector = Vector(event.value)

                for data in keymap.get("hats", {}).get("{0}_{1}_{2}".format(event.hat, key_vector.x, key_vector.y), []):
                    action = data.get("action", "momentary")
                    if not is_neutral and action in ["momentary", "latch"]:
                        to_do.append(shlex.split(data["do"]))
                    elif is_neutral and action == "momentary":
                        to_undo.append(shlex.split(data["do"]))
                
                self._most_recent_hat_vector[event.hat] = Vector.NEUTRAL

            elif event.type == JOYAXISMOTION:
            
                if event.axis in self._uncalibrated_axes:
                    self._uncalibrated_axes.discard(event.axis)
                
                for data in keymap.get("axes", {}).get(event.axis):
                    processed_value = self.map_float_to_range(self.clamp_axis_value(event.value), **data)
                    if processed_value != None:
                        to_do.append(shlex.split(data["do"]) + [processed_value])

            for td in to_do:
                getattr(self._instrument, td[0])(*td[1:])
            for tu in to_undo:
                self._instrument.undo(*td)
            
            return {"to_do": to_do, "to_undo": to_undo}
