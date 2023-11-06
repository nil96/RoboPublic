
from __future__ import (
    unicode_literals,
    print_function,
    division,
    absolute_import,
    )

# Make Py2's str equivalent to Py3's
str = type('')


import io
from threading import RLock
from collections import deque
from operator import attrgetter
from weakref import ref

from picamera.exc import PiCameraValueError
from picamera.frames import PiVideoFrame, PiVideoFrameType


class BufferIO(io.IOBase):
    """

    """
    __slots__ = ('_buf', '_pos', '_size')

    def __init__(self, obj):
        self._buf = memoryview(obj)
        if self._buf.ndim > 1 or self._buf.format != 'B':
            try:
                # Py2.7 doesn't have memoryview.cast
                self._buf = self._buf.cast('B')
            except AttributeError:
                raise ValueError(
                    'buffer object must be one-dimensional and have unsigned '
                    'byte format ("B")')
        self._pos = 0
        self._size = self._buf.shape[0]

    def close(self):
        super(BufferIO, self).close()
        try:
            self._buf.release()
        except AttributeError:
            # Py2.7 doesn't have memoryview.release
            pass

    def _check_open(self):
        if self.closed:
            raise ValueError('I/O operation on a closed stream')

    @property
    def size(self):
        """

        """
        return self._size

    def readable(self):
        """

        """
        self._check_open()
        return True

    def writable(self):
        """

        """
        self._check_open()
        return not self._buf.readonly

    def seekable(self):
        """

        :meth:`tell`.
        """
        self._check_open()
        return True

    def getvalue(self):
        """

        """
        with self.lock:
            return self._buf.tobytes()

    def tell(self):
        """
        """
        self._check_open()
        return self._pos

    def seek(self, offset, whence=io.SEEK_SET):
        """

        """
        self._check_open()
        if whence == io.SEEK_CUR:
            offset = self._pos + offset
        elif whence == io.SEEK_END:
            offset = self.size + offset
        if offset < 0:
            raise ValueError(
                'New position is before the start of the stream')
        self._pos = offset
        return self._pos

    def read(self, n=-1):
        """

        """
        self._check_open()
        if n < 0:
            return self.readall()
        elif n == 0:
            return b''
        else:
            result = self._buf[self._pos:self._pos + n].tobytes()
            self._pos += len(result)
            return result

    def readinto(self, b):
        """

        """
        self._check_open()
        result = max(0, min(len(b), self._size - self._pos))
        if result == 0:
            return 0
        else:
            b[:result] = self._buf[self._pos:self._pos + result]
            return result

    def readall(self):
        """

        """
        return self.read(max(0, self.size - self._pos))

    def truncate(self, size=None):
        """

        """
        raise NotImplementedError('cannot resize a BufferIO stream')

    def write(self, b):
        """

        """
        self._check_open()
        if self._buf.readonly:
            raise IOError('buffer object is not writeable')
        excess = max(0, len(b) - (self.size - self._pos))
        result = len(b) - excess
        if excess:
            self._buf[self._pos:self._pos + result] = b[:-excess]
        else:
            self._buf[self._pos:self._pos + result] = b
        self._pos += result
        return result


class CircularIO(io.IOBase):
    """

    """
    def __init__(self, size):
        if size < 1:
            raise ValueError('size must be a positive integer')
        self._lock = RLock()
        self._data = deque()
        self._size = size
        self._length = 0
        self._pos = 0
        self._pos_index = 0
        self._pos_offset = 0

    def _check_open(self):
        if self.closed:
            raise ValueError('I/O operation on a closed stream')

    @property
    def lock(self):
        """
        A re-entrant threading lock which is used to guard all operations.
        """
        return self._lock

    @property
    def size(self):
        """
        Return the maximum size of the buffer in bytes.
        """
        return self._size

    def readable(self):
        """
        Returns ``True``, indicating that the stream supports :meth:`read`.
        """
        self._check_open()
        return True

    def writable(self):
        """
        Returns ``True``, indicating that the stream supports :meth:`write`.
        """
        self._check_open()
        return True

    def seekable(self):
        """
        Returns ``True``, indicating the stream supports :meth:`seek` and
        :meth:`tell`.
        """
        self._check_open()
        return True

    def getvalue(self):
        """
        Return ``bytes`` containing the entire contents of the buffer.
        """
        with self.lock:
            return b''.join(self._data)

    def _set_pos(self, value):
        self._pos = value
        self._pos_index = -1
        self._pos_offset = chunk_pos = 0
        for self._pos_index, chunk in enumerate(self._data):
            if chunk_pos + len(chunk) > value:
                self._pos_offset = value - chunk_pos
                return
            else:
                chunk_pos += len(chunk)
        self._pos_index += 1
        self._pos_offset = value - chunk_pos

    def tell(self):
        """
        Return the current stream position.
        """
        self._check_open()
        with self.lock:
            return self._pos

    def seek(self, offset, whence=io.SEEK_SET):
        """
        """
        self._check_open()
        with self.lock:
            if whence == io.SEEK_CUR:
                offset = self._pos + offset
            elif whence == io.SEEK_END:
                offset = self._length + offset
            if offset < 0:
                raise ValueError(
                    'New position is before the start of the stream')
            self._set_pos(offset)
            return self._pos

    def read(self, n=-1):
        """

        """
        self._check_open()
        if n < 0:
            return self.readall()
        elif n == 0:
            return b''
        else:
            with self.lock:
                if self._pos >= self._length:
                    return b''
                from_index, from_offset = self._pos_index, self._pos_offset
                self._set_pos(self._pos + n)
                result = self._data[from_index][from_offset:from_offset + n]
                # Bah ... can't slice a deque
                for i in range(from_index + 1, self._pos_index):
                    result += self._data[i]
                if from_index < self._pos_index < len(self._data):
                    result += self._data[self._pos_index][:self._pos_offset]
                return result

    def readall(self):
        """

        """
        return self.read(max(0, self._length - self._pos))

    def read1(self, n=-1):
        """

        """
        self._check_open()
        with self.lock:
            if self._pos == self._length:
                return b''
            chunk = self._data[self._pos_index]
            if n == -1:
                n = len(chunk) - self._pos_offset
            result = chunk[self._pos_offset:self._pos_offset + n]
            self._pos += len(result)
            self._pos_offset += n
            if self._pos_offset >= len(chunk):
                self._pos_index += 1
                self._pos_offset = 0
            return result

    def truncate(self, size=None):
        """

        """
        self._check_open()
        with self.lock:
            if size is None:
                size = self._pos
            if size < 0:
                raise ValueError('size must be zero, or a positive integer')
            if size > self._length:
                # Backfill the space between stream end and current position
                # with NUL bytes
                fill = b'\x00' * (size - self._length)
                self._set_pos(self._length)
                self.write(fill)
            elif size < self._length:

                save_pos = self._pos
                self._set_pos(size)
                while self._pos_index < len(self._data) - 1:
                    self._data.pop()
                if self._pos_offset > 0:
                    self._data[self._pos_index] = self._data[self._pos_index][:self._pos_offset]
                    self._pos_index += 1
                    self._pos_offset = 0
                else:
                    self._data.pop()
                self._length = size
                if self._pos != save_pos:
                    self._set_pos(save_pos)

    def write(self, b):
        """
        Write the given bytes or bytearray object, *b*, to the underlying
        stream and return the number of bytes written.
        """
        self._check_open()
        b = bytes(b)
        with self.lock:

            if self._pos > self._length:
                self.truncate()
            result = len(b)
            if self._pos == self._length:

                self._data.append(b)
                self._length += len(b)
                self._pos = self._length
                self._pos_index = len(self._data)
                self._pos_offset = 0
            else:

                while b and (self._pos < self._length):
                    chunk = self._data[self._pos_index]
                    head = b[:len(chunk) - self._pos_offset]
                    assert head
                    b = b[len(head):]
                    self._data[self._pos_index] = b''.join((
                            chunk[:self._pos_offset],
                            head,
                            chunk[self._pos_offset + len(head):]
                            ))
                    self._pos += len(head)
                    if self._pos_offset + len(head) >= len(chunk):
                        self._pos_index += 1
                        self._pos_offset = 0
                    else:
                        self._pos_offset += len(head)
                if b:
                    self.write(b)
            # If the stream is now beyond the specified size limit, remove
            # whole chunks until the size is within the limit again
            while self._length > self._size:
                chunk = self._data.popleft()
                self._length -= len(chunk)
                self._pos -= len(chunk)
                self._pos_index -= 1
                # no need to adjust self._pos_offset
            return result


class PiCameraDequeHack(deque):
    def __init__(self, stream):
        super(PiCameraDequeHack, self).__init__()
        self.stream = ref(stream)  # avoid a circular ref

    def append(self, item):
        # Include the frame's metadata.
        frame = self.stream()._get_frame()
        return super(PiCameraDequeHack, self).append((item, frame))

    def pop(self):
        return super(PiCameraDequeHack, self).pop()[0]

    def popleft(self):
        return super(PiCameraDequeHack, self).popleft()[0]

    def __getitem__(self, index):
        return super(PiCameraDequeHack, self).__getitem__(index)[0]

    def __setitem__(self, index, value):
        frame = super(PiCameraDequeHack, self).__getitem__(index)[1]
        return super(PiCameraDequeHack, self).__setitem__(index, (value, frame))

    def __iter__(self):
        for item, frame in self.iter_both(False):
            yield item

    def __reversed__(self):
        for item, frame in self.iter_both(True):
            yield item

    def iter_both(self, reverse):
        if reverse:
            return super(PiCameraDequeHack, self).__reversed__()
        else:
            return super(PiCameraDequeHack, self).__iter__()


class PiCameraDequeFrames(object):
    def __init__(self, stream):
        super(PiCameraDequeFrames, self).__init__()
        self.stream = ref(stream)  # avoid a circular ref

    def __iter__(self):
        with self.stream().lock:
            pos = 0
            for item, frame in self.stream()._data.iter_both(False):
                pos += len(item)
                if frame:
                    # Rewrite the video_size and split_size attributes
                    # according to the current position of the chunk
                    frame = PiVideoFrame(
                        index=frame.index,
                        frame_type=frame.frame_type,
                        frame_size=frame.frame_size,
                        video_size=pos,
                        split_size=pos,
                        timestamp=frame.timestamp,
                        complete=frame.complete,
                    )
                    # Only yield the frame meta-data if the start of the frame
                    # still exists in the stream
                    if pos - frame.frame_size >= 0:
                        yield frame

    def __reversed__(self):
        with self.stream().lock:
            pos = self.stream()._length
            for item, frame in self.stream()._data.iter_both(True):
                if frame:
                    frame = PiVideoFrame(
                        index=frame.index,
                        frame_type=frame.frame_type,
                        frame_size=frame.frame_size,
                        video_size=pos,
                        split_size=pos,
                        timestamp=frame.timestamp,
                        complete=frame.complete,
                        )
                    if pos - frame.frame_size >= 0:
                        yield frame
                pos -= len(item)


class PiCameraCircularIO(CircularIO):
    """
    """
    def __init__(
            self, camera, size=None, seconds=None, bitrate=17000000,
            splitter_port=1):
        if size is None and seconds is None:
            raise PiCameraValueError('You must specify either size, or seconds')
        if size is not None and seconds is not None:
            raise PiCameraValueError('You cannot specify both size and seconds')
        if seconds is not None:
            size = bitrate * seconds // 8
        super(PiCameraCircularIO, self).__init__(size)
        try:
            camera._encoders
        except AttributeError:
            raise PiCameraValueError('camera must be a valid PiCamera object')
        self.camera = camera
        self.splitter_port = splitter_port
        self._data = PiCameraDequeHack(self)
        self._frames = PiCameraDequeFrames(self)

    def _get_frame(self):
        """
        """
        encoder = self.camera._encoders[self.splitter_port]
        return encoder.frame if encoder.frame.complete else None

    @property
    def frames(self):
        """
        """
        return self._frames

    def clear(self):
        """

        """
        with self.lock:
            self.seek(0)
            self.truncate()

    def _find(self, field, criteria, first_frame):
        first = last = None
        attr = attrgetter(field)
        for frame in reversed(self._frames):
            if last is None:
                last = frame
            if first_frame in (None, frame.frame_type):
                first = frame
            if last is not None and attr(last) - attr(frame) >= criteria:
                break
                if last is not None and attr(last) - attr(frame) >= criteria:
                    break
        return first, last

    def _find_all(self, first_frame):
        chunks = []
        first = last = None
        for frame in reversed(self._frames):
            last = frame
            break
        for frame in self._frames:
            if first_frame in (None, frame.frame_type):
                first = frame
                break
        return first, last

    def copy_to(
            self, output, size=None, seconds=None, frames=None,
            first_frame=PiVideoFrameType.sps_header):
        """

        """
        if (size, seconds, frames).count(None) < 2:
            raise PiCameraValueError(
                'You can only specify one of size, seconds, or frames')
        if isinstance(output, bytes):
            output = output.decode('utf-8')
        opened = isinstance(output, str)
        if opened:
            output = io.open(output, 'wb')
        try:
            with self.lock:
                if size is not None:
                    first, last = self._find('video_size', size, first_frame)
                elif seconds is not None:
                    seconds = int(seconds * 1000000)
                    first, last = self._find('timestamp', seconds, first_frame)
                elif frames is not None:
                    first, last = self._find('index', frames, first_frame)
                else:
                    first, last = self._find_all(first_frame)

                chunks = []
                if first is not None and last is not None:
                    pos = 0
                    for buf, frame in self._data.iter_both(False):
                        if pos > last.position + last.frame_size:
                            break
                        elif pos >= first.position:
                            chunks.append(buf)
                        pos += len(buf)
            for buf in chunks:
                output.write(buf)
            return first, last
        finally:
            if opened:
                output.close()
