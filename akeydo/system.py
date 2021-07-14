class _System:
    def __init__(self) -> None:
        self._values = {}

    def set(self, path: str, value, parse=None):
        with open(path) as file:
            contents = path.read()
        self._values[path] = parse(contents) if parse else contents
        with open(path, "w") as file:
            file.write(f"{value}")
        return self._values[path]

    def reset(self, path: str):
        with open(path, "w") as file:
            file.write(f"{self._values[path]}")


system = _System()
