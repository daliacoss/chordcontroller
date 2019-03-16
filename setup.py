from setuptools import setup
setup(
    name="chordcontroller",
    version="0.1",
    py_modules=["chordcontroller"],
    python_requires="~=3.3",
    install_requires=[
        "appdirs>=1.4.3",
        # until they get rid of the annoying startup message, don't use later
        # version of pygame than 1.9.3
        "pygame==1.9.3",
        "python-rtmidi>=1.2.1",
        "PyYAML>=5.1",
    ]
)
