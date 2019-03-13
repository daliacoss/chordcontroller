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

import os, math
import pygame, rtmidi, rtmidi.midiutil
from collections import namedtuple
from pygame.locals import *

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

MIN_TRIGGER = -1.0
MAX_TRIGGER = 1.0
MIN_THUMB = -1.0
MAX_THUMB = 1.0

MAJOR = 0
MINOR = 1
DIMINISHED = 2

DIMINISHED_SEVENTH = 9
MINOR_SEVENTH = 10
MAJOR_NINTH = 14

BASS_NONE = 0
BASS_ROOT = 1       # add an extra voice an octave below the root
BASS_INVERSION = 2  # add an extra voice an octave below the lowest note

mappings = dict(
    toggle = dict(
        do_increase_octave = BUTTON_START,
        do_decrease_octave = BUTTON_BACK,
        do_change_bass = BUTTON_LTHUMB,
    ),
    momentary = dict(
        do_flatten = BUTTON_RB,
        do_extension_1 = BUTTON_X,
        do_extension_2 = BUTTON_Y,
        do_change_quality_1 = BUTTON_A,
        do_change_quality_2 = BUTTON_B,
        do_change_tonic = BUTTON_LB,
        do_activate_mod_wheel = BUTTON_RTHUMB,
    ),
    axes = dict(
        velocity = AXIS_RTRIGGER,
        voicing = AXIS_LTRIGGER,
        mod_wheel = AXIS_RTHUMBY,
    ),
    # if voicing slider value <= [0], use 1st inversion
    # else if <= [1], use 2nd inversion
    # etc
    # each number should be between 0 and 1 inclusive
    voicing_ranges = [.05, .4, .9, 1],

    # horizontal, vertical
    # 1 is up/right, -1 is down/left
    scale_positions = {
        (0, -1): 0,     # I
        (0, 1): 0,      # I
        (-1, 0): 4,     # V
        (1, 0): 3,      # IV
        (-1, -1): 5,    # vi
        (1, -1): 1,     # ii
        (-1, 1): 6,     # vii*
        (1, 1): 2       # iii
    }
)

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

class Instrument(object):

    def __init__(self, octave=5):
        self.octave = octave

        self._midi_device = rtmidi.MidiOut(
            name="Chord Controller",
            rtapi=rtmidi.midiutil.get_api_from_environment())
        self._midi_device.open_virtual_port()

        self._most_recent_chord = tuple()
        self._tonic = 0
        self._next_tonic = 0
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
        self._bass = b % 3

    @property
    def tonic(self):
        return self._tonic

    def set_next_tonic(self, scale_position, flatten_by=0):
        spd = scale_position_data[scale_position]
        self._next_tonic = (self._tonic + spd.root_pitch - flatten_by) % 12

    def commit_tonic(self):
        self._tonic = self._next_tonic

    def play_chord(self, scale_position, **modifiers):

        self.release_chord()

        spd = scale_position_data[scale_position]
        root = self.tonic + (self.octave * 12) + spd.root_pitch - modifiers.get("do_flatten", 0)

        if modifiers.get("do_change_quality_1"):
            quality = not spd.quality
        elif modifiers.get("do_change_quality_2"):
            quality = DIMINISHED if spd.quality != DIMINISHED else MINOR
        else:
            quality = spd.quality

        velocity = 0x70 - round(modifiers["velocity"]**1.7 * 0x70)

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

        for voice in chord:
            self._midi_device.send_message(NoteOn(voice, velocity=velocity))
        self._most_recent_chord = chord

    def release_chord(self):
        for voice in self._most_recent_chord:
            self._midi_device.send_message(NoteOn(voice, velocity=0))

    def send_mod_wheel(self, mod_wheel):
        self._midi_device.send_message(ModWheel(int(mod_wheel * 127)))

class App(object):

    def __init__(self):
        self._joysticks = []
        self._joystick_index = -1
        self._instrument = Instrument()
        self._most_recent_hat_vector = Vector(0,0)
        self._uncalibrated_axes = set([AXIS_RTRIGGER, AXIS_LTRIGGER])

    def setup_pygame(self):

        # set SDL to use the dummy NULL video driver, so it doesn't need a
        # windowing system.
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        # init the joystick control
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            self._joysticks.append(joy)

    @property
    def joystick_index(self):
        return self._joystick_index

    def startup_message(self):
        s = ""
        for i, joystick in enumerate(self._joysticks):
            s += "{0}\t{1}\n".format(i, joystick.get_name())
        return s + "To continue, press any button on the controller you want to use."

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

    def read_modifier_inputs(self):
        joystick = self._joysticks[self._joystick_index]

        items = tuple()
        for k, axis in mappings["axes"].items():
            if axis in self._uncalibrated_axes:
                value = 0
            else:
                value = (joystick.get_axis(axis) - MIN_TRIGGER) / (MAX_TRIGGER - MIN_TRIGGER)
            items += ((k, value),)

        items += tuple( (k, joystick.get_button(v)) for k, v in mappings["momentary"].items() )

        return dict(items)

    def handle_voicing_slider(self, voicing_input):
        for i, r in enumerate(mappings["voicing_ranges"]):
            if voicing_input <= r:
                break
        return i

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

                kwargs = dict(scale_position=mappings["scale_positions"][vector])

                if modifier_inputs["do_change_tonic"]:
                    method = self._instrument.set_next_tonic
                    kwargs.update(flatten_by=modifier_inputs["do_flatten"])
                else:
                    modifier_inputs["voicing"] = self.handle_voicing_slider(modifier_inputs["voicing"])
                    method = self._instrument.play_chord
                    kwargs.update(**modifier_inputs)
        else:
            method = self._instrument.release_chord
        return method, kwargs

    def update(self):
        modifier_inputs = self.read_modifier_inputs()

        if modifier_inputs["do_activate_mod_wheel"]:
            self._instrument.send_mod_wheel(modifier_inputs["mod_wheel"])

        for event in pygame.event.get():

            try:
                joy_index = getattr(event, "joy")
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

            joystick = self._joysticks[self._joystick_index]

            if event.type == JOYHATMOTION and event.hat == HAT_DPAD:
                vector = Vector(*event.value)
                method, kwargs = self.handle_hat_motion(vector, modifier_inputs)
                if method:
                    method(**kwargs)
                self._most_recent_hat_vector = vector

            elif event.type == JOYAXISMOTION:

                if event.axis in self._uncalibrated_axes:
                    self._uncalibrated_axes.discard(event.axis)

            elif event.type == JOYBUTTONDOWN:
                if event.button == mappings["toggle"]["do_increase_octave"]:
                    self._instrument.octave += 1
                elif event.button == mappings["toggle"]["do_decrease_octave"]:
                    self._instrument.octave -= 1
                elif event.button == mappings["toggle"]["do_change_bass"]:
                    self._instrument.bass += 1

            # tonic change isn't committed until the change tonic button is released
            elif event.type == JOYBUTTONUP and event.button == mappings["momentary"]["do_change_tonic"]:
                self._instrument.commit_tonic()

def main():
    app = App()
    app.setup_pygame()
    print(app.startup_message())

    try:
        is_controller_selected = False
        clock = pygame.time.Clock()
        while True:
            app.update()

            joystick_index = app.joystick_index
            if joystick_index >= 0 and not is_controller_selected:
                print ("Using controller {}".format(joystick_index))
                is_controller_selected = True

            # delay for 1/60 second
            clock.tick(60)

    except KeyboardInterrupt:
        print("\nQuitting...")
    finally:
        pygame.quit()

if __name__ == "__main__":
    main()
