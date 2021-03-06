import threading

from tornado.gen import coroutine, Future, Return
from tornado.ioloop import IOLoop
from PIL import Image
from sys import exc_info
from io import BytesIO


class ImageResizer(object):
    def __init__(self, log, pool, io_loop=None):
        if io_loop is None:
            io_loop = IOLoop.current()
        self._log = log
        self._io_loop = io_loop
        self._pool = pool

    @coroutine
    def resize(self, avatar, width, height):
        log = self._log.getChild('avatar[%d]' % avatar.avatar_id)
        log.audit('Resizing to bounding box %sx%s', width, height)
        future = Future()

        if (width is None) and (height is None):
            raise ValueError('width and height cannot both be None')

        # Handing the value back to the coroutine
        def _on_done(result):
            if isinstance(result, tuple):
                log.audit('Passing back exception')
                future.set_exc_info(result)
            else:
                log.audit('Passing back result')
                future.set_result(result)

        # What to do in the thread pool
        def _do_resize(image_data, image_format, width, height):
            try:
                log.audit('Opening image, format %s', image_format)
                image = Image.open(BytesIO(image_data))

                # Get the aspect ratio
                raw_width, raw_height = image.size
                ratio = float(raw_width) / float(raw_height)
                log.audit('Raw size: %dx%d, ratio %f',
                        raw_width, raw_height, ratio)

                if (ratio >= 1.0) or (height is None):
                    # Fit to width
                    height = int(width / ratio)
                else:
                    # Fit to height
                    width = int(height * ratio)

                # Scale
                log.audit('Scaling to %dx%d', width, height)
                image = image.resize((width, height), Image.LANCZOS)

                # Write out result
                if image_format == 'image/jpeg':
                    pil_format = 'JPEG'
                else:
                    pil_format = 'PNG'

                out_buffer = BytesIO()
                log.audit('Saving output as %s', pil_format)
                image.save(out_buffer, pil_format)
                self._io_loop.add_callback(_on_done, out_buffer.getvalue())
            except:
                log.exception('Failed to resize')
                self._io_loop.add_callback(_on_done, exc_info())

        # Run the above in the thread pool:
        yield self._pool.apply(_do_resize, (avatar.avatar,
                avatar.avatar_type, width, height))

        # Wait for the result
        resized_data = yield future

        # Return the data
        raise Return(resized_data)
