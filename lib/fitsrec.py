import warnings

import numpy as np
from numpy import char as chararray

from pyfits import rec
from pyfits.column import ASCIITNULL, Column, ColDefs, FITS2NUMPY, _FormatX, \
                          _FormatP, _VLF, _get_index, _wrapx, _unwrapx, \
                          _convert_format, _convert_ascii_format
from pyfits.util import _fromfile


class FITS_record(object):
    """
    FITS record class.

    `FITS_record` is used to access records of the `FITS_rec` object.
    This will allow us to deal with scaled columns.  The `FITS_record`
    class expects a `FITS_rec` object as input.
    """

    def __init__(self, input, row=0, startColumn=0, endColumn=0):
        """
        Parameters
        ----------
        input : array
           The array to wrap.

        row : int, optional
           The starting logical row of the array.

        startColumn : int, optional
           The starting column in the row associated with this object.
           Used for subsetting the columns of the FITS_rec object.

        endColumn : int, optional
           The ending column in the row associated with this object.
           Used for subsetting the columns of the FITS_rec object.
        """

        self.array = input
        self.row = row
        len = self.array._nfields

        if startColumn > len:
            self.start = len + 1
        else:
            self.start = startColumn

        if endColumn <= 0 or endColumn > len:
            self.end = len
        else:
            self.end = endColumn

    def field(self, fieldName):
        """
        Get the field data of the record.
        """

        return self.__getitem__(fieldName)


    def setfield(self, fieldName, value):
        """
        Set the field data of the record.
        """

        self.__setitem__(fieldName, value)

    def __str__(self):
        """
        Print one row.
        """

        outlist = []
        for idx in range(self.array._nfields):
            if idx >= self.start and idx < self.end:
                outlist.append(repr(self.array.field(idx)[self.row]))
        return '(%s)' % ', '.join(outlist)

    def __repr__(self):
        return self.__str__()

    def __getitem__(self,key):
        if isinstance(key, (str, unicode)):
            indx = _get_index(self.array._coldefs.names, key)

            if indx < self.start or indx > self.end - 1:
                raise KeyError("Key '%s' does not exist." % key)
        else:
            indx = key + self.start

            if indx > self.end - 1:
                raise IndexError('Index out of bounds')

        return self.array.field(indx)[self.row]

    def __setitem__(self,fieldname, value):
        if isinstance(fieldname, basestring):
            indx = _get_index(self.array._coldefs.names, fieldname)

            if indx < self.start or indx > self.end - 1:
                raise KeyError("Key '%s' does not exist." % fieldname)
        else:
            indx = fieldname + self.start

            if indx > self.end - 1:
                raise IndexError('Index out of bounds')

        self.array.field(indx)[self.row] = value

    def __len__(self):
        return min(self.end - self.start, self.array._nfields)

    def __getslice__(self, i, j):
        return FITS_record(self.array, self.row, i, j)


class FITS_rec(rec.recarray):
    """
    FITS record array class.

    `FITS_rec` is the data part of a table HDU's data part.  This is a
    layer over the `recarray`, so we can deal with scaled columns.

    It inherits all of the standard methods from `numpy.ndarray`.
    """

    def __new__(subtype, input):
        """
        Construct a FITS record array from a recarray.
        """

        # input should be a record array
        if input.dtype.subdtype is None:
            self = rec.recarray.__new__(subtype, input.shape, input.dtype,
                                        buf=input.data,
                                        heapoffset=input._heapoffset,
                                        file=input._file)
        else:
            self = rec.recarray.__new__(subtype, input.shape, input.dtype,
                                        buf=input.data, strides=input.strides,
                                        heapoffset=input._heapoffset,
                                        file=input._file)

        self._nfields = len(self.dtype.names)
        self._convert = [None] * len(self.dtype.names)
        self._coldefs = None
        self._gap = 0
        self.names = self.dtype.names
        # This attribute added for backward compatibility with numarray
        # version of FITS_rec
        self._names = self.dtype.names
        self.formats = None
        return self

    def __array_finalize__(self, obj):
        if obj is None:
            return

        if type(obj) == FITS_rec:
            self._convert = obj._convert
            self._coldefs = obj._coldefs
            self._nfields = obj._nfields
            self.names = obj.names
            self._names = obj._names
            self._gap = obj._gap
            self.formats = obj.formats
        else:
            # This will allow regular ndarrays with fields, rather than
            # just other FITS_rec objects
            self._nfields = len(obj.dtype.names)
            self._convert = [None] * len(obj.dtype.names)

            self._heapoffset = getattr(obj, '_heapoffset', 0)
            self._file = getattr(obj, '_file', None)

            self._coldefs = None
            self._gap = 0
            self.names = obj.dtype.names
            self._names = obj.dtype.names
            self.formats = None

            attrs = ['_convert', '_coldefs', 'names', '_names', '_gap',
                     'formats']
            for attr in attrs:
                if hasattr(obj, attr):
                    value = getattr(obj, attr, None)
                    if value is None:
                        warnings.warn('Setting attribute %s as None' % attr)
                    setattr(self, attr, value)

            if self._coldefs is None:
                # The data does not have a _coldefs attribute so
                # create one from the underlying recarray.
                columns = []
                formats = []

                for idx in range(len(obj.dtype.names)):
                    cname = obj.dtype.names[idx]

                    format = _convert_format(obj.dtype[idx], reverse=True)

                    formats.append(format)

                    c = Column(name=cname, format=format)
                    columns.append(c)

                tbtype = 'BinTableHDU'
                try:
                    if self._extension == 'TABLE':
                        tbtype = 'TableHDU'
                except AttributeError:
                    pass

                self.formats = formats
                self._coldefs = ColDefs(columns, tbtype=tbtype)


    def _clone(self, shape):
        """
        Overload this to make mask array indexing work properly.
        """

        from pyfits.hdu.table import new_table

        hdu = new_table(self._coldefs, nrows=shape[0])
        return hdu.data

    def __repr__(self):
        return rec.recarray.__repr__(self)

    def __getslice__(self, i, j):
        key = slice(i, j)
        return self.__getitem__(key)

    def __getitem__(self, key):
        if isinstance(key, basestring):
            return self.field(key)
        elif isinstance(key, (slice, np.ndarray)):
            out = rec.recarray.__getitem__(self, key)
            out._coldefs = ColDefs(self._coldefs)
            arrays = []
            out._convert = [None] * len(self.dtype.names)
            for idx in range(len(self.dtype.names)):
                #
                # Store the new arrays for the _coldefs object
                #
                arrays.append( self._coldefs._arrays[idx][key])

                # touch all fields to expand the original ._convert list
                # so the sliced FITS_rec will view the same scaled columns as
                # the original
                dummy = self.field(idx)
                if self._convert[idx] is not None:
                    out._convert[idx] = \
                        np.ndarray.__getitem__(self._convert[idx], key)
            del dummy

            out._coldefs._arrays = arrays
            out._coldefs._shape = len(arrays[0])

            return out

        # if not a slice, do this because Record has no __getstate__.
        # also more efficient.
        else:
            if isinstance(key, int) and key >= len(self):
                raise IndexError("Index out of bounds")

            newrecord = FITS_record(self,key)
            return newrecord

    def __setitem__(self, row, value):
        if isinstance(value, FITS_record):
            for idx in range(self._nfields):
                self.field(self.names[idx])[row] = value.field(self.names[idx])
        elif isinstance(value, (tuple, list)):
            if self._nfields == len(value):
                for idx in range (self._nfields):
                    self.field(idx)[row] = value[idx]
            else:
               raise ValueError('Input tuple or list required to have %s '
                                'elements.' % self._nfields)
        else:
            raise TypeError('Assignment requires a FITS_record, tuple, or '
                            'list as input.')

    def __setslice__(self, start, end, value):
        _end = min(len(self), end)
        _end = max(0, _end)
        _start = max(0,start)
        _end = min(_end, _start + len(value))

        for idx in range(_start, _end):
            self.__setitem__(idx, value[idx - _start])

    def _get_scale_factors(self, indx):
        """
        Get the scaling flags and factors for one field.

        `indx` is the index of the field.
        """

        if self._coldefs._tbtype == 'BinTableHDU':
            _str = 'a' in self._coldefs.formats[indx]
            _bool = self._coldefs._recformats[indx][-2:] == FITS2NUMPY['L']
        else:
            _str = self._coldefs.formats[indx][0] == 'A'
            _bool = 0             # there is no boolean in ASCII table
        _number = not(_bool or _str)
        bscale = self._coldefs.bscales[indx]
        bzero = self._coldefs.bzeros[indx]
        _scale = bscale not in ['', None, 1]
        _zero = bzero not in ['', None, 0]
        # ensure bscale/bzero are numbers
        if not _scale:
            bscale = 1
        if not _zero:
            bzero = 0

        return (_str, _bool, _number, _scale, _zero, bscale, bzero)

    def field(self, key):
        """
        A view of a `Column`'s data as an array.
        """

        indx = _get_index(self._coldefs.names, key)

        if (self._convert[indx] is None):
            # for X format
            if isinstance(self._coldefs._recformats[indx], _FormatX):
                _nx = self._coldefs._recformats[indx]._nx
                dummy = np.zeros(self.shape+(_nx,), dtype=np.bool_)
                _unwrapx(rec.recarray.field(self,indx), dummy, _nx)
                self._convert[indx] = dummy
                return self._convert[indx]

            (_str, _bool, _number, _scale, _zero, bscale, bzero) = \
                self._get_scale_factors(indx)

            # for P format
            if isinstance(self._coldefs._recformats[indx], _FormatP):
                dummy = _VLF([None] * len(self))
                dummy._dtype = self._coldefs._recformats[indx]._dtype
                for i in range(len(self)):
                    _offset = \
                        rec.recarray.field(self,indx)[i,1] + self._heapoffset
                    self._file.seek(_offset)
                    if self._coldefs._recformats[indx]._dtype is 'a':
                        count = rec.recarray.field(self,indx)[i,0]
                        dt = self._coldefs._recformats[indx]._dtype + str(1)
                        da = _fromfile(self._file, dtype=dt, count=count,
                                       sep="")
                        dummy[i] = chararray.array(da, itemsize=count)
                    else:
#                       print type(self._file)
#                       print "type =",self._coldefs._recformats[indx]._dtype
                        count = rec.recarray.field(self,indx)[i,0]
                        dt = self._coldefs._recformats[indx]._dtype
                        dummy[i] = _fromfile(self._file, dtype=dt, count=count,
                                             sep="")
                        dummy[i].dtype = dummy[i].dtype.newbyteorder('>')

                # scale by TSCAL and TZERO
                if _scale or _zero:
                    for i in range(len(self)):
                        dummy[i][:] = dummy[i]*bscale+bzero

                # Boolean (logical) column
                if self._coldefs._recformats[indx]._dtype is FITS2NUMPY['L']:
                    for i in range(len(self)):
                        dummy[i] = np.equal(dummy[i], ord('T'))

                self._convert[indx] = dummy
                return self._convert[indx]

            if _str:
                return rec.recarray.field(self, indx)

            # ASCII table, convert strings to numbers
            if self._coldefs._tbtype == 'TableHDU':
                _fmap = {'I': np.int32, 'F': np.float32, 'E': np.float32,
                         'D': np.float64}
                _type = _fmap[self._coldefs._Formats[indx][0]]

                # if the string = TNULL, return ASCIITNULL
                nullval = self._coldefs.nulls[indx].strip()
                dummy = rec.recarray.field(self,indx).replace('D', 'E')
                dummy = np.where(dummy.strip() == nullval, str(ASCIITNULL),
                                 dummy)
                dummy = np.array(dummy, dtype=_type)

                self._convert[indx] = dummy
            else:
                dummy = rec.recarray.field(self, indx)

            # further conversion for both ASCII and binary tables
            if _number and (_scale or _zero):

                # only do the scaling the first time and store it in _convert
                self._convert[indx] = np.array(dummy, dtype=np.float64)
                if _scale:
                    np.multiply(self._convert[indx], bscale,
                                self._convert[indx])
                if _zero:
                    self._convert[indx] += bzero
            elif _bool:
                self._convert[indx] = np.equal(dummy, ord('T'))
            else:
                return dummy

        return self._convert[indx]

    def _scale_back(self):
        """
        Update the parent array, using the (latest) scaled array.
        """

        _fmap = {'A': 's', 'I': 'd', 'F': 'f', 'E': 'E', 'D': 'E'}
        # calculate the starting point and width of each field for ASCII table
        if self._coldefs._tbtype == 'TableHDU':
            _loc = self._coldefs.starts
            _width = []
            for i in range(len(self.dtype.names)):
                f = _convert_ascii_format(self._coldefs._Formats[i])
                _width.append(f[1])
            _loc.append(_loc[-1]+rec.recarray.field(self,i).itemsize)

        self._heapsize = 0
        for indx in range(len(self.dtype.names)):
            if (self._convert[indx] is not None):
                if isinstance(self._coldefs._recformats[indx], _FormatX):
                    _wrapx(self._convert[indx], rec.recarray.field(self,indx),
                           self._coldefs._recformats[indx]._nx)
                    continue

                (_str, _bool, _number, _scale, _zero, bscale, bzero) = \
                    self._get_scale_factors(indx)

                # add the location offset of the heap area for each
                # variable length column
                if isinstance(self._coldefs._recformats[indx], _FormatP):
                    desc = rec.recarray.field(self,indx)
                    desc[:] = 0 # reset
                    _npts = map(len, self._convert[indx])
                    desc[:len(_npts),0] = _npts
                    dt = self._coldefs._recformats[indx]._dtype
                    _dtype = np.array([], dtype=dt)
                    desc[1:,1] = np.add.accumulate(desc[:-1,0])*_dtype.itemsize

                    desc[:,1][:] += self._heapsize
                    self._heapsize += desc[:,0].sum()*_dtype.itemsize

                # conversion for both ASCII and binary tables
                if _number or _str:
                    if _number and (_scale or _zero):
                        dummy = self._convert[indx].copy()
                        if _zero:
                            dummy -= bzero
                        if _scale:
                            dummy /= bscale
                    elif self._coldefs._tbtype == 'TableHDU':
                        dummy = self._convert[indx]
                    else:
                        continue

                    # ASCII table, convert numbers to strings
                    if self._coldefs._tbtype == 'TableHDU':
                        _format = self._coldefs._Formats[indx].strip()
                        _lead = self._coldefs.starts[indx] - _loc[indx]
                        if _lead < 0:
                            raise ValueError(
                                'Column `%s` starting point overlaps to the '
                                'previous column.' % indx + 1)
                        _trail = _loc[indx+1] - _width[indx] - \
                                 self._coldefs.starts[indx]
                        if _trail < 0:
                            raise ValueError(
                                'Column `%s` ending point overlaps to the '
                                'next column.' % indx + 1)
                        if 'A' in _format:
                            _pc = '%-'
                        else:
                            _pc = '%'
                        _fmt = ' '*_lead + _pc + _format[1:] + \
                               _fmap[_format[0]] + ' '*_trail

                        # not using numarray.strings's num2char because the
                        # result is not allowed to expand (as C/Python does).
                        for i in range(len(dummy)):
                            x = _fmt % dummy[i]
                            if len(x) > (_loc[indx+1]-_loc[indx]):
                                raise ValueError(
                                    "Number `%s` does not fit into the "
                                    "output's itemsize of %s."
                                    % (x, _width[indx]))
                            else:
                                rec.recarray.field(self, indx)[i] = x
                        if 'D' in _format:
                            rec.recarray.field(self,indx).replace('E', 'D')


                    # binary table
                    else:
                        if isinstance(rec.recarray.field(self,indx)[0],
                                      np.integer):
                            dummy = np.around(dummy)
                        f = rec.recarray.field(self, indx)
                        f[:] = dummy.astype(f.dtype)

                    del dummy

                # ASCII table does not have Boolean type
                elif _bool:
                    rec.recarray.field(self,indx)[:] = \
                        np.choose(self._convert[indx],
                                  (np.array([ord('F')], dtype=np.int8)[0],
                                  np.array([ord('T')],dtype=np.int8)[0]))
