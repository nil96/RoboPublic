
from __future__ import (
    unicode_literals,
    print_function,
    division,
    absolute_import,
    )

# Make Py2's str and range equivalent to Py3's
str = type('')

import datetime
import threading
import warnings
import ctypes as ct

from . import bcm_host, mmal, mmalobj as mo
from .frames import PiVideoFrame, PiVideoFrameType
from .exc import (
    PiCameraMMALError,
    PiCameraValueError,
    PiCameraIOError,
    PiCameraRuntimeError,
    PiCameraResizerEncoding,
    PiCameraAlphaStripping,
    PiCameraResolutionRounded,
    )


class PiEncoder(object):
    """

    """

    DEBUG = 0
    encoder_type = None

    def __init__(
            self, parent, camera_port, input_port, format, resize, **options):
        self.parent = parent
        self.encoder = None
        self.resizer = None
        self.camera_port = camera_port
        self.input_port = input_port
        self.output_port = None
        self.outputs_lock = threading.Lock() # protects access to self.outputs
        self.outputs = {}
        self.exception = None
        self.event = threading.Event()
        try:
            if parent and parent.closed:
                raise PiCameraRuntimeError("Camera is closed")
            if resize:
                self._create_resizer(*mo.to_resolution(resize))
            self._create_encoder(format, **options)
            if self.encoder:
                self.encoder.connection.enable()
            if self.resizer:
                self.resizer.connection.enable()
        except:
            self.close()
            raise

    def _create_resizer(self, width, height):
        """

        """
        self.resizer = mo.MMALResizer()
        self.resizer.inputs[0].connect(self.input_port)
        self.resizer.outputs[0].copy_from(self.resizer.inputs[0])
        self.resizer.outputs[0].format = mmal.MMAL_ENCODING_I420
        self.resizer.outputs[0].framesize = (width, height)
        self.resizer.outputs[0].commit()

    def _create_encoder(self, format):
        """

        """
        assert not self.encoder
        self.encoder = self.encoder_type()
        self.output_port = self.encoder.outputs[0]
        if self.resizer:
            self.encoder.inputs[0].connect(self.resizer.outputs[0])
        else:
            self.encoder.inputs[0].connect(self.input_port)
        self.encoder.outputs[0].copy_from(self.encoder.inputs[0])


    def _callback(self, port, buf):
        """

        """
        if self.DEBUG > 1:
            print(repr(buf))
        try:
            stop = self._callback_write(buf)
        except Exception as e:
            stop = True
            self.exception = e
        if stop:
            self.event.set()
        return stop

    def _callback_write(self, buf, key=PiVideoFrameType.frame):
        """

        """
        if buf.length:
            with self.outputs_lock:
                try:
                    output = self.outputs[key][0]
                    written = output.write(buf.data)
                except KeyError:

                    pass
                else:
                    # Ignore None return value; most Python 2 streams have
                    # no return value for write()
                    if (written is not None) and (written != buf.length):
                        raise PiCameraIOError(
                            "Failed to write %d bytes from buffer to "
                            "output %r" % (buf.length, output))
        return bool(buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_EOS)

    def _open_output(self, output, key=PiVideoFrameType.frame):
        """

        """
        with self.outputs_lock:
            self.outputs[key] = mo.open_stream(output)

    def _close_output(self, key=PiVideoFrameType.frame):
        """

        """
        with self.outputs_lock:
            try:
                (output, opened) = self.outputs.pop(key)
            except KeyError:
                pass
            else:
                mo.close_stream(output, opened)

    @property
    def active(self):
        """
        Returns ``True`` if the MMAL encoder exists and is enabled.
        """
        try:
            return bool(self.output_port.enabled)
        except AttributeError:
            # output_port can be None; avoid a (demonstrated) race condition
            # by catching AttributeError
            return False

    def start(self, output):
        """

        """
        self.event.clear()
        self.exception = None
        self._open_output(output)
        with self.parent._encoders_lock:
            self.output_port.enable(self._callback)
            if self.DEBUG > 0:
                mo.print_pipeline(self.output_port)
            self.parent._start_capture(self.camera_port)

    def wait(self, timeout=None):
        """

        """
        result = self.event.wait(timeout)
        if result:
            self.stop()
            # Check whether the callback set an exception
            if self.exception:
                raise self.exception
        return result

    def stop(self):

        if self.active:
            if self.parent and self.camera_port:
                with self.parent._encoders_lock:
                    self.parent._stop_capture(self.camera_port)
            self.output_port.disable()
        self.event.set()
        self._close_output()

    def close(self):

        self.stop()
        if self.encoder:
            self.encoder.disconnect()
        if self.resizer:
            self.resizer.disconnect()
        if self.encoder:
            self.encoder.close()
            self.encoder = None
        if self.resizer:
            self.resizer.close()
            self.resizer = None
        self.output_port = None


class MMALBufferAlphaStrip(mo.MMALBuffer):
    """

    """

    def __init__(self, buf):
        super(MMALBufferAlphaStrip, self).__init__(buf)
        self._stripped = bytearray(super(MMALBufferAlphaStrip, self).data)
        del self._stripped[3::4]

    @property
    def length(self):
        return len(self._stripped)

    @property
    def data(self):
        return self._stripped


class PiRawMixin(PiEncoder):
    """

    """

    RAW_ENCODINGS = {
        # name   mmal-encoding             bytes-per-pixel
        'yuv':  (mmal.MMAL_ENCODING_I420,  1.5),
        'rgb':  (mmal.MMAL_ENCODING_RGB24, 3),
        'rgba': (mmal.MMAL_ENCODING_RGBA,  4),
        'bgr':  (mmal.MMAL_ENCODING_BGR24, 3),
        'bgra': (mmal.MMAL_ENCODING_BGRA,  4),
        }

    def __init__(
            self, parent, camera_port, input_port, format, resize, **options):
        encoding, bpp = self.RAW_ENCODINGS[format]

        if resize is None and encoding != mmal.MMAL_ENCODING_I420:
            input_port.format = encoding
            try:
                input_port.commit()
            except PiCameraMMALError as e:
                if e.status != mmal.MMAL_EINVAL:
                    raise
                resize = input_port.framesize
                warnings.warn(
                    PiCameraResizerEncoding(
                        "))

        self._strip_alpha = False
        if resize:
            width, height = resize
            try:
                format = {
                    'rgb': 'rgba',
                    'bgr': 'bgra',
                    }[format]
                self._strip_alpha = True
                warnings.warn(
                    PiCameraAlphaStripping(
                        "using alpha-stripping to convert to non-alpha "
                        "format; you may find the equivalent alpha format "
                        "faster"))
            except KeyError:
                pass
        else:
            width, height = input_port.framesize

        if not resize and format != 'yuv' and input_port.name.startswith('vc.ril.video_splitter'):

            fwidth = bcm_host.VCOS_ALIGN_UP(width, 16)
        else:
            fwidth = bcm_host.VCOS_ALIGN_UP(width, 32)
        fheight = bcm_host.VCOS_ALIGN_UP(height, 16)
        if fwidth != width or fheight != height:
            warnings.warn(
                PiCameraResolutionRounded(
                    "frame size rounded up from %dx%d to %dx%d" % (
                        width, height, fwidth, fheight)))
        if resize:
            resize = (fwidth, fheight)

        self._frame_size = int(fwidth * fheight * bpp)
        super(PiRawMixin, self).__init__(
                parent, camera_port, input_port, format, resize, **options)

    def _create_encoder(self, format):
        """

        """
        if self.resizer:
            self.output_port = self.resizer.outputs[0]
        else:
            self.output_port = self.input_port
        try:
            self.output_port.format = self.RAW_ENCODINGS[format][0]
        except KeyError:
            raise PiCameraValueError('unknown format %s' % format)
        self.output_port.commit()

    def _callback_write(self, buf, key=PiVideoFrameType.frame):
        """

        """
        if self._strip_alpha:
            return super(PiRawMixin, self)._callback_write(MMALBufferAlphaStrip(buf._buf), key)
        else:
            return super(PiRawMixin, self)._callback_write(buf, key)


class PiVideoEncoder(PiEncoder):
    """

    """

    encoder_type = mo.MMALVideoEncoder

    def __init__(
            self, parent, camera_port, input_port, format, resize, **options):
        super(PiVideoEncoder, self).__init__(
                parent, camera_port, input_port, format, resize, **options)
        self._next_output = []
        self._split_frame = None
        self.frame = None

    def _create_encoder(
            self, format, bitrate=17000000, intra_period=None, profile='high',
            level='4', quantization=0, quality=0, inline_headers=True,
            sei=False, sps_timing=False, motion_output=None,
            intra_refresh=None):
        """

        """
        super(PiVideoEncoder, self)._create_encoder(format)

        # XXX Remove quantization in 2.0
        quality = quality or quantization

        try:
            self.output_port.format = {
                'h264':  mmal.MMAL_ENCODING_H264,
                'mjpeg': mmal.MMAL_ENCODING_MJPEG,
                }[format]
        except KeyError:
            raise PiCameraValueError('Unsupported format %s' % format)

        if format == 'h264':
            try:
                profile = {
                    'baseline':    mmal.MMAL_VIDEO_PROFILE_H264_BASELINE,
                    'main':        mmal.MMAL_VIDEO_PROFILE_H264_MAIN,
                    #'extended':    mmal.MMAL_VIDEO_PROFILE_H264_EXTENDED,
                    'high':        mmal.MMAL_VIDEO_PROFILE_H264_HIGH,
                    'constrained': mmal.MMAL_VIDEO_PROFILE_H264_CONSTRAINED_BASELINE,
                    }[profile]
            except KeyError:
                raise PiCameraValueError("Invalid H.264 profile %s" % profile)
            try:
                level = {
                    '1':   mmal.MMAL_VIDEO_LEVEL_H264_1,
                    '1.0': mmal.MMAL_VIDEO_LEVEL_H264_1,
                    '1b':  mmal.MMAL_VIDEO_LEVEL_H264_1b,
                    '1.1': mmal.MMAL_VIDEO_LEVEL_H264_11,
                    '1.2': mmal.MMAL_VIDEO_LEVEL_H264_12,
                    '1.3': mmal.MMAL_VIDEO_LEVEL_H264_13,
                    '2':   mmal.MMAL_VIDEO_LEVEL_H264_2,
                    '2.0': mmal.MMAL_VIDEO_LEVEL_H264_2,
                    '2.1': mmal.MMAL_VIDEO_LEVEL_H264_21,
                    '2.2': mmal.MMAL_VIDEO_LEVEL_H264_22,
                    '3':   mmal.MMAL_VIDEO_LEVEL_H264_3,
                    '3.0': mmal.MMAL_VIDEO_LEVEL_H264_3,
                    '3.1': mmal.MMAL_VIDEO_LEVEL_H264_31,
                    '3.2': mmal.MMAL_VIDEO_LEVEL_H264_32,
                    '4':   mmal.MMAL_VIDEO_LEVEL_H264_4,
                    '4.0': mmal.MMAL_VIDEO_LEVEL_H264_4,
                    '4.1': mmal.MMAL_VIDEO_LEVEL_H264_41,
                    '4.2': mmal.MMAL_VIDEO_LEVEL_H264_42,
                    }[level]
            except KeyError:
                raise PiCameraValueError("Invalid H.264 level %s" % level)

            # From https://en.wikipedia.org/wiki/H.264/MPEG-4_AVC#Levels
            bitrate_limit = {
                # level, high-profile:  bitrate
                (mmal.MMAL_VIDEO_LEVEL_H264_1,  False): 64000,
                (mmal.MMAL_VIDEO_LEVEL_H264_1b, False): 128000,
                (mmal.MMAL_VIDEO_LEVEL_H264_11, False): 192000,
                (mmal.MMAL_VIDEO_LEVEL_H264_12, False): 384000,
                (mmal.MMAL_VIDEO_LEVEL_H264_13, False): 768000,
                (mmal.MMAL_VIDEO_LEVEL_H264_2,  False): 2000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_21, False): 4000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_22, False): 4000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_3,  False): 10000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_31, False): 14000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_32, False): 20000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_4,  False): 20000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_41, False): 50000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_42, False): 50000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_1,  True):  80000,
                (mmal.MMAL_VIDEO_LEVEL_H264_1b, True):  160000,
                (mmal.MMAL_VIDEO_LEVEL_H264_11, True):  240000,
                (mmal.MMAL_VIDEO_LEVEL_H264_12, True):  480000,
                (mmal.MMAL_VIDEO_LEVEL_H264_13, True):  960000,
                (mmal.MMAL_VIDEO_LEVEL_H264_2,  True):  2500000,
                (mmal.MMAL_VIDEO_LEVEL_H264_21, True):  5000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_22, True):  5000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_3,  True):  12500000,
                (mmal.MMAL_VIDEO_LEVEL_H264_31, True):  17500000,
                (mmal.MMAL_VIDEO_LEVEL_H264_32, True):  25000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_4,  True):  25000000,
                (mmal.MMAL_VIDEO_LEVEL_H264_41, True):  62500000,
                (mmal.MMAL_VIDEO_LEVEL_H264_42, True):  62500000,
                }[level, profile == mmal.MMAL_VIDEO_PROFILE_H264_HIGH]
            if bitrate > bitrate_limit:
                raise PiCameraValueError(
                    '' %
                    (bitrate, bitrate_limit))
            self.output_port.bitrate = bitrate
            self.output_port.commit()

            # Again, from https://en.wikipedia.org/wiki/H.264/MPEG-4_AVC#Levels
            macroblocks_per_s_limit, macroblocks_limit = {
                #level: macroblocks/s, macroblocks
                mmal.MMAL_VIDEO_LEVEL_H264_1:  (1485,   99),
                mmal.MMAL_VIDEO_LEVEL_H264_1b: (1485,   99),
                mmal.MMAL_VIDEO_LEVEL_H264_11: (3000,   396),
                mmal.MMAL_VIDEO_LEVEL_H264_12: (6000,   396),
                mmal.MMAL_VIDEO_LEVEL_H264_13: (11880,  396),
                mmal.MMAL_VIDEO_LEVEL_H264_2:  (11880,  396),
                mmal.MMAL_VIDEO_LEVEL_H264_21: (19800,  792),
                mmal.MMAL_VIDEO_LEVEL_H264_22: (20250,  1620),
                mmal.MMAL_VIDEO_LEVEL_H264_3:  (40500,  1620),
                mmal.MMAL_VIDEO_LEVEL_H264_31: (108000, 3600),
                mmal.MMAL_VIDEO_LEVEL_H264_32: (216000, 5120),
                mmal.MMAL_VIDEO_LEVEL_H264_4:  (245760, 8192),
                mmal.MMAL_VIDEO_LEVEL_H264_41: (245760, 8192),
                mmal.MMAL_VIDEO_LEVEL_H264_42: (522240, 8704),
                }[level]
            w, h = self.output_port.framesize
            w = bcm_host.VCOS_ALIGN_UP(w, 16) >> 4
            h = bcm_host.VCOS_ALIGN_UP(h, 16) >> 4
            if w * h > macroblocks_limit:
                raise PiCameraValueError(
                    %
                    (self.output_port.framesize, macroblocks_limit))
            if self.parent:
                if self.parent.framerate == 0:

                    framerate = self.parent.framerate_range[1]
                else:
                    framerate = (
                        self.parent.framerate + self.parent.framerate_delta)
            else:
                framerate = self.input_port.framerate
            if w * h * framerate > macroblocks_per_s_limit:
                raise PiCameraValueError(
                    '
                    'level' % macroblocks_per_s_limit)

            mp = mmal.MMAL_PARAMETER_VIDEO_PROFILE_T(
                    mmal.MMAL_PARAMETER_HEADER_T(
                        mmal.MMAL_PARAMETER_PROFILE,
                        ct.sizeof(mmal.MMAL_PARAMETER_VIDEO_PROFILE_T),
                        ),
                    )
            mp.profile[0].profile = profile
            mp.profile[0].level = level
            self.output_port.params[mmal.MMAL_PARAMETER_PROFILE] = mp

            if inline_headers:
                self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_ENCODE_INLINE_HEADER] = True
            if sei:
                self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_ENCODE_SEI_ENABLE] = True
            if sps_timing:
                self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_ENCODE_SPS_TIMING] = True
            if motion_output is not None:
                self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_ENCODE_INLINE_VECTORS] = True

            # We need the intra-period to calculate the SPS header timeout in
            # the split method below. If one is not set explicitly, query the
            # encoder's default
            if intra_period is not None:
                self.output_port.params[mmal.MMAL_PARAMETER_INTRAPERIOD] = intra_period
                self._intra_period = intra_period
            else:
                self._intra_period = self.output_port.params[mmal.MMAL_PARAMETER_INTRAPERIOD]

            if intra_refresh is not None:
                # Get the intra-refresh structure first as there are several
                # other fields in it which we don't wish to overwrite
                mp = self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_INTRA_REFRESH]
                try:
                    mp.refresh_mode = {
                        'cyclic':     mmal.MMAL_VIDEO_INTRA_REFRESH_CYCLIC,
                        'adaptive':   mmal.MMAL_VIDEO_INTRA_REFRESH_ADAPTIVE,
                        'both':       mmal.MMAL_VIDEO_INTRA_REFRESH_BOTH,
                        'cyclicrows': mmal.MMAL_VIDEO_INTRA_REFRESH_CYCLIC_MROWS,
                        }[intra_refresh]
                except KeyError:
                    raise PiCameraValueError(
                        "Invalid intra_refresh %s" % intra_refresh)
                self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_INTRA_REFRESH] = mp

        elif format == 'mjpeg':
            self.output_port.bitrate = bitrate
            self.output_port.commit()

            self._intra_period = 1

        if quality:
            self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_ENCODE_INITIAL_QUANT] = quality
            self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_ENCODE_MIN_QUANT] = quality
            self.output_port.params[mmal.MMAL_PARAMETER_VIDEO_ENCODE_MAX_QUANT] = quality

        self.encoder.inputs[0].params[mmal.MMAL_PARAMETER_VIDEO_IMMUTABLE_INPUT] = True
        self.encoder.enable()

    def start(self, output, motion_output=None):
        """
        Extended to initialize video frame meta-data tracking.
        """
        self.frame = PiVideoFrame(
                index=0,
                frame_type=None,
                frame_size=0,
                video_size=0,
                split_size=0,
                timestamp=0,
                complete=False,
                )
        if motion_output is not None:
            self._open_output(motion_output, PiVideoFrameType.motion_data)
        super(PiVideoEncoder, self).start(output)

    def stop(self):
        super(PiVideoEncoder, self).stop()
        self._close_output(PiVideoFrameType.motion_data)

    def request_key_frame(self):
        """

        """
        self.encoder.control.params[mmal.MMAL_PARAMETER_VIDEO_REQUEST_I_FRAME] = True

    def split(self, output, motion_output=None):
        """
        Called to switch the encoder's output.

     .
        """
        with self.outputs_lock:
            outputs = {}
            if output is not None:
                outputs[PiVideoFrameType.frame] = output
            if motion_output is not None:
                outputs[PiVideoFrameType.motion_data] = motion_output
            self._next_output.append(outputs)

        if self.parent:
            framerate = self.parent.framerate + self.parent.framerate_delta
        else:
            framerate = self.input_port.framerate
        timeout = max(15.0, float(self._intra_period / framerate) * 3.0)
        if self._intra_period > 1:
            self.request_key_frame()
        if not self.event.wait(timeout):
            raise PiCameraRuntimeError('Timed out waiting for a split point')
        self.event.clear()
        return self._split_frame

    def _callback_write(self, buf, key=PiVideoFrameType.frame):
        """

        """
        last_frame = self.frame
        this_frame = PiVideoFrame(
            index=
                last_frame.index + 1
                if last_frame.complete else
                last_frame.index,
            frame_type=
                PiVideoFrameType.key_frame
                if buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_KEYFRAME else
                PiVideoFrameType.sps_header
                if buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_CONFIG else
                PiVideoFrameType.motion_data
                if buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_CODECSIDEINFO else
                PiVideoFrameType.frame,
            frame_size=
                buf.length
                if last_frame.complete else
                last_frame.frame_size + buf.length,
            video_size=
                last_frame.video_size
                if buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_CODECSIDEINFO else
                last_frame.video_size + buf.length,
            split_size=
                last_frame.split_size
                if buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_CODECSIDEINFO else
                last_frame.split_size + buf.length,
            timestamp=
                # Time cannot go backwards, so if we've got an unknown pts
                # simply repeat the last one
                last_frame.timestamp
                if buf.pts in (0, mmal.MMAL_TIME_UNKNOWN) else
                buf.pts,
            complete=
                bool(buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_FRAME_END)
            )
        if self._intra_period == 1 or (buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_CONFIG):
            with self.outputs_lock:
                try:
                    new_outputs = self._next_output.pop(0)
                except IndexError:
                    new_outputs = None
            if new_outputs:
                for new_key, new_output in new_outputs.items():
                    self._close_output(new_key)
                    self._open_output(new_output, new_key)
                    if new_key == PiVideoFrameType.frame:
                        this_frame = PiVideoFrame(
                                index=this_frame.index,
                                frame_type=this_frame.frame_type,
                                frame_size=this_frame.frame_size,
                                video_size=this_frame.video_size,
                                split_size=0,
                                timestamp=this_frame.timestamp,
                                complete=this_frame.complete,
                                )
                self._split_frame = this_frame
                self.event.set()
        if buf.flags & mmal.MMAL_BUFFER_HEADER_FLAG_CODECSIDEINFO:
            key = PiVideoFrameType.motion_data
        self.frame = this_frame
        return super(PiVideoEncoder, self)._callback_write(buf, key)


class PiCookedVideoEncoder(PiVideoEncoder):
    """

    """


class PiRawVideoEncoder(PiRawMixin, PiVideoEncoder):
    """

    """

    def _create_encoder(self, format):
        super(PiRawVideoEncoder, self)._create_encoder(format)

        self._intra_period = 1


class PiImageEncoder(PiEncoder):
    """

    """

    encoder_type = mo.MMALImageEncoder

    def _create_encoder(
            self, format, quality=85, thumbnail=(64, 48, 35), restart=0):
        """

        """
        super(PiImageEncoder, self)._create_encoder(format)

        try:
            self.output_port.format = {
                'jpeg': mmal.MMAL_ENCODING_JPEG,
                'png':  mmal.MMAL_ENCODING_PNG,
                'gif':  mmal.MMAL_ENCODING_GIF,
                'bmp':  mmal.MMAL_ENCODING_BMP,
                }[format]
        except KeyError:
            raise PiCameraValueError("Unsupported format %s" % format)
        self.output_port.commit()

        if format == 'jpeg':
            self.output_port.params[mmal.MMAL_PARAMETER_JPEG_Q_FACTOR] = quality
            if restart > 0:
                # Don't set if zero as old firmwares don't support this param
                self.output_port.params[mmal.MMAL_PARAMETER_JPEG_RESTART_INTERVAL] = restart
            if thumbnail is None:
                mp = mmal.MMAL_PARAMETER_THUMBNAIL_CONFIG_T(
                    mmal.MMAL_PARAMETER_HEADER_T(
                        mmal.MMAL_PARAMETER_THUMBNAIL_CONFIGURATION,
                        ct.sizeof(mmal.MMAL_PARAMETER_THUMBNAIL_CONFIG_T)
                        ),
                    0, 0, 0, 0)
            else:
                mp = mmal.MMAL_PARAMETER_THUMBNAIL_CONFIG_T(
                    mmal.MMAL_PARAMETER_HEADER_T(
                        mmal.MMAL_PARAMETER_THUMBNAIL_CONFIGURATION,
                        ct.sizeof(mmal.MMAL_PARAMETER_THUMBNAIL_CONFIG_T)
                        ),
                    1, *thumbnail)
            self.encoder.control.params[mmal.MMAL_PARAMETER_THUMBNAIL_CONFIGURATION] = mp

        self.encoder.enable()


class PiOneImageEncoder(PiImageEncoder):
    """

    """

    def _callback_write(self, buf, key=PiVideoFrameType.frame):
        return (
            super(PiOneImageEncoder, self)._callback_write(buf, key)
            ) or bool(
            buf.flags & (
                mmal.MMAL_BUFFER_HEADER_FLAG_FRAME_END |
                mmal.MMAL_BUFFER_HEADER_FLAG_TRANSMISSION_FAILED)
            )


class PiMultiImageEncoder(PiImageEncoder):
    """

    """

    def _open_output(self, outputs, key=PiVideoFrameType.frame):
        self._output_iter = iter(outputs)
        self._next_output(key)

    def _next_output(self, key=PiVideoFrameType.frame):
        """
        This method moves output to the next item from the iterable passed to
        :meth:`~PiEncoder.start`.
        """
        self._close_output(key)
        super(PiMultiImageEncoder, self)._open_output(next(self._output_iter), key)

    def _callback_write(self, buf, key=PiVideoFrameType.frame):
        try:
            if (
                super(PiMultiImageEncoder, self)._callback_write(buf, key)
                ) or bool(
                buf.flags & (
                    mmal.MMAL_BUFFER_HEADER_FLAG_FRAME_END |
                    mmal.MMAL_BUFFER_HEADER_FLAG_TRANSMISSION_FAILED)
                ):
                self._next_output(key)
            return False
        except StopIteration:
            return True


class PiCookedOneImageEncoder(PiOneImageEncoder):
    """

    """

    exif_encoding = 'ascii'

    def __init__(
            self, parent, camera_port, input_port, format, resize, **options):
        super(PiCookedOneImageEncoder, self).__init__(
                parent, camera_port, input_port, format, resize, **options)
        if parent:
            self.exif_tags = self.parent.exif_tags
        else:
            self.exif_tags = {}

    def _add_exif_tag(self, tag, value):
        # Format the tag and value into an appropriate bytes string, encoded
        # with the Exif encoding (ASCII)
        if isinstance(tag, str):
            tag = tag.encode(self.exif_encoding)
        if isinstance(value, str):
            value = value.encode(self.exif_encoding)
        elif isinstance(value, datetime.datetime):
            value = value.strftime('%Y:%m:%d %H:%M:%S').encode(self.exif_encoding)
        # MMAL_PARAMETER_EXIF_T is a variable sized structure, hence all the
        # mucking about with string buffers here...
        buf = ct.create_string_buffer(
            ct.sizeof(mmal.MMAL_PARAMETER_EXIF_T) + len(tag) + len(value) + 1)
        mp = ct.cast(buf, ct.POINTER(mmal.MMAL_PARAMETER_EXIF_T))
        mp[0].hdr.id = mmal.MMAL_PARAMETER_EXIF
        mp[0].hdr.size = len(buf)
        if (b'=' in tag or b'\x00' in value):
            data = tag + value
            mp[0].keylen = len(tag)
            mp[0].value_offset = len(tag)
            mp[0].valuelen = len(value)
        else:
            data = tag + b'=' + value
        ct.memmove(mp[0].data, data, len(data))
        self.output_port.params[mmal.MMAL_PARAMETER_EXIF] = mp[0]

    def start(self, output):
        timestamp = datetime.datetime.now()
        timestamp_tags = (
            'EXIF.DateTimeDigitized',
            'EXIF.DateTimeOriginal',
            'IFD0.DateTime')
        # Timestamp tags are always included with the value calculated
        # above, but the user may choose to override the value in the
        # exif_tags mapping
        for tag in timestamp_tags:
            self._add_exif_tag(tag, self.exif_tags.get(tag, timestamp))
        # All other tags are just copied in verbatim
        for tag, value in self.exif_tags.items():
            if not tag in timestamp_tags:
                self._add_exif_tag(tag, value)
        super(PiCookedOneImageEncoder, self).start(output)


class PiCookedMultiImageEncoder(PiMultiImageEncoder):
    """

    """
    pass


class PiRawImageMixin(PiRawMixin, PiImageEncoder):
    """

    """

    def __init__(
            self, parent, camera_port, input_port, format, resize, **options):
        super(PiRawImageMixin, self).__init__(
                parent, camera_port, input_port, format, resize, **options)
        self._image_size = 0

    def _callback_write(self, buf, key=PiVideoFrameType.frame):
        """

        """
        if self._image_size > 0:
            super(PiRawImageMixin, self)._callback_write(buf, key)
            self._image_size -= buf.length
        return self._image_size <= 0

    def start(self, output):
        self._image_size = self._frame_size
        super(PiRawImageMixin, self).start(output)


class PiRawOneImageEncoder(PiOneImageEncoder, PiRawImageMixin):
    """

    """
    pass


class PiRawMultiImageEncoder(PiMultiImageEncoder, PiRawImageMixin):
    """

    """
    def _next_output(self, key=PiVideoFrameType.frame):
        super(PiRawMultiImageEncoder, self)._next_output(key)
        self._image_size = self._frame_size

