#!/usr/bin/env python

import os
import sys

if sys.version_info < (3, 10):
    raise RuntimeError("This package requres Python 3.10+")

VERSION = "0.7.0"

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

    
if sys.argv[-1] == "publish":
    os.system("python3 setup.py sdist upload")
    sys.exit()

setup(
    version=VERSION,
    download_url="https://github.com/rsnodgrass/pymonoprice/archive/{}.tar.gz".format(VERSION)
)
