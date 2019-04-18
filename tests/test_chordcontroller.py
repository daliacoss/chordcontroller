import pytest, os, pkg_resources, yaml
from collections import namedtuple
from pygame.locals import *

os.environ["RTMIDI_API"] = "RTMIDI_DUMMY"

############
# FIXTURES #
############

class Event(object):
    def __init__(self, type, **params):
        self.__dict__ = params
        self.type = type

class ButtonEvent(Event):
    def __init__(self, button, is_down=True, joy=0):
        super().__init__(type = (JOYBUTTONDOWN if is_down else JOYBUTTONUP), joy = joy, button = button)

@pytest.fixture
def mapping():
    return {
        "hats": {
            "0_0_1": [{"do": ["set", "octave", 4]}],
            "0_0_-1": [{"do": ["set", "octave", 5]}],
        },
        "buttons": {
            "0": [{"do": ["play_scale_position", 1]}]
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
        assert cmd.group_by() == ("foo", 1)
        assert cmd.group_by(True) == ("foo", o, 1)

        assert o.x == 3
        assert o.y == 4                
        cmd.execute()
        assert o.x == 4
        assert o.y == 6
        
        FooBar = def_command("foo_bar", "myfoo", ["x", "y"])
        o = MyClass(3, 4)
        cmd = FooBar(o, 1, 2)
        assert cmd.group_by() == ("foo_bar", 1, 2)
        assert cmd.group_by(True) == ("foo_bar", o, 1, 2)
    
    def test_invoker(self):
        from chordcontroller import SetAttribute, IncrementAttribute, Invoker
        
        obj = ButtonEvent(-1)
        invoker = Invoker(obj, [SetAttribute, IncrementAttribute])
        
        cmd_set_button_0 = invoker.add_command("set", "button", 0)
        cmd_set_button_1 = invoker.add_command("set", "button", 1)
        cmd_set_button_2 = invoker.add_command("set", "button", 2)
        cmd_set_button_1000 = invoker.add_command("set", "button", 1000)
        assert obj.button == -1

        invoker.do("set", "button", 0)
        assert obj.button == 0

        invoker.do("set", "button", 1)
        assert obj.button == 1

        invoker.do("set", "button", 2)
        assert obj.button == 2
        assert invoker.get_command_stack(("set", "button")) == (
            cmd_set_button_2, cmd_set_button_1, cmd_set_button_0)
        
        # undoing a command below the top of the undo stack should remove
        # it from the stack, but should have no effect on the button value
        # if there is no revert method
        assert invoker.undo("set", "button", 1) is cmd_set_button_1
        assert obj.button == 2
        assert invoker.get_command_stack(("set", "button")) == (
            cmd_set_button_2, cmd_set_button_0)

        # undoing a command that was never executed should have no effect
        assert not invoker.undo("set", "button", 1000)
        assert obj.button == 2
        assert invoker.get_command_stack(("set", "button")) == (
            cmd_set_button_2, cmd_set_button_0)
        
        # undoing the most recent command should change the button value
        assert invoker.undo("set", "button", 2) is cmd_set_button_2
        assert obj.button == 0
        assert invoker.get_command_stack(("set","button")) == (cmd_set_button_0,)

        # undoing the only command in the stack should have no effect if
        # the command has no revert method
        assert not invoker.undo("set", "button", 0)
        assert obj.button == 0
        assert invoker.get_command_stack(("set","button")) == (cmd_set_button_0,)

def test_commands_from_input_mapping(mapping):
    from chordcontroller import commands_from_input_mapping
    
    cmds = commands_from_input_mapping(mapping)
    expected = (("set", "octave", 4), ("set", "octave", 5), ("play_scale_position", 1))
    for i, c in enumerate(cmds):
        print(c)
        assert tuple(c) in expected

class TestInstrument(object):

    @pytest.mark.parametrize("input_value,expected_value", [
        (-1, 8),
        (9, 0),
        (10, 1),
        (8.8, 8),
        ("3", 3),
    ])
    def test_octave(self, instrument, input_value, expected_value):
        instrument.octave = input_value
        assert instrument.octave == expected_value

    @pytest.mark.parametrize("input_value", ["1.7","jeff"])
    def test_octave_from_bad_string(self, instrument, input_value):
        with pytest.raises(ValueError):
            instrument.octave = input_value

    @pytest.mark.parametrize("input_value,expected_value", [
        (-1, 2),
        (10, 1),
        (2.8, 2),
        ("2", 2),
    ])
    def test_bass(self, instrument, input_value, expected_value):
        instrument.bass = input_value
        assert instrument.bass == expected_value

    @pytest.mark.parametrize("input_value", ["1.7","jeff"])
    def test_bass_from_bad_string(self, instrument, input_value):
        with pytest.raises(ValueError):
            instrument.bass = input_value

    @pytest.mark.parametrize("scale_position,modifiers,expected_value", [
        (0, {}, (60, 64, 67)),
        (0, {"do_flatten":1}, (60-1, 64-1, 67-1)),
    ])
    def test_construct_chord(self, instrument, scale_position, modifiers, expected_value):
        chord = instrument.construct_chord(scale_position, **modifiers)
        assert chord == expected_value

class TestInputHandler(object):

    def test_button_press(self, input_handler):

        response = input_handler.update([ButtonEvent(0)])
        assert not response["to_undo"]

        expected_to_do = ["set", "quality", 1]
        for i, x in enumerate(expected_to_do):
            assert response["to_do"][0][i] == x

        response = input_handler.update([ButtonEvent(0, is_down=False)])
        assert not response["to_do"]

        expected_to_do = ["set", "quality", 1]
        for i, x in enumerate(expected_to_do):
            assert response["to_undo"][0][i] == x

class TestChordController(object):
    
    def test_init(self, input_handler, instrument):
        from chordcontroller import ChordController
        
        ChordController(input_handler, instrument)
