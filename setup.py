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
    url='http://github.com/mgedmin/project-summary/',
    description='Script to generate a summary page for all my projects',
    long_description=long_description,
    classifiers=[
        'Development Status :: 4 - Beta',
##      'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Private :: Do Not Upload To PyPI', # it rejects unknown classifiers ;)
    ],
    license='GPL',

    py_modules=['summary'],
    zip_safe=False,
    install_requires=['arrow'],
    entry_points={
        'console_scripts': [
            'summary = summary:main',
        ],
    },
)
