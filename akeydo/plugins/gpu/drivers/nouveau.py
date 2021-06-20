import logging

from .base import BaseDriver


class Driver(BaseDriver):
    def bind_framebuffer(self):
        logging.debug("nouveau driver does not rebind the framebuffer")

    def unbind_framebuffer(self):
        logging.debug("nouveau driver does not unbind the framebuffer")
