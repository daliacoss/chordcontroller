import pygame, yaml, appdirs
import os, sys, argparse, pkg_resources

from chordcontroller import InputHandler, Instrument

def startup_message(joysticks):
    s = "Available controllers:\n"
    for i, joystick in enumerate(joysticks):
        s += "{0}\t{1}\n".format(i, joystick.get_name())
    return s + "To continue, press any button on the controller you want to use."


def initialize():

    # set SDL to use the dummy NULL video driver, so it doesn't need a
    # windowing system.
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.display.init()
    pygame.display.set_mode((1, 1))

    # init the joystick control
    pygame.joystick.init()
    joysticks = []
    for i in range(pygame.joystick.get_count()):
        joy = pygame.joystick.Joystick(i)
        joy.init()
        joysticks.append(joy)

    if not joysticks:
        print("No controllers found. Please connect a game controller before starting.\nAborting...")
        sys.exit(1)

    print(startup_message(joysticks))

def main(argv=None):
    """
    main([argv]) -> None. Run the chordcontroller application.

    If using sys.argv, do not include the first element.
    """

    default_user_config = os.path.join(appdirs.user_config_dir("chordcontroller"), "ChordController.yaml")

    parser = argparse.ArgumentParser(description="Turn your Xbox controller into a MIDI keyboard.")
    parser.add_argument(
        "--config",
        default=os.path.join(appdirs.user_config_dir("chordcontroller"), "ChordController.yaml"),
        type=str,
        help="specify a config file in YAML format (default is {})".format(default_user_config)
    )
    parser.add_argument(
        "-q", "--quit-on-parse-failure",
        action="store_true",
        help="abort the program if the config file exists but is improperly formatted"
    )
    args = parser.parse_args(argv)

    with pkg_resources.resource_stream("chordcontroller", "data/defaults.yaml") as defaults:
        config = yaml.full_load(defaults)

    try:
        with open(args.config) as stream:
            config = yaml.full_load(stream)

    except yaml.YAMLError as e:
        print("Error parsing {0}: {1}".format(os.path.abspath(args.config), e))
        if args.quit_on_parse_failure:
            print("Aborting...")
            sys.exit(1)
        else:
            print("Using default settings...")

    except IOError:
        print("{} not found. Using default settings...".format(os.path.abspath(args.config)))

    finally:
        input_handler = InputHandler(config["mappings"], config["axis_calibration"])
        instrument = Instrument()

    initialize()

    try:
        is_controller_selected = False
        clock = pygame.time.Clock()
        while True:
            response = input_handler.update(pygame.event.get())
            for td in response["to_do"]:
                getattr(instrument, td[0])(*td[1:])
            for tu in response["to_undo"]:
                instrument.undo(*td)

            joystick_index = input_handler.joystick_index
            if joystick_index >= 0 and not is_controller_selected:
                print ("Using controller {}".format(joystick_index))
                is_controller_selected = True

            # delay for 1/60 second
            clock.tick(60)

    except KeyboardInterrupt:
        print("\nQuitting...")

    finally:
        pygame.quit()

main()
