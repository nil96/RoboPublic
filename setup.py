#!/usr/bin/env python3


"""A pure Python interface for the Raspberry Pi camera module."""

import os
import sys
from setuptools import setup, find_packages

if sys.version_info[0] == 2:
    if not sys.version_info >= (2, 7):
        raise ValueError('This package requires Python 2.7 or above')
elif sys.version_info[0] == 3:
    if not sys.version_info >= (3, 2):
        raise ValueError('This package requires Python 3.2 or above')
else:
    raise ValueError('Unrecognized major version of Python')

HERE = os.path.abspath(os.path.dirname(__file__))


try:
    import multiprocessing
except ImportError:
    pass

__project__      = 'picamera'
__version__      = '1.13'
__author__       = 'Dave Jones'
__author_email__ = 'dave@waveform.org.uk'
__url__          = 'http://picamera.readthedocs.io/'
__platforms__    = 'ALL'

__classifiers__ = [
    "',
]

__keywords__ = [
    'raspberrypi',
    'camera',
]

__requires__ = [
]

__extra_requires__ = {
    'doc':   ['sphinx'],
    'test':  ['coverage', 'pytest', 'mock', 'Pillow', 'numpy'],
    'array': ['numpy'],
}

__entry_points__ = {
}


def main():
    import io
    with io.open(os.path.join(HERE, 'README.rst'), 'r') as readme:
        setup(
            name                 = __project__,
            version              = __version__,
            description          = __doc__,
            long_description     = readme.read(),
            classifiers          = __classifiers__,
            author               = __author__,
            author_email         = __author_email__,
            url                  = __url__,
            license              = [
                c.rsplit('::', 1)[1].strip()
                for c in __classifiers__
                if c.startswith('License ::')
            ][0],
            keywords             = __keywords__,
            packages             = find_packages(),
            include_package_data = True,
            platforms            = __platforms__,
            install_requires     = __requires__,
            extras_require       = __extra_requires__,
            entry_points         = __entry_points__,
        )


if __name__ == '__main__':
    main()
