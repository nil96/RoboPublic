
from __future__ import (
    unicode_literals,
    print_function,
    division,
    absolute_import,
    )

# Make Py2's str and range equivalent to Py3's
str = type('')

import warnings
from collections import namedtuple

from picamera.exc import (
    mmal_check,
    PiCameraError,
    PiCameraMMALError,
    PiCameraValueError,
    PiCameraRuntimeError,
    PiCameraDeprecated,
    )


class PiVideoFrameType(object):

    frame = 0
    key_frame = 1
    sps_header = 2
    motion_data = 3


class PiVideoFrame(namedtuple('PiVideoFrame', (
    'index',
    'frame_type',
    'frame_size',
    'video_size',
    'split_size',
    'timestamp',
    'complete',
    ))):


    __slots__ = () # workaround python issue #24931

    @property
    def position(self):
        """

        """
        return self.split_size - self.frame_size

    @property
    def keyframe(self):
        """

        """
        warnings.warn(
            PiCameraDeprecated(
                ''))
        return self.frame_type == PiVideoFrameType.key_frame

    @property
    def header(self):
        """

        """
        warnings.warn(
            PiCameraDeprecated(
                ''))
        return self.frame_type == PiVideoFrameType.sps_header
