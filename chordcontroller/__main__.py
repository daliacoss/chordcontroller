import pygame, appdirs
import os, sys, argparse, pkg_resources, logging

from chordcontroller import InputHandler, ChordController, Instrument
from yaml import YAMLError
from rtmidi import midiutil

def startup_message(joysticks):
    s = "Available controllers:\n"
    for i, joystick in enumerate(joysticks):
        s += "{0}\t{1}\n".format(i, joystick.get_name())
    return s + "To continue, press any button on the controller you want to use."


def initialize_pygame():

    # set SDL to use the dummy NULL video driver, so it doesn't need a
    # windowing system.
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.display.init()
    pygame.display.set_mode((1, 1))

def list_joysticks():

    # init the joystick control
    pygame.joystick.quit()
    pygame.joystick.init()

    joysticks = []
    for i in range(pygame.joystick.get_count()):
        joy = pygame.joystick.Joystick(i)
        joy.init()
        joysticks.append(joy)

    if not joysticks:
        print("No controllers found.")
    else:
        s = "Available controllers:\n" + "\n".join(
            "{0}\t{1}".format(i, j.get_name()) for i, j in enumerate(joysticks)
        )
        #for i, joystick in enumerate(joysticks):
            #s += "{0}\t{1}\n".format(i, joystick.get_name())
        print(s)

    return joysticks

def main(argv=None):
    """
    main([argv]) -> None. Run the chordcontroller application.

    If using sys.argv, do not include the first element.
    """

    default_user_config = os.path.join(appdirs.user_config_dir("chordcontroller"), "ChordController.yaml")

    parser = argparse.ArgumentParser(prog="chordcontroller", description="Turn your Xbox controller into a MIDI keyboard.")
    parser.add_argument(
        "--config",
        default=os.path.join(appdirs.user_config_dir("chordcontroller"), "ChordController.yaml"),
        type=str,
        help="config file in YAML format (default is {})".format(default_user_config)
    )
    parser.add_argument(
        "-q", "--quit-on-parse-failure",
        action="store_true",
        help="abort the program if the config file exists but is improperly formatted"
    )
    parser.add_argument(
        "-c", "--controller",
        type=int,
        help="index of controller to use (overrides -a)"
    )
    parser.add_argument(
        "-a", "--controller-autoset",
        action="store_true",
        help="select whichever controller is first to register a button press"
    )
    parser.add_argument(
        "-p", "--port",
        default=-1,
        type=int,
        help="index of MIDI out port to use",
    )
    parser.add_argument(
        "-l", "--list-ports",
        action="store_true",
        help="list all available MIDI ports and exit"
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        type=(lambda x: str(x).upper()),
        help="minimum severity of logs to record (case-insensitive, default is WARNING)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level))

    # list ports if asked

    if args.list_ports:
        midiutil.list_output_ports()
        sys.exit()

    # load config

    abort = False
    input_handler = None

    #with pkg_resources.resource_stream("chordcontroller", "data/defaults.yaml") as f:
        #defaults = f.read()

    try:
        with open(args.config) as stream:
            input_handler = InputHandler(stream)
    except YAMLError as e:
        print("Error parsing {0}: {1}".format(os.path.abspath(args.config), e))
        if args.quit_on_parse_failure:
            print("Aborting...")
            abort = True
        else:
            print("Using default settings...")
    except IOError:
        print("{} not found. Using default settings...".format(os.path.abspath(args.config)))
    finally:
        if abort:
            sys.exit(1)

    if not input_handler:
        input_handler = InputHandler()
    chord_controller = ChordController(input_handler, Instrument(port=args.port))

    input_handler.joystick_autoset = args.controller_autoset
    if args.controller != None:
        input_handler.joystick_index = args.controller

    # game loop
    try:

        # initialize
        initialize_pygame()
        clock = pygame.time.Clock()

        while not list_joysticks():
            input("Please connect a game controller, then press Enter.")

        is_controller_selected = False
        while True:
            #TODO: replace clock with Event.wait and threading
            clock.tick(60)

            joystick_index = input_handler.joystick_index
            if joystick_index >= 0:
                if not is_controller_selected:
                    print ("Using controller {}".format(joystick_index))
                    is_controller_selected = True
            elif not args.controller_autoset:
                try:
                    input_handler.joystick_index = int(input("Type the number of the controller you want to use, and press Enter: "))
                except ValueError:
                    print("Unable to parse input.")

            #ev = pygame.event.wait()
            ev = pygame.event.get()
            if not ev:
                continue
            #response = chord_controller.update([ev])
            response = chord_controller.update(ev)

    except KeyboardInterrupt:
        print("\nQuitting...")

    finally:
        pygame.quit()

main()
