import pytest, os

os.environ["RTMIDI_API"] = "RTMIDI_DUMMY"

@pytest.fixture
def instrument():
    import chordcontroller
    return chordcontroller.Instrument()

@pytest.fixture(params=[
    (60, 0, tuple(), 0),
    (60, 0, (10,), 0),
])
def chord_root_position(request):
    import chordcontroller
    return chordcontroller.Chord(*request.param)

def test_chord_inversions(chord_root_position):
    from chordcontroller import Chord
    
    root = chord_root_position[0]
    triad = chord_root_position[:3]
    extensions = tuple(x - root for x in chord_root_position[3:])
    
    for i in range(1, len(chord_root_position)):
        inversion = Chord(root, voicing=i, extensions=extensions)
        assert inversion == chord_root_position[i:] + tuple(x+12 for x in chord_root_position[:i])

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
