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
BUTTON_LEFTTHUMB = 9
BUTTON_RIGHTTHUMB = 10
AXIS_RTRIGGER = 4
AXIS_LTRIGGER = 5

MIN_TRIGGER = -1.0
MAX_TRIGGER = 1.0

MAJOR = 0
MINOR = 1
DIMINISHED = 2

DIMINISHED_SEVENTH = 9
MINOR_SEVENTH = 10
MAJOR_NINTH = 14

mappings = dict(
    modifiers = dict(
        do_flatten = BUTTON_RB,
        do_add_voices_1 = BUTTON_X,
        do_add_voices_2 = BUTTON_Y,
        do_change_quality_1 = BUTTON_A,
        do_change_quality_2 = BUTTON_B,
        do_set_octave = BUTTON_START,
    ),
    axes = dict(
        velocity = AXIS_RTRIGGER,
    ),

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

def Chord(root, quality=MAJOR, extensions=tuple()):

    if quality == MINOR:
        triad = (root, root+3, root+7)
    elif quality == DIMINISHED:
        triad = (root, root+3, root+6)
    else:
        triad = (root, root+4, root+7)

    return triad + tuple(root + x for x in extensions)

Vector = namedtuple("Vector", ("x", "y"))

class Instrument(object):

    def __init__(self, octave=6):
        self.octave = octave

        self._midi_device = rtmidi.MidiOut(
            name="Chord Controller",
            rtapi=rtmidi.midiutil.get_api_from_environment())
        self._midi_device.open_virtual_port()
        self._most_recent_chord = tuple()

    @property
    def octave(self):
        return self._octave
    
    @octave.setter
    def octave(self, o):
        self._octave = int(o) % 9

    def play_chord(self, scale_position, **modifiers):

        self.release_chord()
        
        spd = scale_position_data[scale_position]
        root = (self.octave * 12) + spd.root_pitch - modifiers.get("do_flatten", 0)

        if modifiers.get("do_change_quality_1"):
            quality = not spd.quality
        elif modifiers.get("do_change_quality_2"):
            quality = DIMINISHED if spd.quality != DIMINISHED else MINOR
        else:
            quality = spd.quality
            
        velocity = 0x70 - round(modifiers["velocity"]**1.7 * 0x70)
        # print(velocity)
        # velocity = hex(127 - round(vel_slider**2 * 127))
            
        e = modifiers.get("do_add_voices_1", 0) + modifiers.get("do_add_voices_2", 0)
        if e == 1:
            extensions = (MINOR_SEVENTH,)
        elif e == 2:
            if quality == DIMINISHED:
                extensions = (DIMINISHED_SEVENTH,)
            else:
                extensions = (MINOR_SEVENTH, MAJOR_NINTH)
        else:
            extensions = tuple()
        
        chord = Chord(root, quality, extensions=extensions)

        for voice in chord:
            self._midi_device.send_message(NoteOn(voice, velocity=velocity))

        self._most_recent_chord = chord

    def release_chord(self):
        for voice in self._most_recent_chord:
            self._midi_device.send_message(NoteOn(voice, velocity=0))

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
        for input_type, m in [("axes", joystick.get_axis), ("modifiers", joystick.get_button)]:
            items += tuple((k, m(v)) for k, v in mappings[input_type].items())
        # dict( ((k, joystick.get_axis(v)) for k, v in mappings["axes"].items()) )
        # return dict(((k, joystick.get_button(v)) for k, v in mappings["modifiers"].items()))
        return dict(items)

    def handle_hat_motion(self, vector):
        """
        maps d-pad vector to the correct Instrument method and returns that
        method, along with appropriate args and kwargs, without calling it.

        if no Instrument method should be called for this vector, returns None
        and empty arg collections.
        """
        
        method = None
        kwargs = {}
        
        modifier_inputs = self.read_modifier_inputs()

        if AXIS_RTRIGGER in self._uncalibrated_axes:
            modifier_inputs["velocity"] = 0
        else:
            modifier_inputs["velocity"] = (modifier_inputs["velocity"] - MIN_TRIGGER) / (MAX_TRIGGER - MIN_TRIGGER)

        if vector != (0,0):
            # don't register a d-pad press in any of the cardinal directions
            # if the most recent d-pad event was a diagonal press
            # (prevent accidentally playing the wrong chord)
            if not (self.is_cardinal(vector) and self.are_adjacent(vector, self._most_recent_hat_vector)):
                method = self._instrument.play_chord
                kwargs = dict(scale_position=mappings["scale_positions"][vector], **modifier_inputs)
        else:
            method = self._instrument.release_chord
        
        return method, kwargs

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
                vector = Vector(*event.value)
                method, kwargs = self.handle_hat_motion(vector)
                if method:
                    method(**kwargs)
                self._most_recent_hat_vector = vector
            
            elif event.type == JOYAXISMOTION and event.axis in self._uncalibrated_axes:
                self._uncalibrated_axes.discard(event.axis)

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
