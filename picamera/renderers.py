
from __future__ import (
    unicode_literals,
    print_function,
    division,
    absolute_import,
    )

# Make Py2's str equivalent to Py3's
str = type('')

import ctypes as ct

from . import mmal, mmalobj as mo
from .exc import (
    PiCameraRuntimeError,
    PiCameraValueError,
    mmal_check,
    )


class PiRenderer(object):


    def __init__(
            self, parent, layer=0, alpha=255, fullscreen=True, window=None,
            crop=None, rotation=0, vflip=False, hflip=False, anamorphic=False):
        # Create and enable the renderer component
        self._rotation = 0
        self._vflip = False
        self._hflip = False
        self.renderer = mo.MMALRenderer()
        try:
            self.layer = layer
            self.alpha = alpha
            self.fullscreen = fullscreen
            self.anamorphic = anamorphic
            if window is not None:
                self.window = window
            if crop is not None:
                self.crop = crop
            self.rotation = rotation
            self.vflip = vflip
            self.hflip = hflip
            self.renderer.enable()
        except:
            self.renderer.close()
            raise

    def close(self):
        """
        Finalizes the renderer and deallocates all structures.

        This method is called by the camera prior to destroying the renderer
        (or more precisely, letting it go out of scope to permit the garbage
        collector to destroy it at some future time).
        """
        if self.renderer:
            self.renderer.close()
            self.renderer = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()

    def _get_alpha(self):
        return self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION].alpha
    def _set_alpha(self, value):
        try:
            if not (0 <= value <= 255):
                raise PiCameraValueError(
                    "Invalid alpha value: %d (valid range 0..255)" % value)
        except TypeError:
            raise PiCameraValueError("Invalid alpha value: %s" % value)
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        mp.set = mmal.MMAL_DISPLAY_SET_ALPHA
        mp.alpha = value
        self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION] = mp
    alpha = property(_get_alpha, _set_alpha, doc="""\

        """)

    def _get_layer(self):
        return self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION].layer
    def _set_layer(self, value):
        try:
            if not (0 <= value <= 255):
                raise PiCameraValueError(
                    "Invalid layer value: %d (valid range 0..255)" % value)
        except TypeError:
            raise PiCameraValueError("Invalid layer value: %s" % value)
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        mp.set = mmal.MMAL_DISPLAY_SET_LAYER
        mp.layer = value
        self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION] = mp
    layer = property(_get_layer, _set_layer, doc="""\

        """)

    def _get_fullscreen(self):
        return self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION].fullscreen.value != mmal.MMAL_FALSE
    def _set_fullscreen(self, value):
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        mp.set = mmal.MMAL_DISPLAY_SET_FULLSCREEN
        mp.fullscreen = bool(value)
        self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION] = mp
    fullscreen = property(_get_fullscreen, _set_fullscreen, doc="""\

        """)

    def _get_anamorphic(self):
        return self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION].noaspect.value != mmal.MMAL_FALSE
    def _set_anamorphic(self, value):
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        mp.set = mmal.MMAL_DISPLAY_SET_NOASPECT
        mp.noaspect = bool(value)
        self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION] = mp
    anamorphic = property(_get_anamorphic, _set_anamorphic, doc="""\

        """)

    def _get_window(self):
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        return (
            mp.dest_rect.x,
            mp.dest_rect.y,
            mp.dest_rect.width,
            mp.dest_rect.height,
            )
    def _set_window(self, value):
        try:
            x, y, w, h = value
        except (TypeError, ValueError) as e:
            raise PiCameraValueError(
                "Invalid window rectangle (x, y, w, h) tuple: %s" % value)
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        mp.set = mmal.MMAL_DISPLAY_SET_DEST_RECT
        mp.dest_rect = mmal.MMAL_RECT_T(x, y, w, h)
        self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION] = mp
    window = property(_get_window, _set_window, doc="""\

        active.
        """)

    def _get_crop(self):
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        return (
            mp.src_rect.x,
            mp.src_rect.y,
            mp.src_rect.width,
            mp.src_rect.height,
            )
    def _set_crop(self, value):
        try:
            x, y, w, h = value
        except (TypeError, ValueError) as e:
            raise PiCameraValueError(
                "Invalid crop rectangle (x, y, w, h) tuple: %s" % value)
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        mp.set = mmal.MMAL_DISPLAY_SET_SRC_RECT
        mp.src_rect = mmal.MMAL_RECT_T(x, y, w, h)
        self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION] = mp
    crop = property(_get_crop, _set_crop, doc="""\

        """)

    def _get_rotation(self):
        return self._rotation
    def _set_rotation(self, value):
        try:
            value = ((int(value) % 360) // 90) * 90
        except ValueError:
            raise PiCameraValueError("Invalid rotation angle: %s" % value)
        self._set_transform(
                self._get_transform(value, self._vflip, self._hflip))
        self._rotation = value
    rotation = property(_get_rotation, _set_rotation, doc="""\



        """)

    def _get_vflip(self):
        return self._vflip
    def _set_vflip(self, value):
        value = bool(value)
        self._set_transform(
                self._get_transform(self._rotation, value, self._hflip))
        self._vflip = value
    vflip = property(_get_vflip, _set_vflip, doc="""\

        """)

    def _get_hflip(self):
        return self._hflip
    def _set_hflip(self, value):
        value = bool(value)
        self._set_transform(
                self._get_transform(self._rotation, self._vflip, value))
        self._hflip = value
    hflip = property(_get_hflip, _set_hflip, doc="""\

        """)

    def _get_transform(self, rotate, vflip, hflip):
        # Use a (horizontally) mirrored transform if one of vflip or hflip is
        # set. If vflip is set, rotate by an extra 180 degrees to make up for
        # the lack of a "true" vertical flip
        mirror = vflip ^ hflip
        if vflip:
            rotate = (rotate + 180) % 360
        return {
            (0,   False): mmal.MMAL_DISPLAY_ROT0,
            (90,  False): mmal.MMAL_DISPLAY_ROT90,
            (180, False): mmal.MMAL_DISPLAY_ROT180,
            (270, False): mmal.MMAL_DISPLAY_ROT270,
            (0,   True):  mmal.MMAL_DISPLAY_MIRROR_ROT0,
            (90,  True):  mmal.MMAL_DISPLAY_MIRROR_ROT90,
            (180, True):  mmal.MMAL_DISPLAY_MIRROR_ROT180,
            (270, True):  mmal.MMAL_DISPLAY_MIRROR_ROT270,
            }[(rotate, mirror)]

    def _set_transform(self, value):
        mp = self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION]
        mp.set = mmal.MMAL_DISPLAY_SET_TRANSFORM
        mp.transform = value
        self.renderer.inputs[0].params[mmal.MMAL_PARAMETER_DISPLAYREGION] = mp


class PiOverlayRenderer(PiRenderer):
    """
    """

    SOURCE_BPP = {
        3: 'rgb',
        4: 'rgba',
        }

    SOURCE_ENCODINGS = {
        'yuv':  mmal.MMAL_ENCODING_I420,
        'rgb':  mmal.MMAL_ENCODING_RGB24,
        'rgba': mmal.MMAL_ENCODING_RGBA,
        'bgr':  mmal.MMAL_ENCODING_BGR24,
        'bgra': mmal.MMAL_ENCODING_BGRA,
        }

    def __init__(
            self, parent, source, resolution=None, format=None, layer=0,
            alpha=255, fullscreen=True, window=None, crop=None, rotation=0,
            vflip=False, hflip=False, anamorphic=False):
        super(PiOverlayRenderer, self).__init__(
            parent, layer, alpha, fullscreen, window, crop,
            rotation, vflip, hflip, anamorphic)

        # Copy format from camera's preview port, then adjust the encoding to
        # RGB888 or RGBA and optionally adjust the resolution and size
        if resolution is not None:
            self.renderer.inputs[0].framesize = resolution
        else:
            self.renderer.inputs[0].framesize = parent.resolution
        self.renderer.inputs[0].framerate = 0
        if format is None:
            source_len = mo.buffer_bytes(source)
            plane_size = self.renderer.inputs[0].framesize.pad()
            plane_len = plane_size.width * plane_size.height
            try:
                format = self.SOURCE_BPP[source_len // plane_len]
            except KeyError:
                raise PiCameraValueError(
                    'unable to determine format from source size')
        try:
            self.renderer.inputs[0].format = self.SOURCE_ENCODINGS[format]
        except KeyError:
            raise PiCameraValueError('unknown format %s' % format)
        self.renderer.inputs[0].commit()
        # The following callback is required to prevent the mmalobj layer
        # automatically passing buffers back to the port
        self.renderer.inputs[0].enable(callback=lambda port, buf: True)
        self.update(source)

    def update(self, source):
        """
        """
        buf = self.renderer.inputs[0].get_buffer()
        buf.data = source
        self.renderer.inputs[0].send_buffer(buf)


class PiPreviewRenderer(PiRenderer):
    """
    """

    def __init__(
            self, parent, source, resolution=None, layer=2, alpha=255,
            fullscreen=True, window=None, crop=None, rotation=0, vflip=False,
            hflip=False, anamorphic=False):
        super(PiPreviewRenderer, self).__init__(
            parent, layer, alpha, fullscreen, window, crop,
            rotation, vflip, hflip, anamorphic)
        self._parent = parent
        if resolution is not None:
            resolution = mo.to_resolution(resolution)
            source.framesize = resolution
        self.renderer.inputs[0].connect(source).enable()

    def _get_resolution(self):
        result = self._parent._camera.outputs[self._parent.CAMERA_PREVIEW_PORT].framesize
        if result != self._parent.resolution:
            return result
        else:
            return None
    def _set_resolution(self, value):
        if value is not None:
            value = mo.to_resolution(value)
        if (
                value.width > self._parent.resolution.width or
                value.height > self._parent.resolution.height
                ):
            raise PiCameraValueError(
                'preview resolution cannot exceed camera resolution')
        self.renderer.connection.disable()
        if value is None:
            value = self._parent.resolution
        self._parent._camera.outputs[self._parent.CAMERA_PREVIEW_PORT].framesize = value
        self._parent._camera.outputs[self._parent.CAMERA_PREVIEW_PORT].commit()
        self.renderer.connection.enable()
    resolution = property(_get_resolution, _set_resolution, doc="""\

        """)


class PiNullSink(object):
    """
    """

    def __init__(self, parent, source):
        self.renderer = mo.MMALNullSink()
        self.renderer.enable()
        self.renderer.inputs[0].connect(source).enable()

    def close(self):
        """

        """
        if self.renderer:
            self.renderer.close()
            self.renderer = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()
