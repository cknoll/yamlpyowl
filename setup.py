#!/usr/bin/env python
# -*- coding: utf-8 -*-


# the main purpose of this setup file is to enable local installation via `pip install -e .`


from setuptools import setup, find_packages

# This directory
from yamlpyowl import __version__

with open("requirements.txt") as requirements_file:
    requirements = requirements_file.read()

setup(
    name='yamlpyowl',
    version=__version__,
    author='Carsten Knoll',
    author_email='Carsten.Knoll@tu-dresden.de',
    packages=find_packages(),
    url='https://github.com/cknoll/...',
    license='GPLv3',
    description='...',
    long_description="""
    ...
    """,
    install_requires=requirements,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
    ],
)

