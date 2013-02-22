<p align="center" style="padding: 20px">
<img src="https://raw.github.com/ContinuumIO/blaze-core/master/docs/source/svg/blaze_med.png">
</p>

**Blaze** is the next-generation of NumPy. It is designed as a
foundational set of abstractions on which to build out-of-core and
distributed algorithms over a wide variety of data sources and to extend
the structure of NumPy itself.

<p align="center" style="padding: 20px">
<img src="https://raw.github.com/ContinuumIO/blaze-core/master/docs/source/svg/numpy_plus.png">
</p>

Our goal is to allow easy composition of low level computation kernels
( C, Fortran, Numba ) to form complex data transformations on large
datasets.

In Blaze computations are described in a high-level language ( Python
) but executed on a low-level runtime outside of Python. Allowing the
easy mapping of high-level expertise to data while not sacrificing
low-level performance. Blaze aims to bring Python and NumPy into the
massively-multicore arena, allowing it to able to leverage many CPU and
GPU cores across computers, virtual machines and cloud services.

<p align="center" style="padding: 20px">
<img src="https://raw.github.com/ContinuumIO/blaze-core/master/docs/source/svg/codepush.png">
</p>

Continuum Analytics' vision is to provide open technologies for data
integration on a massive scale based on a vision of a structured,
universal "data web". In the same way that URL, HTML, and HTTP form
the basis of the World Wide Web for documents, their technologies will
be the fabric for structured and numerical data and will spearhead
innovations in data management, analytics, and distributed computation.

Blaze aims to be a "glue project" allowing many different users of
other PyData projects ( Pandas, Theano, Numba, SciPy, Scikit-Learn)
to interoperate at the appication level and at the library level with
the goal of being able to to lift their existing functionality into a
distributed context.

<p align="center" style="padding: 20px">
<img src="https://raw.github.com/ContinuumIO/blaze-core/master/docs/source/svg/sources.png">
</p>

Status
------

Blaze is a work in progress at the moment. The code is quite a distance
from feature complete. The code is released in an effort to start a
public discussion with our end users and community.

Documentation
-------------

* [0.1 Dev Docs](http://blaze.pydata.org/docs/)

Installing
----------

If you are interested in the development version of Blaze you can
obtain the source from Github.

```bash
$ git clone git@github.com:ContinuumIO/blaze-core.git
```

Many of the dependencies ( llvm, numba, ... ) are non-trivial to
install. It is **highly recommend** that you build Blaze using the Anaconda
Python distribution.

Free Anaconda CE is available here: http://continuum.io/anacondace.html .

Using Anaconda's package manager:

```bash
$ conda install ply
```

Introduction
------------

To build project inside of Anaconda:

```bash
$ make build
```

To build documentation:

```bash
$ make docs
```

To run tests:

```bash
>>> python
>>> from blaze.testing import runner
>>> runner()
```

Alternative Installation
------------------------

If you desire not to use Anaconda it is possible to build Blaze using
standard Python tools. This method is not recommended.

1) After you have checked out the Blaze source, create a virtualenv
under the root of the Blaze repo.

```bash
$ virtualenv venv --distribute --no-site-packages 
$ . venv/bin/activate
```

2) Pull the Conda package manager for use inside of your virtualenv.

```bash
git clone git@github.com:ContinuumIO/conda.git
```

3) Build and install conda.

```bash
cd conda
python setup.sh install
cd ..
```

4) Create a directory in your virtualenv to mimic the behavior of
Anaconda and allow Continuum signed packages to be installed.

```bash
mkdir venv/pkgs
```

5) Add ``conda`` to your path.

```bash
$ PATH=venv/bin:$PATH
```

6) Use Anaconda to resolve Blaze dependencies.

```bash
conda install ply
conda install numpy
conda install cython
```

7) From inside the Blaze directory run the Makefile.

```bash
make build
```

Contributing
------------

Anyone wishing to discuss on Blaze should join the
[blaze-dev](https://groups.google.com/a/continuum.io/forum/#!forum/blaze
-dev) mailing list at: blaze-dev@continuum.io

License
-------

Blaze development is sponsored by Continuum Analytics.

Released under BSD license. See LICENSE for details.
