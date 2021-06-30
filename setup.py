#!/usr/bin/env python
"""Install akeydo."""

from setuptools import setup
from setuptools import find_packages


with open("README.md") as readme_fp:
    readme = readme_fp.read()

setup(
    name="akeydo",
    use_scm_version=True,
    description="A library for rapidly creating command-line tools.",
    long_description=readme,
    author="Melissa Nuno",
    author_email="melissa@contains.io",
    url="https://github.com/dangle/akeydo",
    keywords=[
        "vfio",
        "kvm",
        "keyboard",
        "video",
        "mouse",
        "monitor",
        "passthrough",
        "toggle",
        "vm",
        "virtual",
        "machine",
        "qemu",
        "libvirt",
        "akeydo",
    ],
    license="MIT",
    packages=find_packages(exclude=["tests", "docs"]),
    install_requires=["importlib_metadata", "dbus_next", "pyyaml"],
    setup_requires=["packaging", "appdirs", "pytest-runner", "setuptools_scm"],
    tests_require=["pytest >= 6.2"],
    entry_points="""
      [console_scripts]
      akeydo = akeydo.__main__:main
      [akeydo.plugins]
      devices = akeydo.plugins.devices
      gpu = akeydo.plugins.gpu
      cpu = akeydo.plugins.cpu
      memory = akeydo.plugins.memory
    """,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Intended Audience :: Developers",
        "Topic :: Utilities",
    ],
)
