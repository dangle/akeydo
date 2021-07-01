import logging
import os
import time


class BaseDriver:
    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def bind_vtcons(self) -> None:
        logging.debug("Binding vtconsoles")
        for filename in reversed(os.listdir("/sys/class/vtconsole/")):
            logging.debug("Binding %s", filename)
            with open(f"/sys/class/vtconsole/{filename}/bind", "w") as file:
                file.write("1")

    def unbind_vtcons(self) -> None:
        logging.debug("Unbinding vtconsoles")
        for filename in os.listdir("/sys/class/vtconsole/"):
            logging.debug("Unbinding %s", filename)
            with open(f"/sys/class/vtconsole/{filename}/bind", "w") as file:
                file.write("0")

    def bind_framebuffer(self) -> None:
        logging.debug("Enabling the framebuffer")
        if os.path.isfile("/sys/bus/platform/drivers/efi-framebuffer/bind"):
            with open("/sys/bus/platform/drivers/efi-framebuffer/bind", "w") as file:
                file.write("efi-framebuffer.0")
        else:
            logging.debug("Unable to enable the framebuffer")

    def unbind_framebuffer(self) -> None:
        logging.debug("Disabling the framebuffer")
        if os.path.isfile("/sys/bus/platform/drivers/efi-framebuffer/unbind"):
            with open("/sys/bus/platform/drivers/efi-framebuffer/unbind", "w") as file:
                file.write("efi-framebuffer.0")
            time.sleep(5)
        else:
            logging.debug("Unable to disable the framebuffer")
