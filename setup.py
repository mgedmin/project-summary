#!/usr/bin/env python
import os

from setuptools import setup


here = os.path.dirname(__file__)
with open(os.path.join(here, 'README.rst')) as f:
    long_description = f.read()

version = None
with open(os.path.join(here, 'summary.py')) as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.partition('=')[-1].strip(' \'"\n')

setup(
    name='project-summary',
    version=version,
    author='Marius Gedminas',
    author_email='marius@gedmin.as',
    url='https://github.com/mgedmin/project-summary/',
    description='Script to generate a summary page for all my projects',
    long_description=long_description,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Private :: Do Not Upload To PyPI',  # it rejects unknown classifiers ;)
    ],
    python_requires='>= 3.7',
    license='GPL v2 or v3',

    py_modules=['summary'],
    zip_safe=False,
    install_requires=[
        'arrow',
        'mako',
        'markupsafe',
        'pypistats >= 0.13',
        'requests',
        'requests-cache >= 0.8, < 1.0',
    ],
    entry_points={
        'console_scripts': [
            'summary = summary:main',
        ],
    },
)
