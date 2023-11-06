
from __future__ import (
    unicode_literals,
    print_function,
    division,
    absolute_import,
    )

# Make Py2's str and range equivalent to Py3's
native_str = str
str = type('')
try:
    range = xrange
except NameError:
    pass

import io
import ctypes as ct
import warnings

import numpy as np
from numpy.lib.stride_tricks import as_strided

from . import mmalobj as mo, mmal
from .exc import (
    mmal_check,
    PiCameraValueError,
    PiCameraDeprecated,
    PiCameraPortDisabled,
    )


motion_dtype = np.dtype([
    (native_str('x'),   np.int8),
    (native_str('y'),   np.int8),
    (native_str('sad'), np.uint16),
    ])


def raw_resolution(resolution, splitter=False):
    """

    """
    width, height = resolution
    if splitter:
        fwidth = (width + 15) & ~15
    else:
        fwidth = (width + 31) & ~31
    fheight = (height + 15) & ~15
    return fwidth, fheight


def bytes_to_yuv(data, resolution):
    """
    Converts a bytes object containing YUV data to a `numpy`_ array.
    """
    width, height = resolution
    fwidth, fheight = raw_resolution(resolution)
    y_len = fwidth * fheight
    uv_len = (fwidth // 2) * (fheight // 2)
    if len(data) != (y_len + 2 * uv_len):
        raise PiCameraValueError(
            'Incorrect buffer length for resolution %dx%d' % (width, height))
    # Separate out the Y, U, and V values from the array
    a = np.frombuffer(data, dtype=np.uint8)
    Y = a[:y_len].reshape((fheight, fwidth))
    Uq = a[y_len:-uv_len].reshape((fheight // 2, fwidth // 2))
    Vq = a[-uv_len:].reshape((fheight // 2, fwidth // 2))

    U = np.empty_like(Y)
    V = np.empty_like(Y)
    U[0::2, 0::2] = Uq
    U[0::2, 1::2] = Uq
    U[1::2, 0::2] = Uq
    U[1::2, 1::2] = Uq
    V[0::2, 0::2] = Vq
    V[0::2, 1::2] = Vq
    V[1::2, 0::2] = Vq
    V[1::2, 1::2] = Vq
    # Stack the channels together and crop to the actual resolution
    return np.dstack((Y, U, V))[:height, :width]


def bytes_to_rgb(data, resolution):
    """
    Converts a bytes objects containing RGB/BGR data to a `numpy`_ array.
    """
    width, height = resolution
    fwidth, fheight = raw_resolution(resolution)
    # Workaround: output from the video splitter is rounded to 16x16 instead
    # of 32x16 (but only for RGB, and only when a resizer is not used)
    if len(data) != (fwidth * fheight * 3):
        fwidth, fheight = raw_resolution(resolution, splitter=True)
        if len(data) != (fwidth * fheight * 3):
            raise PiCameraValueError(
                'Incorrect buffer length for resolution %dx%d' % (width, height))
    # Crop to the actual resolution
    return np.frombuffer(data, dtype=np.uint8).\
            reshape((fheight, fwidth, 3))[:height, :width, :]


class PiArrayOutput(io.BytesIO):
    """

    """

    def __init__(self, camera, size=None):
        super(PiArrayOutput, self).__init__()
        self.camera = camera
        self.size = size
        self.array = None

    def close(self):
        super(PiArrayOutput, self).close()
        self.array = None

    def truncate(self, size=None):
        """

        """
        if size is not None:
            warnings.warn(
                PiCameraDeprecated(
                    ''))
        super(PiArrayOutput, self).truncate(size)
        if size is not None:
            self.seek(size)


class PiRGBArray(PiArrayOutput):
    """

    """

    def flush(self):
        super(PiRGBArray, self).flush()
        self.array = bytes_to_rgb(self.getvalue(), self.size or self.camera.resolution)


class PiYUVArray(PiArrayOutput):
    """

    """

    def __init__(self, camera, size=None):
        super(PiYUVArray, self).__init__(camera, size)
        self._rgb = None

    def flush(self):
        super(PiYUVArray, self).flush()
        self.array = bytes_to_yuv(self.getvalue(), self.size or self.camera.resolution)
        self._rgb = None

    @property
    def rgb_array(self):
        if self._rgb is None:
            # Apply the standard biases
            YUV = self.array.astype(float)
            YUV[:, :, 0]  = YUV[:, :, 0]  - 16  # Offset Y by 16
            YUV[:, :, 1:] = YUV[:, :, 1:] - 128 # Offset UV by 128
            # YUV conversion matrix from ITU-R BT.601 version (SDTV)
            #              Y       U       V
            M = np.array([[1.164,  0.000,  1.596],    # R
                          [1.164, -0.392, -0.813],    # G
                          [1.164,  2.017,  0.000]])   # B

            self._rgb = YUV.dot(M.T).clip(0, 255).astype(np.uint8)
        return self._rgb


class BroadcomRawHeader(ct.Structure):
    _fields_ = [
        ('name',          ct.c_char * 32),
        ('width',         ct.c_uint16),
        ('height',        ct.c_uint16),
        ('padding_right', ct.c_uint16),
        ('padding_down',  ct.c_uint16),
        ('dummy',         ct.c_uint32 * 6),
        ('transform',     ct.c_uint16),
        ('format',        ct.c_uint16),
        ('bayer_order',   ct.c_uint8),
        ('bayer_format',  ct.c_uint8),
        ]


class PiBayerArray(PiArrayOutput):
    """

    """
    BAYER_OFFSETS = {
        0: ((0, 0), (1, 0), (0, 1), (1, 1)),
        1: ((1, 0), (0, 0), (1, 1), (0, 1)),
        2: ((1, 1), (0, 1), (1, 0), (0, 0)),
        3: ((0, 1), (1, 1), (0, 0), (1, 0)),
        }

    def __init__(self, camera, output_dims=3):
        super(PiBayerArray, self).__init__(camera, size=None)
        if not (2 <= output_dims <= 3):
            raise PiCameraValueError('output_dims must be 2 or 3')
        self._demo = None
        self._header = None
        self._output_dims = output_dims

    @property
    def output_dims(self):
        return self._output_dims

    def _to_3d(self, array):
        array_3d = np.zeros(array.shape + (3,), dtype=array.dtype)
        (
            (ry, rx), (gy, gx), (Gy, Gx), (by, bx)
            ) = PiBayerArray.BAYER_OFFSETS[self._header.bayer_order]
        array_3d[ry::2, rx::2, 0] = array[ry::2, rx::2] # Red
        array_3d[gy::2, gx::2, 1] = array[gy::2, gx::2] # Green
        array_3d[Gy::2, Gx::2, 1] = array[Gy::2, Gx::2] # Green
        array_3d[by::2, bx::2, 2] = array[by::2, bx::2] # Blue
        return array_3d

    def flush(self):
        super(PiBayerArray, self).flush()
        self._demo = None
        offset = {
            'OV5647': {
                0: 6404096,
                1: 2717696,
                2: 6404096,
                3: 6404096,
                4: 1625600,
                5: 1233920,
                6: 445440,
                7: 445440,
                },
            'IMX219': {
                0: 10270208,
                1: 2678784,
                2: 10270208,
                3: 10270208,
                4: 2628608,
                5: 1963008,
                6: 1233920,
                7: 445440,
                },
            }[self.camera.revision.upper()][self.camera.sensor_mode]
        data = self.getvalue()[-offset:]
        if data[:4] != b'BRCM':
            raise PiCameraValueError('Unable to locate Bayer data at end of buffer')
      rom_buffer_copy(
            data[176:176 + ct.sizeof(BroadcomRawHeader)])
        data = np.frombuffer(data, dtype=np.uint8, offset=32768)

        crop = mo.PiResolution(
            self._header.width * 5 // 4,
            self._header.height)
        shape = mo.PiResolution(
            (((self._header.width + self._header.padding_right) * 5) + 3) // 4,
            (self._header.height + self._header.padding_down)
            ).pad()
        data = data.reshape((shape.height, shape.width))[:crop.height, :crop.width]

        data = data.astype(np.uint16) << 2
        for byte in range(4):
            data[:, byte::5] |= ((data[:, 4::5] >> (byte * 2)) & 3)
        self.array = np.zeros(
            (data.shape[0], data.shape[1] * 4 // 5), dtype=np.uint16)
        for i in range(4):
            self.array[:, i::4] = data[:, i::5]
        if self.output_dims == 3:
            self.array = self._to_3d(self.array)

    def demosaic(self):
        """

        """
        if self._demo is None:
            # Construct 3D representation of Bayer data (if necessary)
            if self.output_dims == 2:
                array_3d = self._to_3d(self.array)
            else:
                array_3d = self.array
            # Construct representation of the bayer pattern
            bayer = np.zeros(array_3d.shape, dtype=np.uint8)
            (
                (ry, rx), (gy, gx), (Gy, Gx), (by, bx)
                ) = PiBayerArray.BAYER_OFFSETS[self._header.bayer_order]
            bayer[ry::2, rx::2, 0] = 1 # Red
            bayer[gy::2, gx::2, 1] = 1 # Green
            bayer[Gy::2, Gx::2, 1] = 1 # Green
            bayer[by::2, bx::2, 2] = 1 # Blue

            window = (3, 3)
            borders = (window[0] - 1, window[1] - 1)
            border = (borders[0] // 2, borders[1] // 2)

            rgb = np.zeros((
                array_3d.shape[0] + borders[0],
                array_3d.shape[1] + borders[1],
                array_3d.shape[2]), dtype=array_3d.dtype)
            rgb[
                border[0]:rgb.shape[0] - border[0],
                border[1]:rgb.shape[1] - border[1],
                :] = array_3d
            bayer_pad = np.zeros((
                array_3d.shape[0] + borders[0],
                array_3d.shape[1] + borders[1],
                array_3d.shape[2]), dtype=bayer.dtype)
            bayer_pad[
                border[0]:bayer_pad.shape[0] - border[0],
                border[1]:bayer_pad.shape[1] - border[1],
                :] = bayer
            bayer = bayer_pad

            self._demo = np.empty(array_3d.shape, dtype=array_3d.dtype)
            for plane in range(3):
                p = rgb[..., plane]
                b = bayer[..., plane]
                pview = as_strided(p, shape=(
                    p.shape[0] - borders[0],
                    p.shape[1] - borders[1]) + window, strides=p.strides * 2)
                bview = as_strided(b, shape=(
                    b.shape[0] - borders[0],
                    b.shape[1] - borders[1]) + window, strides=b.strides * 2)
                psum = np.einsum('ijkl->ij', pview)
                bsum = np.einsum('ijkl->ij', bview)
                self._demo[..., plane] = psum // bsum
        return self._demo


class PiMotionArray(PiArrayOutput):
    """

    """

    def flush(self):
        super(PiMotionArray, self).flush()
        width, height = self.size or self.camera.resolution
        cols = ((width + 15) // 16) + 1
        rows = (height + 15) // 16
        b = self.getvalue()
        frames = len(b) // (cols * rows * motion_dtype.itemsize)
        self.array = np.frombuffer(b, dtype=motion_dtype).reshape((frames, rows, cols))


class PiAnalysisOutput(io.IOBase):
    """

    """

    def __init__(self, camera, size=None):
        super(PiAnalysisOutput, self).__init__()
        self.camera = camera
        self.size = size

    def writable(self):
        return True

    def write(self, b):
        return len(b)

    def analyze(self, array):
        """
        Stub method for users to override.
        """
        try:
            self.analyse(array)
            warnings.warn(
                PiCameraDeprecated(
                    'The analyse method is deprecated; use analyze (US '
                    'English spelling) instead'))
        except NotImplementedError:
            raise

    def analyse(self, array):
        """
        Deprecated alias of :meth:`analyze`.
        """
        raise NotImplementedError


class PiRGBAnalysis(PiAnalysisOutput):
    """

    """

    def write(self, b):
        result = super(PiRGBAnalysis, self).write(b)
        self.analyze(bytes_to_rgb(b, self.size or self.camera.resolution))
        return result


class PiYUVAnalysis(PiAnalysisOutput):
    """

    """

    def write(self, b):
        result = super(PiYUVAnalysis, self).write(b)
        self.analyze(bytes_to_yuv(b, self.size or self.camera.resolution))
        return result


class PiMotionAnalysis(PiAnalysisOutput):
    """

    """

    def __init__(self, camera, size=None):
        super(PiMotionAnalysis, self).__init__(camera, size)
        self.cols = None
        self.rows = None

    def write(self, b):
        result = super(PiMotionAnalysis, self).write(b)
        if self.cols is None:
            width, height = self.size or self.camera.resolution
            self.cols = ((width + 15) // 16) + 1
            self.rows = (height + 15) // 16
        self.analyze(
                np.frombuffer(b, dtype=motion_dtype).\
                reshape((self.rows, self.cols)))
        return result


class MMALArrayBuffer(mo.MMALBuffer):
    __slots__ = ('_shape',)

    def __init__(self, port, buf):
        super(MMALArrayBuffer, self).__init__(buf)
        width = port._format[0].es[0].video.width
        height = port._format[0].es[0].video.height
        bpp = self.size // (width * height)
        self.offset = 0
        self.length = width * height * bpp
        self._shape = (height, width, bpp)

    def __enter__(self):
        mmal_check(
            mmal.mmal_buffer_header_mem_lock(self._buf),
            prefix='unable to lock buffer header memory')
        assert self.offset == 0
        return np.frombuffer(
            ct.cast(
                self._buf[0].data,
                ct.POINTER(ct.c_uint8 * self._buf[0].alloc_size)).contents,
            dtype=np.uint8, count=self.length).reshape(self._shape)

    def __exit__(self, *exc):
        mmal.mmal_buffer_header_mem_unlock(self._buf)
        return False


class PiArrayTransform(mo.MMALPythonComponent):
    """

    """
    __slots__ = ()

    def __init__(self, formats=('rgb', 'bgr', 'rgba', 'bgra')):
        super(PiArrayTransform, self).__init__()
        if isinstance(formats, bytes):
            formats = formats.decode('ascii')
        if isinstance(formats, str):
            formats = (formats,)
        try:
            formats = {
                {
                    'rgb': mmal.MMAL_ENCODING_RGB24,
                    'bgr': mmal.MMAL_ENCODING_BGR24,
                    'rgba': mmal.MMAL_ENCODING_RGBA,
                    'bgra': mmal.MMAL_ENCODING_BGRA,
                    }[fmt]
                for fmt in formats
                }
        except KeyError as e:
            raise PiCameraValueError(
                'PiArrayTransform cannot handle format %s' % str(e))
        self.inputs[0].supported_formats = formats
        self.outputs[0].supported_formats = formats

    def _callback(self, port, source_buf):
        try:
            target_buf = self.outputs[0].get_buffer(False)
        except PiCameraPortDisabled:
            return False
        if target_buf:
            target_buf.copy_meta(source_buf)
            result = self.transform(
                MMALArrayBuffer(port, source_buf._buf),
                MMALArrayBuffer(self.outputs[0], target_buf._buf))
            try:
                self.outputs[0].send_buffer(target_buf)
            except PiCameraPortDisabled:
                return False
        return False

    def transform(self, source, target):
        """

        """
        return False
