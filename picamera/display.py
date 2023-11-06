
from __future__ import (
    unicode_literals,
    print_function,
    division,
    absolute_import,
    )

# Make Py2's str equivalent to Py3's
str = type('')

import mimetypes
import ctypes as ct
from functools import reduce
from operator import or_

from . import bcm_host, mmalobj as mo, mmal
from .encoders import PiCookedOneImageEncoder, PiRawOneImageEncoder
from .exc import PiCameraRuntimeError, PiCameraValueError


class PiDisplay(object):
    __slots__ = (
        '_display',
        '_info',
        '_transform',
        '_exif_tags',
        )

    _ROTATIONS = {
        bcm_host.DISPMANX_NO_ROTATE:  0,
        bcm_host.DISPMANX_ROTATE_90:  90,
        bcm_host.DISPMANX_ROTATE_180: 180,
        bcm_host.DISPMANX_ROTATE_270: 270,
        }
    _ROTATIONS_R = {v: k for k, v in _ROTATIONS.items()}
    _ROTATIONS_MASK = reduce(or_, _ROTATIONS.keys(), 0)

    RAW_FORMATS = {
        'yuv',
        'rgb',
        'rgba',
        'bgr',
        'bgra',
        }

    def __init__(self, display_num=0):
        bcm_host.bcm_host_init()
        self._exif_tags = {}
        self._display = bcm_host.vc_dispmanx_display_open(display_num)
        self._transform = bcm_host.DISPMANX_NO_ROTATE
        if not self._display:
            raise PiCameraRuntimeError('unable to open display %d' % display_num)
        self._info = bcm_host.DISPMANX_MODEINFO_T()
        if bcm_host.vc_dispmanx_display_get_info(self._display, self._info):
            raise PiCameraRuntimeError('unable to get display info')

    def close(self):
        bcm_host.vc_dispmanx_display_close(self._display)
        self._display = None

    @property
    def closed(self):
        return self._display is None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()

    def _get_output_format(self, output):
        """

        """
        if isinstance(output, bytes):
            filename = output.decode('utf-8')
        elif isinstance(output, str):
            filename = output
        else:
            try:
                filename = output.name
            except AttributeError:
                raise PiCameraValueError(
                    'Format must be specified when output has no filename')
        (type, encoding) = mimetypes.guess_type(filename, strict=False)
        if not type:
            raise PiCameraValueError(
                'Unable to determine type from filename %s' % filename)
        return type

    def _get_image_format(self, output, format=None):
        """

        """
        if isinstance(format, bytes):
            format = format.decode('utf-8')
        format = format or self._get_output_format(output)
        format = (
            format[6:] if format.startswith('image/') else
            format)
        if format == 'x-ms-bmp':
            format = 'bmp'
        return format

    def _get_image_encoder(self, output_port, format, resize, **options):
        """

        """
        encoder_class = (
                PiRawOneImageEncoder if format in self.RAW_FORMATS else
                PiCookedOneImageEncoder)
        return encoder_class(
                self, None, output_port, format, resize, **options)

    def capture(self, output, format=None, resize=None, **options):
        format = self._get_image_format(output, format)
        if format == 'yuv':
            raise PiCameraValueError('YUV format is unsupported at this time')
        res = self.resolution
        if (self._info.transform & bcm_host.DISPMANX_ROTATE_90) or (
                self._info.transform & bcm_host.DISPMANX_ROTATE_270):
            res = res.transpose()
        transform = self._transform
        if (transform & bcm_host.DISPMANX_ROTATE_90) or (
                transform & bcm_host.DISPMANX_ROTATE_270):
            res = res.transpose()
        source = mo.MMALPythonSource()
        source.outputs[0].format = mmal.MMAL_ENCODING_RGB24
        if format == 'bgr':
            source.outputs[0].format = mmal.MMAL_ENCODING_BGR24
            transform |= bcm_host.DISPMANX_SNAPSHOT_SWAP_RED_BLUE
        source.outputs[0].framesize = res
        source.outputs[0].commit()
        encoder = self._get_image_encoder(
            source.outputs[0], format, resize, **options)
        try:
            encoder.start(output)
            try:
                pitch = res.pad(width=16).width * 3
                image_ptr = ct.c_uint32()
                resource = bcm_host.vc_dispmanx_resource_create(
                    bcm_host.VC_IMAGE_RGB888, res.width, res.height, image_ptr)
                if not resource:
                    raise PiCameraRuntimeError(
                        'unable to allocate resource for capture')
                try:
                    buf = source.outputs[0].get_buffer()
                    if bcm_host.vc_dispmanx_snapshot(self._display, resource, transform):
                        raise PiCameraRuntimeError('failed to capture snapshot')
                    rect = bcm_host.VC_RECT_T(0, 0, res.width, res.height)
                    if bcm_host.vc_dispmanx_resource_read_data(resource, rect, buf._buf[0].data, pitch):
                        raise PiCameraRuntimeError('failed to read snapshot')
                    buf._buf[0].length = pitch * res.height
                    buf._buf[0].flags = (
                        mmal.MMAL_BUFFER_HEADER_FLAG_EOS |
                        mmal.MMAL_BUFFER_HEADER_FLAG_FRAME_END
                        )
                finally:
                    bcm_host.vc_dispmanx_resource_delete(resource)
                source.outputs[0].send_buffer(buf)
                # XXX Anything more intelligent than a 10 second default?
                encoder.wait(10)
            finally:
                encoder.stop()
        finally:
            encoder.close()

    def _calculate_transform(self):
        """

        """
        r = PiDisplay._ROTATIONS[self._info.transform & PiDisplay._ROTATIONS_MASK]
        r = (360 - r) % 360 # undo the native rotation
        r = (r + self.rotation) % 360 # add selected rotation
        result = PiDisplay._ROTATIONS_R[r]
        result |= self._info.transform & ( # undo flips by re-doing them
            bcm_host.DISPMANX_FLIP_HRIZ | bcm_host.DISPMANX_FLIP_VERT
            )
        return result

    @property
    def resolution(self):
        """
        Retrieves the resolution of the display device.
        """
        return mo.PiResolution(width=self._info.width, height=self._info.height)

    def _get_hflip(self):
        return bool(self._info.transform & bcm_host.DISPMANX_FLIP_HRIZ)
    def _set_hflip(self, value):
        if value:
            self._info.transform |= bcm_host.DISPMANX_FLIP_HRIZ
        else:
            self._info.transform &= ~bcm_host.DISPMANX_FLIP_HRIZ
    hflip = property(_get_hflip, _set_hflip, doc="""\

        """)

    def _get_vflip(self):
        return bool(self._info.transform & bcm_host.DISPMANX_FLIP_VERT)
    def _set_vflip(self, value):
        if value:
            self._info.transform |= bcm_host.DISPMANX_FLIP_VERT
        else:
            self._info.transform &= ~bcm_host.DISPMANX_FLIP_VERT
    vflip = property(_get_vflip, _set_vflip, doc="""\

        """)

    def _get_rotation(self):
        return PiDisplay._ROTATIONS[self._transform & PiDisplay._ROTATIONS_MASK]
    def _set_rotation(self, value):
        try:
            self._transform = (
                self._transform & ~PiDisplay._ROTATIONS_MASK) | PiDisplay._ROTATIONS_R[value]
        except KeyError:
            raise PiCameraValueError('invalid rotation %d' % value)
    rotation = property(_get_rotation, _set_rotation, doc="""\

        """)

    def _get_exif_tags(self):
        return self._exif_tags
    def _set_exif_tags(self, value):
        self._exif_tags = {k: v for k, v in value.items()}
    exif_tags = property(_get_exif_tags, _set_exif_tags)

