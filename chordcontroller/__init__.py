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

import logging
import pygame, rtmidi, rtmidi.midiutil, yaml
from collections import namedtuple, deque, OrderedDict
from pygame.locals import *
from immutables import Map

MAJOR = 0
MINOR = 1
DIMINISHED = 2

DIMINISHED_SEVENTH = 9
MINOR_SEVENTH = 10
MAJOR_NINTH = 14

BASS_NONE = 0
BASS_ROOT = 1       # add an extra voice an octave below the root
BASS_INVERSION = 2  # add an extra voice an octave below the lowest note

yaml.add_constructor(
    "!immutable",
    lambda l, n: Map(l.construct_mapping(n)),
    yaml.FullLoader
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
ControlChange = lambda cn, cv, channel=0: (176 + channel, cn, cv)

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
        k = i + int(voicing)
        octave = k // len(chord)
        inversion += (chord[k % len(chord)] + octave * 12,)

    return inversion

class Vector(namedtuple("Vector", ("x", "y"))):
    def is_adjacent_to(self, other):
        """
        return True if vector directions are diagonally 'adjacent' to each other
        (e.g., (0,1) and (1,1))
        if vectors are equal, return False.
        if either vector is (0,0), return False.
        """

        if (0,0) in (self, other):
            return False

        diff = sorted((abs(self.x-other.x), abs(self.y-other.y)))
        return diff[0] == 0 and diff[1] == 1

    def is_cardinal(self):
        return bool(self[0]) ^ bool(self[1])

    def is_diagonal(self):
        return self[0] and self[1]

Vector.DOWN = Vector(0,-1)
Vector.UP = Vector(0,1)
Vector.RIGHT = Vector(1,0)
Vector.LEFT = Vector(-1,0)
Vector.DOWNRIGHT = Vector(1,-1)
Vector.DOWNLEFT = Vector(-1,-1)
Vector.UPRIGHT = Vector(1,1)
Vector.UPLEFT = Vector(-1,1)
Vector.NEUTRAL = Vector(0,0)

class Event(object):
    def __init__(self, _type, **params):
        self.__dict__ = params
        self.type = _type

class ButtonEvent(Event):
    def __init__(self, button, is_down=True, joy=0):
        super().__init__(_type = (JOYBUTTONDOWN if is_down else JOYBUTTONUP), joy = joy, button = button)

class HatEvent(Event):
    def __init__(self, value, hat=0, joy=0):
        super().__init__(value=value, _type=JOYHATMOTION, hat=hat, joy=joy)

class AxisEvent(Event):
    def __init__(self, value, axis, joy=0):
        super().__init__(value=value, _type=JOYAXISMOTION, axis=axis, joy=joy)


class UndoError(Exception):
    pass

class Command(object):

    def __init__(self, obj):
        self._obj = obj

    def execute(self):
        """
        Execute the command.
        """
        raise NotImplementedError

    def group_by(self, include_obj=True):
        """
        Return this command object's group_by attribute. This can be used by
        an invoker to determine which undo stack to place the object in.
        """

        raise NotImplementedError

    name = "command"
    revert = False

def def_command(name, obj_method_name, obj_method_params, param_group_range=None):
    class _Command(Command):

        def __init__(self, obj, *arg):
            super().__init__(obj)

            self._obj_method_name = obj_method_name
            self._obj_method_arg = OrderedDict()
            num_params = len(obj_method_params)
            self._param_group_range = param_group_range or range(num_params)
            for i, k in enumerate(obj_method_params):
                self._obj_method_arg[k] = arg[i]

        def execute(self):
            getattr(self._obj, self._obj_method_name)(**self._obj_method_arg)

        def __getattr__(self, key):
            return self._obj_method_arg[key]

        def __repr__(self):
            return (self._obj_method_arg.values())

        def group_by(self, include_obj=True):

            all_values = tuple(self._obj_method_arg.values())
            rest = []
            for i in self._param_group_range:
                rest.append(all_values[i])

            if include_obj:
                rest = (self._obj, *rest)

            return (self.name, *rest)

    _Command.name = name

    return _Command

class SetAttribute(Command):

    name = "set"

    def __init__(self, obj, key, value):
        super().__init__(obj)
        self._key = key
        self._value = value

    def group_by(self, include_obj=True):
        if include_obj:
            rest = (self._obj, self._key)
        else:
            rest = (self._key,)
        return (self.name, *rest)

    def __repr__(self):
        return str((self.name, self._obj, self.key, self.value))

    @property
    def key(self):
        return self._key

    @property
    def value(self):
        return self._value

    def execute(self):
        setattr(self._obj, self._key, self._value)

class SetNextAttribute(SetAttribute):

    name = "set_next"

    def execute(self):
        self._obj.set_next(self._key, self._value)

class IncrementAttribute(SetAttribute):

    name = "inc"

    def execute(self):
        setattr(self._obj, self._key, getattr(self._obj, self._key) + self._value)

    def revert(self):
        setattr(self._obj, self._key, getattr(self._obj, self._key) - self._value)

    def group_by(self, include_obj=True):

        rest = (self._key, self._value)
        if include_obj:
            rest = (self._obj, *rest)
        return (self.name, *rest)

class DecrementAttribute(IncrementAttribute):

    name = "dec"

    def __init__(self, obj, key, value):
        super().__init__(obj, key, -value)

class PlayScalePosition(Command):

    name = "play_scale_position"

    def __init__(self, obj, position):
        super().__init__(obj)
        self._position = position

    def execute(self):
        self._obj.play_scale_position(self._position)

    def group_by(self, include_obj=True):
        if include_obj:
            return (self.name, self._obj)
        else:
            return (self.name,)

    def revert(self):
        self._obj.release()

class SetMode(SetAttribute):

    name = "mode"

    def __init__(self, obj, mode_name):
        super().__init__(obj, "mode", mode_name)

SendCC = def_command("send_cc", "send_cc", ["cn", "cv"])
CommitAttribute = def_command("commit", "commit", ["key"])
def _revert(self):
    pass
CommitAttribute.revert = _revert
del _revert

class Invoker(object):

    def __init__(self, obj, command_classes=None):
        self._obj = obj
        self._commands = {}
        self._command_stacks = {}
        self._command_classes = {}
        self._command_stack_limits = {}
        for cmd_class in command_classes or []:
            self.add_command_class(cmd_class)

    def add_command_class(self, cmd_class):
        self._command_classes[cmd_class.name] = cmd_class

    def get_command_class(self, cmd_name):

        cmd_class = self._command_classes.get(cmd_name)
        if not cmd_class:
            raise KeyError(
                "{} is not a registered command. Did you remember to call {}.add_command_class?".format(
                    cmd_name, self.__class__.__name__))

        return cmd_class

    @property
    def commands(self):
        return self._commands.items()

    @property
    def command_stacks(self):
        return self._command_stacks.items()

    def add_command(self, cmd, stack_limit=0):

        cmd = tuple(cmd)
        command = self._commands.get(cmd)
        if command:
            return command

        cmd_name = cmd[0]
        cmd_arg = cmd[1:]
        cmd_class = self.get_command_class(cmd_name)
        command = cmd_class(*cmd_arg)

        self._commands[cmd] = command
        self._command_stacks.setdefault(command.group_by(), tuple())
        self._command_stack_limits[command.group_by()] = stack_limit

        return command

    def remove_command(self, cmd):
        self._commands.pop(cmd)
        # TODO: remove from stack

    def get_command_stack(self, stack_id):
        return self._command_stacks[stack_id]

    def get_command_stack_limit(self, stack_id):
        return self._command_stack_limits[stack_id]

    def do(self, cmd, autoregister_if_unknown=False, stack_limit_if_unknown=0):

        cmd = tuple(cmd)
        command = self._commands.get(cmd)
        if not command:
            if autoregister_if_unknown:
                command = self.add_command(cmd, stack_limit_if_unknown)
            else:
                raise KeyError("{} is not a registered command".format(cmd))

        stack_id = command.group_by()
        stack_limit = self._command_stack_limits.get(stack_id, 0)
        stack = self._command_stacks[stack_id]

        if stack_limit > 0:
            while len(stack) >= stack_limit:
                stack = self._undo(None, stack, 0)

        command.execute()

        self._command_stacks[stack_id] = (command, *stack)

    def undo(self, cmd):

        cmd = tuple(cmd)
        command = self._commands[cmd]
        stack_id = command.group_by()
        new_stack = self._undo(command, self._command_stacks.get(stack_id))
        self._command_stacks[stack_id] = new_stack

        return command

    def _undo(self, command, stack, i_cmd=-1):
        """command default is stack[i_cmd]"""

        #stack either doesn't exist or is empty
        if not stack:
            raise UndoError("No non-empty undo stack for {}".format(command))

        if i_cmd < 0 and command:
            for i_cmd, to_undo in enumerate(stack):
                if command is to_undo:
                    break
            else:
                # nothing to undo
                raise UndoError("{} not in undo stack".format(command))
        elif not command:
            command = stack[i_cmd]

        # run the revert method if it exists. otherwise, if the command to undo
        # is at the top of the stack, run the previous command to restore the
        # previous state
        if command.revert:
            command.revert()
        elif not i_cmd:
            if len(stack) == 1:
                # raise exception if there is no "previous" state to restore
                raise UndoError("{} has no revert method and is the only command in its undo stack".format(command))
            stack[1].execute()

        return stack[:i_cmd] + stack[i_cmd+1:]

class Instrument(object):

    def __init__(self, octave=5):

        self._midi_device = rtmidi.MidiOut(
            name="Chord Controller",
            rtapi=rtmidi.midiutil.get_api_from_environment())
        self._midi_device.open_virtual_port()

        self._most_recent_chord = tuple()
        self._playing_notes = set()
        # self._prev = {}
        # _prev = []
        self._next = {}

        self.octave = octave
        self.tonic = 0
        self.tonic_offset = 0
        self.bass = 0
        self.harmony = 0
        self.voicing = 0
        self.quality_modifier = 0
        self.extension_modifier = 0
        self.velocity = 127

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
        try:
            t = int(t)
        except TypeError:
            t = self._tonic_from_sd_and_offset(t["scale_degree"])
        self._tonic = t % 12
 
    @property
    def playing_notes(self):
        return frozenset(self._playing_note)

    def _tonic_from_sd_and_offset(self, value):

        if value == None:
            return
        return scale_position_data[value].root_pitch + self.tonic + self.tonic_offset

    def get_next(self, key):
        return self._next[key]

    def set_next(self, key, value):
 
        # TODO: allow None as a value
        if not value:
            self.unset_next(value)
            return
        if key == "tonic":
            try:
                value = int(value)
            except TypeError:
                if value.get("calculate_immediately"):
                    value = self._tonic_from_sd_and_offset(value["scale_degree"])
        self._next[key] = value

    def unset_next(self, key):
        if key in self._next:
            self._next.pop(key)

    def commit(self, key):

        try:
            next_value = self._next[key]
            self._next.pop(key)
        except KeyError:
            return

        setattr(self, key, next_value)

    def construct_chord(self, scale_position, **modifiers):
        spd = scale_position_data[scale_position]
        tonic_offset = self.tonic_offset
        quality_modifier = self.quality_modifier
        extension_modifier = self.extension_modifier

        root = self.tonic + (self.octave * 12) + spd.root_pitch + tonic_offset

        if self.quality_modifier == 1:
            quality = not spd.quality
        elif self.quality_modifier == 2:
            quality = DIMINISHED if spd.quality != DIMINISHED else MINOR
        else:
            quality = spd.quality

        if extension_modifier == 1:
            extensions = (MINOR_SEVENTH,)
        elif extension_modifier == 2:
            if quality == DIMINISHED:
                extensions = (DIMINISHED_SEVENTH,)
            else:
                extensions = (MINOR_SEVENTH, MAJOR_NINTH)
        else:
            extensions = tuple()

        chord = Chord(root, quality, extensions=extensions, voicing=self.voicing)
        if self.bass == BASS_ROOT:
            chord += (root - 12,)
        elif self.bass == BASS_INVERSION:
            chord += (chord[0] - 12,)

        return chord

    def play(self, do_release=True):
        """
        Play the current note cluster/chord.
        
        Keyword arguments:
        do_release -- release (silence) any currently playing notes first.
        """

        if do_release:
            self.release()
        self.send_note_on(self._chord)

    def release(self):
        """Release (silence) any currently playing notes."""

        self.send_note_on(self._playing_notes, velocity=0)

    def play_scale_position(self, scale_position):

        self.set_chord_from_scale_position(scale_position)
        self.play()

    def set_chord_from_scale_position(self, scale_position):
        """Set current note cluster/chord to result of construct_chord."""

        self._chord = self.construct_chord(scale_position)

    @property
    def playing_notes(self):
        return frozenset(self._playing_notes)

    def send_note_on(self, note_values, velocity=None):
        """
        Send a MIDI note-on message for each specified note.
        
        Keyword arguments:
        note_values -- iterable of note (pitch) values.
        velocity -- if None, will default to self.velocity.
        """
        if not note_values:
            return

        if velocity is None:
            velocity = self.velocity

        for voice in note_values:
            # velocity = 0x70 - round(modifiers.get("velocity", 0)**1.7 * 0x70)
            self._midi_device.send_message(NoteOn(voice, velocity=velocity))
        if velocity:
            self._playing_notes.update(note_values)
        else:
            self._playing_notes.difference_update(note_values)

    def send_cc(self, cn, cv):
        self._midi_device.send_message(ControlChange(cn,cv))

    def send_mod_wheel(self, mod_wheel):
        self._midi_device.send_message(ModWheel(int(mod_wheel * 127)))

def commands_from_input_mapping(mapping):

    commands = []

    def to_extend(action, t):
        do = action["do"]
        if t == "axes":
            return [*do, action["value_at_min"]], [*do, action["value_at_max"]]
        else:
            return [do]

    for x in ["hats", "buttons", "axes"]:
        for switch_name, switch_actions in mapping.get(x, {}).items():
            for action in switch_actions:
                commands.extend(to_extend(action, x))

    return commands

class ChordController(object):

    _default_cmd_classes = (
        SetAttribute,
        SetNextAttribute,
        CommitAttribute,
        IncrementAttribute,
        DecrementAttribute,
        SendCC,
        PlayScalePosition,
        SetMode,
    )

    def __init__(self, input_handler, instrument=None, **params):
        """
        input_handler can be either instance of InputHandler, or a map of config
        settings to pass to a new InputHandler instance
        """

        if issubclass(type(input_handler), InputHandler):
            self.input_handler = input_handler
        else:
            self.input_handler = InputHandler(input_handler)

        self.allow_unknown_commands = params.get("allow_unknown_commands", True)
        self.instrument = instrument or Instrument()
        self.invoker = Invoker(
            self.instrument,
            (*self._default_cmd_classes, *params.get("extra_cmd_classes", []))
        )

        # add commands to invoker
        is_fallback_needed = set()
        for k_mode, mode in input_handler.mappings.items():
            for do in commands_from_input_mapping(mode):
                obj = self.input_handler if do[0] == "mode" else self.instrument
                do = [do[0], obj, *do[1:]]
                cmd = self.invoker.add_command(do, stack_limit=20)

                if (
                    type(cmd) in [SetAttribute, SetNextAttribute] and
                    #issubclass(cmd.__class__, SetAttribute) and
                    not cmd.revert and
                    (cmd.group_by(), tuple()) in self.invoker.command_stacks
                ):
                    is_fallback_needed.add(cmd.group_by())

        # for "set" commands, we need a default value at the bottom of the undo
        # stack. we will create a command based on the initial value of the
        # attribute to set, then run that command immediately
        for x in is_fallback_needed:
            # using None as fallback for getattr allows SetNextAttribute to work
            fallback_arg = (*x, getattr(self.instrument, x[2], None))
            self.invoker.add_command(fallback_arg, stack_limit=20)
            self.invoker.do(fallback_arg)

        self.execute_actions({"to_do": self.input_handler.startup_commands})

    def update(self, events):

        response = self.input_handler.update(events)
        self.execute_actions(response)
        return response

    def execute_actions(self, response):
        insert = lambda l, index, value: (*l[:index], value, *l[index:])
        for action in response.get("to_undo", []):
            obj = self.input_handler if action[0] == "mode" else self.instrument
            action = insert(action, 1, obj)
            try:
                self.invoker.undo(action)
            except UndoError:
                pass
        for action in response.get("to_do", []):
            obj = self.input_handler if action[0] == "mode" else self.instrument
            action = insert(action, 1, obj)
            self.invoker.do(action, self.allow_unknown_commands, 20)

def value_in_range(percent, value_at_min, value_at_max, curve=1.0, inclusive=True, steps=[]):
    """
    Multiply a percentage by an arbitrary range.

    Optional arguments:
        curve: exponent to apply to percent. Ignored if `steps` is non-empty.
        inclusive: if False, and if `steps` is non-empty, result will always be
        less than `value_at_max`.
        steps: iterable of discrete percentage steps in the range.
        
    If `steps` is specified, the following procedure is used to calculate the
    result:
        1. Sort `steps` if not already sorted.
        3. Let X be `(value_at_max - value_at_min) / len(steps)`.
        4. Let K be the index of the lowest step that is greater than `percent`.
        5. If K is defined or `inclusive` is True, let result be
        `(X * K) + value_at_min`.
        5. Else, let result be `value_at_max`. 
    """

    if percent < 0 or percent > 1:
        raise ValueError("percent must be between 0 and 1 inclusive (got {} instead)".format(percent))
    if curve < 0:
        raise ValueError("curve must be greater than 0")

    if not steps:
        return (value_at_max - value_at_min) * (percent**curve) + value_at_min

    steps = sorted(steps)
    x = (value_at_max - value_at_min) / (len(steps) )
    for i, step in enumerate(steps):
        if percent < step:
            return i * x + value_at_min
    else:
        if inclusive:
            return value_at_max
        else:
            return i * x + value_at_min

class InputHandler(object):

    def __init__(self, config, joystick_index=-1):

        if not hasattr(config, "get"):
            config = yaml.full_load(config)

        self._joystick_index = joystick_index
        self._most_recent_hat_vector = {0: Vector(0,0)}

        self.axis_calibration = config["axis_calibration"]
        self.mappings = config["mappings"]
        self.hat_calibration = config["hat_calibration"]
        self.mode = "default"
        self.scheduled_events = []
        self.startup_commands = config.get("startup", [])

        self._uncalibrated_axes = set()
        self._toggle_states = {}

    @property
    def joystick_index(self):
        return self._joystick_index

    @joystick_index.setter
    def joystick_index(self, v):
        self._joystick_index = v

        #axis_events = []
        #for k, settings in self.axis_calibration.items():
            #value_at_start = settings.get("value_at_start")
            #if value_at_start != None:
                #axis_events.append(AxisEvent(value=value_at_start, axis=k))
        #self.scheduled_events += (axis_events)

    def clamp_axis_value(self, axis_id, raw_axis_value):
        calibration = self.axis_calibration[axis_id]
        rounded_axis_value = round(raw_axis_value, 3)
        return (rounded_axis_value - calibration["min"]) / (calibration["max"] - calibration["min"])

    def _hat_key(self, hat, value):
        return "{0}:{1}:{2}".format(hat, value.x, value.y)

    def _get_hat_actions(self, keymap, hat_key):
        return keymap.get("hats", {}).get(hat_key, [])

    def _get_toggle_state(self, mode, input_type, input_key, action_index):
        return self._toggle_states.get(
            "{}.{}.{}.{}".format(mode, input_type, input_key, action_index), False
        )

    def _set_toggle_state(self, mode, input_type, input_key, action_index, value):
        self._toggle_states[
            "{}.{}.{}.{}".format(mode, input_type, input_key, action_index)
        ] = value

    def _handle_toggle(self, t_args, to_do, to_undo):
        t_args = (self.mode, *t_args)
        t_state = self._get_toggle_state(*t_args)
        self._set_toggle_state(*t_args, not t_state)
        return (to_do if not t_state else to_undo)

    def update(self, events):

        to_do = []
        to_undo = []

        events += self.scheduled_events
        self.scheduled_events.clear()

        for event in events:
            logging.info(event)
            try:
                joy_index = getattr(event, "joy")
            # this event does not spark joy
            except AttributeError:
                continue

            # if we're not tracking any joystick, and this is a button press,
            # start tracking the joystick the button was pressed on.
            # else if we're already tracking a joystick other than this one,
            # do nothing and go to next event
            if joy_index != self._joystick_index:
                if self._joystick_index < 0 and event.type == JOYBUTTONDOWN:
                    self.joystick_index = joy_index
                else:
                    continue

            keymap = self.mappings[self.mode]
 
            if event.type in [JOYBUTTONDOWN, JOYBUTTONUP]:

                actions = keymap.get("buttons", {}).get(event.button, [])

                for i, data in enumerate(actions):
                    behavior = data.get("behavior", "momentary")
                    if behavior == "momentary":
                        if event.type == JOYBUTTONDOWN:
                            to_do.append(data["do"])
                        else:
                            to_undo.append(data["do"])
                        continue
                    
                    action_dir = JOYBUTTONUP if data.get("on_release") else JOYBUTTONDOWN
                    if action_dir != event.type:
                        continue
                    elif behavior == "latch":
                        to_do.append(data["do"])
                    elif behavior == "toggle":
                        self._handle_toggle(("buttons", event.button, i), to_do, to_undo).append(data["do"])

            elif event.type == JOYHATMOTION:

                prev_value = self._most_recent_hat_vector.get(event.hat)
                value = Vector(*event.value)
                is_neutral = (value == Vector.NEUTRAL)

                # easy diagonals: if the most recent dpad event was a diagonal
                # press, ignore presses in any of the adjacent cardinal directions
                # (prevents accidentally playing the wrong chord)
                if (
                    self.hat_calibration.get(event.hat, {}).get("easy_diagonals")
                    and prev_value.is_diagonal()
                    and prev_value.is_adjacent_to(value) 
                ):
                    continue

                # respond to direction we just moved from

                if prev_value:
                    hat_key = self._hat_key(event.hat, prev_value)
                    actions = self._get_hat_actions(keymap, hat_key)
                    for i, data in enumerate(actions):
                        behavior = data.get("behavior", "momentary")
                        on_release = data.get("on_release")
                        if behavior == "momentary":
                            to_undo.append(data["do"])
                        elif on_release and (behavior == "latch"):
                            to_do.append(data["do"])
                        elif on_release and (behavior == "toggle"):
                            self._handle_toggle(("hats", hat_key, i), to_do, to_undo).append(data["do"])

                self._most_recent_hat_vector[event.hat] = value

                if is_neutral:
                    continue

                # respond to direction we just moved to

                hat_key = self._hat_key(event.hat, value)
                actions = self._get_hat_actions(keymap, hat_key)
                for i, data in enumerate(actions):
                    behavior = data.get("behavior", "momentary")
                    on_release = data.get("on_release")
                    if behavior == "momentary":
                        to_do.append(data["do"])
                    elif behavior == "latch" and not on_release:
                        to_do.append(data["do"])
                    elif behavior == "toggle" and not on_release:
                        self._handle_toggle(
                            ("hats", hat_key, i), to_do, to_undo
                        ).append(data["do"])

            elif event.type == JOYAXISMOTION:
                if event.axis in self._uncalibrated_axes:
                    self._uncalibrated_axes.discard(event.axis)

                for data in keymap.get("axes", {}).get(event.axis, []):
                    data = dict(data)
                    do = data.pop("do")
                    processed_value = value_in_range(self.clamp_axis_value(event.axis, event.value), **data)
                    if processed_value != None:
                        to_do.append([*do, processed_value])

        r = {"to_do": to_do, "to_undo": to_undo}
        #logging.info(r)
        return r

