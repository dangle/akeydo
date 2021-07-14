class _System:
    def __init__(self) -> None:
        self._values = {}

    def read(self, path: str, parse=None) -> str:
        with open(path) as file:
            contents = file.read()
        return parse(contents) if parse else contents

    def write(self, path: str, value) -> None:
        with open(path, "w") as file:
            file.write(f"{value}")

    def set(self, path: str, value, parse=None):
        self._values[path] = self.get(path, parse)
        self.write(path, value)
        return self._values[path]

    def reset(self, path: str):
        with open(path, "w") as file:
            file.write(f"{self._values[path]}")


system = _System()
