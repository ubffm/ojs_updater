# -*- coding: utf-8 -*-
"""Setup.py"""
import setuptools
setuptools.setup(name='ojs_updater',
      version='0.1.0',
      description='Simple script to update multiple ojs instances on the same system.',
      url='https://github.com/ubffm/ojs_updater',
      author='UB Frankfurt a. M.',
      author_email='ublabs@ub.uni-frankfurt.de',
      license='MPL 2.0',
      packages=setuptools.find_packages(),
      entry_points={
          'console_scripts': ['ojs_updater=ojs_updater.ojs_update:main']
      },
      platforms=["linux"],
      classifiers=[
          "Development Status :: 4 - Beta",
          "Environment :: Console",
          "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
          "Operating System :: POSIX :: Linux"
      ],
      install_requires=[
        'packaging==21.0',
        'PyYAML==5.4.1',
        'zc.lockfile==2.0',
        'schema==0.7.4'
      ]
)
