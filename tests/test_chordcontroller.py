import pytest, os, pkg_resources, yaml
from collections import namedtuple
from pygame.locals import *
from chordcontroller import UndoError

os.environ["RTMIDI_API"] = "RTMIDI_DUMMY"

############
# FIXTURES #
############

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

B = ButtonEvent
H = HatEvent
A = AxisEvent

@pytest.fixture
def mapping():
    return {
        "hats": {
            "0:0:1": [{"do": ["set", "octave", 4]}],
            "0:0:-1": [{"do": ["set", "octave", 5]}],
        },
        "buttons": {
            "0": [{"do": ["play_scale_position", 0]}],
            "1": [{"do": ["play_scale_position", 1]}],
        }
    }

@pytest.fixture
def instrument():
    import chordcontroller
    return chordcontroller.Instrument(octave=5)

@pytest.fixture
def input_handler():
    from chordcontroller import InputHandler
    with pkg_resources.resource_stream("chordcontroller", "data/defaults.yaml") as defaults:
        config = yaml.full_load(defaults)
    return InputHandler(config)

@pytest.fixture(params=[
    (60, 0, tuple(), 0),
    (60, 0, (10,), 0),
])
def chord_root_position(request):
    import chordcontroller
    return chordcontroller.Chord(*request.param)

@pytest.fixture(params=[
    # press A, then release A, then release A
    ("quality_modifier", (B(0, True), 1), (B(0, False), 0)),
    # press A, then press B, then release B, then release A
    ("quality_modifier", (B(0, True), 1), (B(1, True), 2), (B(1, False), 1), (B(0, False), 0)),
    # press A, then press B, then release A then release B
    ("quality_modifier", (B(0, True), 1), (B(1, True), 2), (B(0, False), 2), (B(1, False), 0)),
    
    # press X, then release X
    (("extension_modifier"), (B(2, True), 1), (B(2, False), 0)),
    # press Y, then release Y
    (("extension_modifier"), (B(3, True), 1), (B(3, False), 0)),
    # press X, then press Y, then release Y, then release X
    (("extension_modifier"), (B(2, True), 1), (B(3, True), 2), (B(3, False), 1), (B(2, False), 0)),

    # press A, then release A, then release A (testing UndoError)
    ("quality_modifier", (B(0, True), 1), (B(0, False), 0), (B(0, False), UndoError)),

    # dpad up, then dpad down, then dpad neutral
    ("playing_notes",
        (H((0,1)), {60, 64, 67}),
        (H((0,-1)), {60, 64, 67}),
        (H((0,0)), set())
    ),

    ("velocity", (A(1.0, 4), 0x0), (A(-1.0, 4), 0x70))
])
def input_sequence(request):
    expected_attr = request.param[0]
    return [{
        "input_event": p[0],
        "expected_value": p[1],
        "expected_attr": expected_attr,
    } for p in request.param[1:]]

#########
# TESTS #
#########

def test_chord_inversions(chord_root_position):
    from chordcontroller import Chord

    root = chord_root_position[0]
    triad = chord_root_position[:3]
    extensions = tuple(x - root for x in chord_root_position[3:])

    for i in range(1, len(chord_root_position)):
        inversion = Chord(root, voicing=i, extensions=extensions)
        assert inversion == chord_root_position[i:] + tuple(x+12 for x in chord_root_position[:i])

        # e.g., for a triad, -1 should be the second inversion minus an octave,
        # -2 the first inversion minus an octave, etc
        negative_inversion = Chord(root, voicing = i - len(chord_root_position), extensions=extensions)
        assert inversion == tuple(x + 12 for x in negative_inversion)

def test_value_in_range():
    from chordcontroller import value_in_range

    assert value_in_range(0, 0, 127) == 0
    assert value_in_range(1, 0, 127) == 127
    assert value_in_range(.4, 0, 127) == 127 * .4
    assert value_in_range(0, 127, 0) == 127
    assert value_in_range(.5, -1, 1) == 0
    assert round(value_in_range(.4, 127, 0), 3) == 76.2 
    with pytest.raises(ValueError):
        value_in_range(-0.00001, 0, 127)
    with pytest.raises(ValueError):
        value_in_range(1.00001, 0, 127)
    
    # test with curve
    assert round(value_in_range(.5, 127, 0, curve=1.7), 3) == 87.911
    with pytest.raises(ValueError):
        value_in_range(.5, 127, 0, curve=-0.00001)

    # test with steps
    assert value_in_range(.3, 0, 10, steps=[.2, .4, .6, .8, 1]) == 2 
    assert value_in_range(1, 0, 10, steps=[.2, .4, .6, .8, 1]) == 10 
    assert value_in_range(.3, 0, 10, steps=[.2, .4, .6, .8, 1], inclusive=False) == 2
    assert value_in_range(1, 0, 10, steps=[.2, .4, .6, .8, 1], inclusive=False) == 8
    assert value_in_range(1, 0, 10, steps=[.25, .5, .75, 1], inclusive=False) == 7.5
    assert value_in_range(.3, 0, 10, steps=[.2, .4, .6, .8]) == 2.5
    assert value_in_range(.800001, 0, 10, steps=[.2, .4, .6, .8]) == 10
    assert value_in_range(.800001, 0, 10, steps=[.2, .4, .6, .8], inclusive=False) == 7.5

    assert value_in_range(.000001, 0, 8, steps=[0,.2,.4,.6,.8]) == (8/5)

class TestVector(object):
    
    def test_equality(self):
        from chordcontroller import Vector

        assert Vector(0,0) == (0,0)
        assert Vector(0,1) == (0,1)
        assert Vector(0,1) == Vector(0,1)
        assert Vector(1,0) != (0,1)
        assert Vector(1,0) != Vector(0,1)

    def test_adjacent(self):
        from chordcontroller import Vector

        assert not Vector(0,0).is_adjacent_to(Vector(0,1))
        assert not Vector(0,0).is_adjacent_to(Vector(0,0))
        assert not Vector(1,0).is_adjacent_to(Vector(1,0))
        assert Vector(1,1).is_adjacent_to(Vector(1,0))
        assert Vector(1,0).is_adjacent_to(Vector(1,1))

    def test_diagonal_and_cardinal(self):
        from chordcontroller import Vector
 
        for v in [(1,1),(-1,-1),(1,-1),(-1,1)]:
            v = Vector(*v)
            assert v.is_diagonal()
            assert not v.is_cardinal()
        for v in [(0,1),(1,0),(0,-1),(-1,0)]:
            v = Vector(*v)
            assert v.is_cardinal()
            assert not v.is_diagonal()

        v = Vector(0,0)
        assert not v.is_cardinal()
        assert not v.is_diagonal()

class TestCommandsAndInvoker(object):

    def test_set_attribute(self):
        from chordcontroller import SetAttribute

        obj = ButtonEvent(0)
        cmd = SetAttribute(obj, "button", 3)
        assert obj.button == 0

        cmd.execute()
        assert obj.button == 3

        assert cmd.group_by(True) == ("set", obj, "button")

        assert not cmd.revert

    def test_inc_attribute(self):
        from chordcontroller import IncrementAttribute

        obj = ButtonEvent(1)
        cmd = IncrementAttribute(obj, "button", 2)
        assert obj.button == 1

        cmd.execute()
        assert obj.button == 3

        assert cmd.group_by(True) == ("inc", obj, "button", 2)

    def test_def_command(self):
        from chordcontroller import def_command

        class MyClass(object):
            def __init__(self, x, y):
                self.x = x
                self.y = y
            def myfoo(self, x, y):
                self.x += x
                self.y += y

        Foo = def_command("foo", "myfoo", ["x", "y"], range(1))
        o = MyClass(3, 4)
        cmd = Foo(o, 1, 2)
        assert cmd.name == "foo"
        assert cmd.x == 1
        assert cmd.y == 2
        assert cmd.group_by(False) == ("foo", 1)
        assert cmd.group_by(True) == ("foo", o, 1)
        assert cmd.group_by() == ("foo", o, 1)

        assert o.x == 3
        assert o.y == 4
        cmd.execute()
        assert o.x == 4
        assert o.y == 6

        FooBar = def_command("foo_bar", "myfoo", ["x", "y"])
        o = MyClass(3, 4)
        cmd = FooBar(o, 1, 2)
        assert cmd.group_by(False) == ("foo_bar", 1, 2)
        assert cmd.group_by(True) == ("foo_bar", o, 1, 2)
        assert cmd.group_by() == ("foo_bar", o, 1, 2)

    def test_invoker(self):
        from chordcontroller import SetAttribute, IncrementAttribute, Invoker

        obj = ButtonEvent(-1)
        invoker = Invoker(obj, [SetAttribute, IncrementAttribute])

        cmd_set_button_0 = invoker.add_command(("set", obj, "button", 0))
        cmd_set_button_1 = invoker.add_command(("set", obj, "button", 1))
        cmd_set_button_2 = invoker.add_command(("set", obj, "button", 2))
        cmd_set_button_1000 = invoker.add_command(("set", obj, "button", 1000))
        assert obj.button == -1

        invoker.do(("set", obj, "button", 0))
        assert obj.button == 0

        invoker.do(("set", obj, "button", 1))
        assert obj.button == 1

        invoker.do(("set", obj, "button", 2))
        assert obj.button == 2
        assert invoker.get_command_stack(("set", obj, "button")) == (
            cmd_set_button_2, cmd_set_button_1, cmd_set_button_0)

        # undoing a command below the top of the undo stack should remove
        # it from the stack, but should have no effect on the button value
        # if there is no revert method
        assert invoker.undo(("set", obj, "button", 1)) is cmd_set_button_1
        assert obj.button == 2
        assert invoker.get_command_stack(("set", obj, "button")) == (
            cmd_set_button_2, cmd_set_button_0)

        # undoing a command that was never executed should raise exception
        with pytest.raises(Exception):
            invoker.undo(("set", obj, "button", 1000))
        assert obj.button == 2
        assert invoker.get_command_stack(("set", obj, "button")) == (
            cmd_set_button_2, cmd_set_button_0)

        # undoing the most recent command should change the button value
        assert invoker.undo(("set", obj, "button", 2)) is cmd_set_button_2
        assert obj.button == 0
        assert invoker.get_command_stack(("set", obj, "button")) == (cmd_set_button_0,)
#
        # undoing the only command in the stack should raise exception if
        # the command has no revert method
        with pytest.raises(Exception):
            invoker.undo(("set", obj,  obj, "button", 0))
        assert obj.button == 0
        assert invoker.get_command_stack(("set", obj, "button")) == (cmd_set_button_0,)

    def test_invoker_stack_limit(self):

        from chordcontroller import SetAttribute, IncrementAttribute, Invoker

        obj = ButtonEvent(-1)
        invoker = Invoker(obj, [SetAttribute, IncrementAttribute])

        cmd_set_button_0 = invoker.add_command(("set", obj, "button", 0), stack_limit=2)
        cmd_set_button_1 = invoker.add_command(("set", obj, "button", 1), stack_limit=0)
        assert invoker.get_command_stack_limit(("set", obj, "button")) == 0
        cmd_set_button_2 = invoker.add_command(("set", obj, "button", 2), stack_limit=2)
        assert invoker.get_command_stack_limit(("set", obj, "button")) == 2

        invoker.do(("set", obj, "button", 0))
        invoker.do(("set", obj, "button", 1))
        invoker.do(("set", obj, "button", 2))
        assert obj.button == 2
        assert len(invoker.get_command_stack(("set", obj, "button"))) == 2
        invoker.undo(("set", obj, "button", 2))
        assert obj.button == 0

def test_commands_from_input_mapping(mapping):
    from chordcontroller import commands_from_input_mapping

    cmds = set((tuple(c) for c in commands_from_input_mapping(mapping)))
    expected = set((("set", "octave", 4), ("set", "octave", 5), ("play_scale_position", 1), ("play_scale_position", 0)))
    assert cmds == expected

class TestInstrument(object):

    @pytest.mark.parametrize("input_value,expected_value", [
        (-1, 8),
        (9, 0),
        (10, 1),
        (8.8, 8),
        ("3", 3),
    ])
    def test_set_octave(self, instrument, input_value, expected_value):
        instrument.octave = input_value
        assert instrument.octave == expected_value

    @pytest.mark.parametrize("input_value", ["1.7","jeff"])
    def test_set_octave_from_bad_string(self, instrument, input_value):
        with pytest.raises(ValueError):
            instrument.octave = input_value

    @pytest.mark.parametrize("input_value,expected_value", [
        (-1, 2),
        (10, 1),
        (2.8, 2),
        ("2", 2),
    ])
    def test_set_bass(self, instrument, input_value, expected_value):
        instrument.bass = input_value
        assert instrument.bass == expected_value

    @pytest.mark.parametrize("input_value", ["1.7","jeff"])
    def test_set_bass_from_bad_string(self, instrument, input_value):
        with pytest.raises(ValueError):
            instrument.bass = input_value

    @pytest.mark.parametrize("scale_position,quality_modifier,expected_value", [
        (0, 0, (60, 64, 67)),
        (0, 1, (60, 63, 67)),
        (0, 2, (60, 63, 66)),
        (1, 0, (62, 65, 69)),
        (1, 1, (62, 66, 69)),
        (1, 2, (62, 65, 68)),
    ])
    def test_construct_chord(self, instrument, scale_position, quality_modifier, expected_value):
        instrument.quality_modifier = quality_modifier
        chord = instrument.construct_chord(scale_position)
        assert chord == expected_value

class TestInputHandler(object):

    def test_button_press(self, input_handler):

        # test momentary behavior

        mb0 = input_handler.mappings[input_handler.mode]["buttons"][0]
        assert len(mb0) == 1
        assert mb0[0].get("behavior", "momentary") == "momentary"

        response = input_handler.update([ButtonEvent(0)])
        assert not response["to_undo"]
        assert response["to_do"] == [["set", "quality_modifier", 1]]

        response = input_handler.update([ButtonEvent(0, is_down=False)])
        assert not response["to_do"]
        assert response["to_undo"] == [["set", "quality_modifier", 1]]

        # test latch behavior

        mb0[0]["behavior"] = "latch"
        response = input_handler.update([ButtonEvent(0)])
        assert not response["to_undo"]
        assert response["to_do"] == [["set", "quality_modifier", 1]]

        response = input_handler.update([ButtonEvent(0, is_down=False)])
        assert not response["to_do"]
        assert not response["to_undo"]
        
        response = input_handler.update([ButtonEvent(0, is_down=True)])
        assert response["to_do"] == [["set", "quality_modifier", 1]]
        assert not response["to_undo"]

        response = input_handler.update([ButtonEvent(0, is_down=False)])
        assert not response["to_do"]
        assert not response["to_undo"]

        # test latch with on_release (only trigger when button is released)

        mb0[0]["on_release"] = True
        response = input_handler.update([ButtonEvent(0)])
        assert not (response["to_do"] or response["to_undo"])

        response = input_handler.update([ButtonEvent(0, is_down=False)])
        assert response["to_do"] == [["set", "quality_modifier", 1]]
        assert not response["to_undo"]

        # test toggle behavior

        mb0[0]["behavior"] = "toggle"
        mb0[0]["on_release"] = False 
        response = input_handler.update([ButtonEvent(0)])
        assert response["to_do"] == [["set", "quality_modifier", 1]]
        assert not response["to_undo"]

        response = input_handler.update([ButtonEvent(0, is_down=False)])
        assert not response["to_do"]
        assert not response["to_undo"]

        response = input_handler.update([ButtonEvent(0)])
        assert response["to_undo"] == [["set", "quality_modifier", 1]]
        assert not response["to_do"]

    def test_clamp_axis_value(self, input_handler):

        a = 4
        assert input_handler.clamp_axis_value(a, -1) == 0
        assert input_handler.clamp_axis_value(a, 1) == 1
        assert input_handler.clamp_axis_value(a, .4) == .7

    def test_axis_motion(self, input_handler):

        from chordcontroller import value_in_range
        input_handler.joystick_index = 0

        response = input_handler.update([AxisEvent(axis=4, value=-1.0)])
        assert response["to_do"] == [["set", "velocity", 112]]

        response = input_handler.update([AxisEvent(axis=4, value=1.0)])
        assert not response["to_undo"]
        assert response["to_do"] == [["set", "velocity", 0]]

        response = input_handler.update([AxisEvent(axis=4, value=0)])
        assert not response["to_undo"]
        assert response["to_do"] == [["set", "velocity", value_in_range(.5, 112, 0, 1.7)]]

        response = input_handler.update([AxisEvent(axis=5, value=-1.0)])
        assert response["to_do"] == [["set", "voicing", 0]]

        response = input_handler.update([AxisEvent(axis=5, value=-.1)])
        assert response["to_do"] == [["set", "voicing", 2]]

    def test_hat_motion(self, input_handler):
        from chordcontroller import Vector
        input_handler.joystick_index = 0

        # dpad up
        mhu = input_handler.mappings[input_handler.mode]["hats"]["0:0:1"]

        response = input_handler.update([HatEvent(Vector.UP)])
        assert response["to_do"] == [["play_scale_position", 0]]
        assert not response["to_undo"]
        
        response = input_handler.update([HatEvent(Vector.LEFT)])
        assert response["to_do"] == [["play_scale_position", 4]]
        assert response["to_undo"] == [["play_scale_position", 0]]
        
        response = input_handler.update([HatEvent(Vector.NEUTRAL)])
        assert not response["to_do"]
        assert response["to_undo"] == [["play_scale_position", 4]]

        # test easy diagonals
        assert input_handler.hat_calibration[0]["easy_diagonals"]
        input_handler.update([HatEvent(Vector.UP)])
        response = input_handler.update([HatEvent(Vector.UPLEFT)])
        assert response["to_do"] == [["play_scale_position", 6]]
        assert response["to_undo"] == [["play_scale_position", 0]]
        response = input_handler.update([HatEvent(Vector.LEFT)])
        assert not response["to_do"]
        assert not response["to_undo"]
        response = input_handler.update([HatEvent(Vector.UP)])
        assert not response["to_do"]
        assert not response["to_undo"]
        response = input_handler.update([HatEvent(Vector.NEUTRAL)])
        assert not response["to_do"]
        assert response["to_undo"] == [["play_scale_position", 6]]

        input_handler.update([HatEvent(Vector.UPLEFT)])
        input_handler.update([HatEvent(Vector.LEFT)])
        response = input_handler.update([HatEvent(Vector.DOWNLEFT)])
        assert response["to_do"] == [["play_scale_position", 5]] 
        assert response["to_undo"] == [["play_scale_position", 6]]

        # test toggle
        input_handler.update([HatEvent(Vector.NEUTRAL)])
        mhu[0]["behavior"] = "toggle"

        response = input_handler.update([HatEvent(Vector.UP)])
        assert response["to_do"] == [["play_scale_position", 0]] 
        assert not response["to_undo"]

        response = input_handler.update([HatEvent(Vector.NEUTRAL)])
        assert not response["to_do"]
        assert not response["to_undo"]

        response = input_handler.update([HatEvent(Vector.UP)])
        assert response["to_undo"] == [["play_scale_position", 0]] 
        assert not response["to_do"]

        response = input_handler.update([HatEvent(Vector.NEUTRAL)])
        assert not response["to_do"]
        assert not response["to_undo"]

        # test on_release
        mhu[0]["on_release"] = True
        response = input_handler.update([HatEvent(Vector.UP)])
        assert not response["to_undo"]
        assert not response["to_do"]

        response = input_handler.update([HatEvent(Vector.NEUTRAL)])
        assert response["to_do"] == [["play_scale_position", 0]] 
        assert not response["to_undo"]

class TestChordController(object):

    def test_init(self, input_handler, instrument):
        from chordcontroller import ChordController

        j = input_handler.joystick_index
        chord_controller = ChordController(input_handler, instrument)
        assert chord_controller.input_handler.joystick_index == j

    def test_default_mode_update(self, input_handler, instrument, input_sequence):
        from chordcontroller import ChordController

        chord_controller = ChordController(input_handler, instrument)
        chord_controller.input_handler.joystick_index = 0

        for d in input_sequence:
            ev = d["expected_value"]
            if type(ev) is type and issubclass(ev, Exception):
                with pytest.raises(ev):
                    chord_controller.update([d["input_event"]])
            else:
                chord_controller.update([d["input_event"]])
                assert getattr(chord_controller.instrument, d["expected_attr"]) == d["expected_value"]

    def test_other_modes(self, input_handler, instrument):
        from chordcontroller import ChordController

        chord_controller = ChordController(input_handler, instrument)
        chord_controller.input_handler.joystick_index = 0

        # start button
        assert instrument.octave == 5
        response = chord_controller.update([ButtonEvent(7)])
        assert input_handler.mode == "change_octave"
        assert instrument.octave == 5

        response = chord_controller.update([HatEvent((1,0))])
        assert instrument.octave == 6

        response = chord_controller.update([HatEvent((0,0))])
        assert instrument.octave == 6

        response = chord_controller.update([HatEvent((-1,0))])
        assert instrument.octave == 5

        response = chord_controller.update([HatEvent((0,0))])
        assert instrument.octave == 5

        response = chord_controller.update([ButtonEvent(7, False)])
        assert input_handler.mode == "default"

