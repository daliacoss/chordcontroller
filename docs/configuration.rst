Configuration reference
=======================

.. toctree::
   :maxdepth: 2

Defining constants
------------------

The **constants** section of your config file is where you define aliases for buttons, axes, and POV hats on your controller.

You can reference these aliases in later sections of the config file, instead of using raw integer values. This is useful for working not only with different controller models, but also different software drivers.

Here are the default values:

.. code-block:: yaml

    constants:
        BUTTON_A: 0
        BUTTON_B: 1
        BUTTON_X: 2
        BUTTON_Y: 3
        BUTTON_LB: 4
        BUTTON_RB: 5
        BUTTON_BACK: 6
        BUTTON_START: 7
        BUTTON_XBOX: 8
        BUTTON_LTHUMB: 9
        BUTTON_RTHUMB: 10
        HAT_DPAD: 0
        AXIS_LTHUMBX: 0
        AXIS_LTHUMBY: 1
        AXIS_RTHUMBX: 2
        AXIS_RTHUMBY: 3
        AXIS_RTRIGGER: 4
        AXIS_LTRIGGER: 5


Note that the names themselves are arbitrary. What matters is being consistent throughout the config file.

Calibrating analog inputs
-------------------------

The **axis_calibration** section of the config file allows you to calibrate the analog inputs on your controller. It should be defined as a dictionary where each key is either:
    * "default",
    * a `string alias <#defining-constants>`_ corresponding to an axis, or
    * the index of an axis as an integer.

Settings for each axis:

**min** 
  The value of the axis at its lowest point.

**max**
  The value of the axis at its highest point.

Here is the default configuration:

.. code-block:: yaml

  axis_calibration:
      default:
          min: -1.0
          max: 1.0


Calibrating POV hats (d-pad)
----------------------------

The **hat_calibration** section of the config file allows you to calibrate the point-of-view (POV) hats on your controller. Generally, a pad-type controller such as the standard Xbox 360 controller will have one hat, the d-pad.

The section should be defined as a dictionary where each key is either:
    * "default",
    * a `string alias <#defining-constants>`_ corresponding to a POV hat, or
    * the index of a POV hat as an integer.

Settings for each hat:

**easy_diagonals**
  Can be either "true" or "false". If true, a d-pad press in a cardinal direction will be unacknowledged (ignored) if the previously acknowledged d-pad event was a press in an adjacent diagonal direction.

  For example, if you press up-right on the d-pad, then press right without allowing the d-pad to go neutral, the second press will be ignored. In order for pressing right to have any effect, you will first need to either press a different direction or let go of the d-pad.

  This setting is useful if your controller's d-pad or hat switch is not optimized for making precision diagonal movements.

Here is the default configuration:

.. code-block:: yaml

    hat_calibration:
        default:
            easy_diagonals: true

Commands
--------

TODO

Executing commands at startup
-----------------------------

TODO

Mappings
--------

The good stuff! This is where you tell chordcontroller what each button, trigger, stick, etc. should do when pressed or moved.
