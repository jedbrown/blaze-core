import os
from tables import openFile, NoSuchNodeError
from ndtable.sources.canonical import Source
from ndtable.datashape.recordclass import from_pytables
from ndtable.datashape import Fixed

class HDF5Source(Source):

    expectedrows = 10000
    compress = 'zlib'

    def __init__(self, shape, path, title=None):
        self.title = title
        self.path  = path
        self.shape = from_pytables(shape)
        self._shape = shape
        self.root, self.table = os.path.split(path)
        self.fd = None

        # TODO: lazy
        self.__alloc__()

    def calculate(self, ntype):
        # Substitue actual values in infered from the metadata
        x = self.shape * Fixed(self.fd.nrows)
        return x

    def get_or_create(self, node):
        try:
            return self.h5file.getNode('/' + self.table)
        except NoSuchNodeError:
            return self.h5file.createTable(
                '/',
                self.table,
                self._shape,
                title='',
            )

    def __alloc__(self):
        self.h5file = openFile(self.root, title=self.title, mode='a')
        self.fd = self.get_or_create(self.root)

    def __dealloc__(self):
        self.h5file.close()

    def __repr__(self):
        return "HDF5('%s')" % self.path