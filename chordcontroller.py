import os
import pygame, rtmidi, rtmidi.midiutil
from collections import namedtuple
from pygame.locals import *

A = 0
B = 1
X = 2
Y = 3
LB = 4
RB = 5
BACK = 6
START = 7
XBOX = 8
LEFTTHUMB = 9
RIGHTTHUMB = 10

MAJOR = 0
MINOR = 1
DIMINISHED = 2

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

def Chord(root, quality=MAJOR):
    if quality == MINOR:
        return (root, root+3, root+7)
    elif quality == DIMINISHED:
        return (root, root+3, root+6)
    else:
        return (root, root+4, root+7)

Vector = namedtuple("Vector", ("x", "y"))

class Instrument(object):

    def __init__(self):
        self._midi_device = rtmidi.MidiOut(
            name="Chord Controller",
            rtapi=rtmidi.midiutil.get_api_from_environment())
        self._midi_device.open_virtual_port()
        self._most_recent_chord = tuple()

    def play_chord(self, scale_position):
        self.release_chord()
        spd = scale_position_data[scale_position]
        chord = Chord(60 + spd.root_pitch, spd.quality)
        for voice in chord:
            self._midi_device.send_message(NoteOn(voice))
        self._most_recent_chord = chord

    def release_chord(self):
        for voice in self._most_recent_chord:
            self._midi_device.send_message(NoteOn(voice, velocity=0))

    # def __del__(self):
    #     print("Closing MIDI port...")
    #     self._midi_device.close_port()

class App(object):

    def __init__(self):
        self._joysticks = []
        self._joystick_index = -1
        self._instrument = Instrument()
        self._most_recent_hat_vector = Vector(0,0)

    def setup_pygame(self):
        # set SDL to use the dummy NULL video driver, so it doesn't need a
        # windowing system.
        os.environ["SDL_VIDEODRIVER"] = "dummy"

        pygame.display.init()
        screen = pygame.display.set_mode((1, 1))

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

    def handle_hat_motion(self, vector):
        if vector != (0,0):
            if not (self.is_cardinal(vector) and self.are_adjacent(vector, self._most_recent_hat_vector)):
                self._instrument.play_chord(scale_positions[vector])
        else:
            self._instrument.release_chord()
            # print(scale_position_names[scale_positions[vector]])
        self._most_recent_hat_vector = vector

    def update(self):
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

            if event.type == JOYHATMOTION and event.hat == 0:
                self.handle_hat_motion(Vector(*event.value))

app = App()
app.setup_pygame()
print(app.startup_message())

try:

    is_controller_selected = False

    while True:
        app.update()

        joystick_index = app.joystick_index
        if joystick_index >= 0 and not is_controller_selected:
            print ("Using controller {}".format(joystick_index))
            is_controller_selected = True

except KeyboardInterrupt:
    print("\nQuitting...")
finally:
    pygame.quit()
