from setuptools import setup, find_packages

setup(name='pysambar',
    version='0.1',
    description='Python implementation of SAMBAR',
    url='https://github.com/genisott/sambar',
    author='Genís Calderer',
    author_email='genis.calderer@gmail.com',
    license='MIT',
    packages=['sambar'],
    install_requires=['pandas',
    'numpy',
    'networkx',
    'matplotlib',
    'scipy'
    ],
    zip_safe=False)