
from __future__ import (
    unicode_literals,
    print_function,
    division,
    absolute_import,
    )

# Make Py2's str equivalent to Py3's
str = type('')


import picamera.mmal as mmal


class PiCameraWarning(Warning):
    """
    Base class for PiCamera warnings.
    """


class PiCameraDeprecated(PiCameraWarning, DeprecationWarning):
    """
    Raised when deprecated functionality in picamera is used.
    """


class PiCameraFallback(PiCameraWarning, RuntimeWarning):
    """
    Raised when picamera has to fallback on old functionality.
    """


class PiCameraResizerEncoding(PiCameraWarning, RuntimeWarning):
    """
    Raised when picamera uses a resizer purely for encoding purposes.
    """


class PiCameraAlphaStripping(PiCameraWarning, RuntimeWarning):
    """
    Raised when picamera does alpha-byte stripping.
    """


class PiCameraResolutionRounded(PiCameraWarning, RuntimeWarning):
    """
    Raised when picamera has to round a requested frame size upward.
    """


class PiCameraError(Exception):
    """
    Base class for PiCamera errors.
    """


class PiCameraRuntimeError(PiCameraError, RuntimeError):
    """
    Raised when an invalid sequence of operations is attempted with a
    :class:`PiCamera` object.
    """


class PiCameraClosed(PiCameraRuntimeError):
    """
    Raised when a method is called on a camera which has already been closed.
    """


class PiCameraNotRecording(PiCameraRuntimeError):
    """
    Raised when :meth:`~PiCamera.stop_recording` or
    :meth:`~PiCamera.split_recording` are called against a port which has no
    recording active.
    """


class PiCameraAlreadyRecording(PiCameraRuntimeError):
    """
    Raised when :meth:`~PiCamera.start_recording` or
    :meth:`~PiCamera.record_sequence` are called against a port which already
    has an active recording.
    """


class PiCameraValueError(PiCameraError, ValueError):
    """
    Raised when an invalid value is fed to a :class:`~PiCamera` object.
    """


class PiCameraIOError(PiCameraError, IOError):
    """
    Raised when a :class:`~PiCamera` object is unable to perform an IO
    operation.
    """


class PiCameraMMALError(PiCameraError):
    """
    Raised when an MMAL operation fails for whatever reason.
    """
    def __init__(self, status, prefix=""):
        self.status = status
        PiCameraError.__init__(self, "%s%s%s" % (prefix, ": " if prefix else "", {
            mmal.MMAL_ENOMEM:    "Out of memory",
            mmal.MMAL_ENOSPC:    "Out of resources",
            mmal.MMAL_EINVAL:
            mmal.MMAL_ENOSYS:    "Function not implemented",
            mmal.MMAL_ENOENT:    "No such file or directory",
            mmal.MMAL_ENXIO:     "No such device or address",
            mmal.MMAL_EIO:       "I/O error",
            mmal.MMAL_ESPIPE:    "Illegal seek",
            mmal.MMAL_ECORRUPT:  "Data is corrupt #FIXME not POSIX",
            mmal.MMAL_ENOTREADY: "Component is not ready #FIXME not POSIX",
            mmal.MMAL_ECONFIG:   ,
            mmal.MMAL_EISCONN:   "Port is already connected",
            mmal.MMAL_ENOTCONN:  "Port is disconnected",
            mmal.MMAL_EAGAIN:    ,
            mmal.MMAL_EFAULT:   ,
            }.get(status, "Unknown status error")))


class PiCameraPortDisabled(PiCameraMMALError):
    """

    """
    def __init__(self, msg):
        super(PiCameraPortDisabled, self).__init__(mmal.MMAL_EINVAL, msg)


def mmal_check(status, prefix=""):
    """
    """
    if status != mmal.MMAL_SUCCESS:
        raise PiCameraMMALError(status, prefix)

