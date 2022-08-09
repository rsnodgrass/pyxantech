#!/usr/bin/env python

import os
import sys
if sys.version_info < (3, 10):
    raise RuntimeError("This package requres Python 3.10+")

VERSION = '0.6.8'

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

license = """
MIT License
Copyright (c) 2017 Egor Tsinko
Copyright (c) 2020 Ryan Snodgrass
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

setup(name='pyxantech',
      python_requires = ">=3.10",
      version=VERSION,
      description='Python RS232 API for Monoprice/Xantech/Dayton Audio multi-zone amps',
      url='https://github.com/rsnodgrass/pymonoprice',
      download_url='https://github.com/rsnodgrass/pymonoprice/archive/{}.tar.gz'.format(VERSION),
      author='Egor Tsinko',
      author_email='etsinko@gmail.com',
      license='MIT',
      install_requires=['pyserial>=3.5','pyserial-asyncio>=0.5','ratelimit>=2.2.1'],
      packages=['pyxantech'],
      classifiers=['Development Status :: 4 - Beta',
                   'License :: OSI Approved :: MIT License',
                   'Programming Language :: Python :: 3.10' ],
      include_package_data=True,
      zip_safe=True)
