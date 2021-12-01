from abc import ABC, abstractmethod
import h5py
import os
import sys
import numpy as np
from warnings import warn
from collections.abc import MutableSequence
from tempfile import TemporaryFile
import logging

_loggers = {}
def _create_logger(name, log_file, level=logging.INFO):
    if name in _loggers.keys():
        return _loggers[name]
    handler = logging.FileHandler(log_file)
    handler.setFormatter(logging.Formatter('%(asctime)s | %(name)s | %(message)s'))
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    _loggers[name] = logger
    return logger

# Package-wide logger
_logger = _create_logger('pysnirf2', 'pysnirf2.log')
_logger.info('Opened pysnirf2.log')

if sys.version_info[0] < 3:
    raise ImportError('pysnirf2 requires Python > 3')

# -- methods to cast data prior to writing to and after reading from h5py interfaces------

_varlen_str_type = h5py.string_dtype(encoding='ascii', length=None)  # Length=None creates HDF5 variable length string
_DTYPE_FLOAT = 'f8'
_DTYPE_INT = 'i4'
_DTYPE_STR = 'S'  # Not sure how robust this is, but fixed length strings will always at least contain S


def _create_dataset(file, name, data):
    """
    Formats the input to satisfy the SNIRF specification as well as the HDF5 format. Determines appropriate write
    function from the type of data. The returned value should be passed to h5py.create_dataset() as kwarg "data" to be
    saved to an HDF5 file.

    Returns None if input is invalid and an h5py.Dataset instance if successful.

    Supported dtype str values: 'O', _DTYPE_FLOAT, _DTYPE_INT
    """
    try:
        if len(data) > 1:
            data = np.array(data)  # Cast to array
            dtype = data[0].dtype
            if any([dtype is t for t in [int, np.int32, np.int64]]):  # int
                return _create_dataset_int_array(file, name, data)
            elif any([dtype is t for t in [float, np.float, np.float64]]):  # float
                return _create_dataset_float_array(file, name, data)
            elif any([dtype is t for t in [str, np.string_]]):  # string
                return _create_dataset_string_array(file, name, data)
    except TypeError:  # data has no len()
        dtype = type(data)
    if any([dtype is t for t in [int, np.int32, np.int64]]):  # int
        return _create_dataset_int(file, name, data)
    elif any([dtype is t for t in [float, np.float, np.float64]]):  # float
        return _create_dataset_float(file, name, data)
    elif any([dtype is t for t in [str, np.string_]]):  # string
        return _create_dataset_string(file, name, data)
    raise TypeError('Unrecognized data type' + str(dtype)
                    + '. Please provide an int, float, or str, or an iterable of these.')


def _create_dataset_string(file: h5py.File, name: str, data: str):
    return file.create_dataset(name, dtype=_varlen_str_type, data=np.string_(data))


def _create_dataset_int(file: h5py.File, name: str, data: int):
    return file.create_dataset(name, dtype=_DTYPE_INT, data=int(data))


def _create_dataset_float(file: h5py.File, name: str, data: float):
    return file.create_dataset(name, dtype=_DTYPE_FLOAT, data=float(data))


def _create_dataset_string_array(file: h5py.File, name: str, data: np.ndarray):
    array = np.array(data).astype('O')
    if data.size is 0:
        array = AbsentDataset()  # Do not save empty or "None" NumPy arrays
    return file.create_dataset(name, dtype=_varlen_str_type, data=array)


def _create_dataset_int_array(file: h5py.File, name: str, data: np.ndarray):
    array = np.array(data).astype(int)
    if data.size is 0:
        array = AbsentDataset()
    return file.create_dataset(name, dtype=_DTYPE_INT, data=array)


def _create_dataset_float_array(file: h5py.File, name: str, data: np.ndarray):
    array = np.array(data).astype(float)
    if data.size is 0:
        array = AbsentDataset()
    return file.create_dataset(name, dtype=_DTYPE_FLOAT, data=array)


# -----------------------------------------


def _read_dataset(h_dataset: h5py.Dataset):
    """
    Reads data from a SNIRF file using the HDF5 interface and casts it to a Pythonic type or numpy array. Determines
    the appropriate read function from the properties of h_dataset
    """
    if type(h_dataset) is not h5py.Dataset:
        raise TypeError("'dataset' must be type h5py.Dataset")
    if h_dataset.size > 1:
        if _DTYPE_STR in h_dataset.dtype:
            return _read_string_array(h_dataset)
        elif _DTYPE_INT in h_dataset.dtype:
            return _read_int_array(h_dataset)
        elif _DTYPE_FLOAT in h_dataset.dtype:
            return _read_float_array(h_dataset)
    else:
        if _DTYPE_STR in h_dataset.dtype:
            return _read_string(h_dataset)
        elif _DTYPE_INT in h_dataset.dtype:
            return _read_int(h_dataset)
        elif _DTYPE_FLOAT in h_dataset.dtype:
            return _read_float(h_dataset)
    raise TypeError("Dataset dtype='" + str(h_dataset.dtype)
    + "' not recognized. Expecting dtype to contain one of these: " + str([_DTYPE_STR, _DTYPE_INT, _DTYPE_FLOAT]))


def _read_string(dataset: h5py.Dataset):
    # Because many SNIRF files are saved with string values in length 1 arrays
    if type(dataset) is not h5py.Dataset:
        raise TypeError("'dataset' must be type h5py.Dataset")
    if dataset.ndim > 0:
        return str(dataset[0].decode('ascii'))
    else:
        return str(dataset[()].decode('ascii'))


def _read_int(dataset: h5py.Dataset):
    # Because many SNIRF files are saved with string values in length 1 arrays
    if type(dataset) is not h5py.Dataset:
        raise TypeError("'dataset' must be type h5py.Dataset")
    if dataset.ndim > 0:
        return int(dataset[0])
    else:
        return int(dataset[()])


def _read_float(dataset: h5py.Dataset):
    # Because many SNIRF files are saved with string values in length 1 arrays
    if type(dataset) is not h5py.Dataset:
        raise TypeError("'dataset' must be type h5py.Dataset")
    if dataset.ndim > 0:
        return float(dataset[0])
    else:
        return float(dataset[()])


def _read_string_array(dataset: h5py.Dataset):
    if type(dataset) is not h5py.Dataset:
        raise TypeError("'dataset' must be type h5py.Dataset")
    return np.array(dataset).astype(str)


def _read_int_array(dataset: h5py.Dataset):
    if type(dataset) is not h5py.Dataset:
        raise TypeError("'dataset' must be type h5py.Dataset")
    return np.array(dataset).astype(int)


def _read_float_array(dataset: h5py.Dataset):
    if type(dataset) is not h5py.Dataset:
        raise TypeError("'dataset' must be type h5py.Dataset")
    return np.array(dataset).astype(float)


# -----------------------------------------


class SnirfFormatError(Exception):
    pass


class SnirfConfig:
    logger: logging.Logger = _logger
    dynamic_loading: bool = False  # If False, data is loaded in the constructor, if True, data is loaded on access


class AbsentDataset():    
    def __repr__(self):
        return str(None)


class AbsentGroup():
    def __repr__(self):
        return str(None)


class Group(ABC):

    def __init__(self, varg, cfg: SnirfConfig):
        """
        Wrapper for an HDF5 Group element defined by SNIRF. Must be created with a
        Group ID or string specifying a complete path relative to file root--in
        the latter case, the wrapper will not correspond to a real HDF5 group on
        disk until _save() (with no arguments) is executed for the first time
        """
        self._cfg = cfg
        if type(varg) is str:  # If a Group wrapper is created prior to a save to HDF Group object
            self._h = {}
            self._location = varg
        elif isinstance(varg, h5py.h5g.GroupID):  # If Group is created based on an HDF Group object
            self._h = h5py.Group(varg)
            self._location = self._h.name
        else:
            raise TypeError('must initialize ' + self.__class__.__name__ + ' with a Group ID or string, not ' + str(type(varg)))

    def save(self, *args):
        """
        Entry to Group-level save
        """
        if len(args) > 0:
            if type(args[0]) is h5py.File:
                self._cfg.logger.info('Group-level save of %s in %s', self.location, self.filename)
                self._save(args[0])
            elif type(args[0]) is str:
                path = args[0]
                if not path.endswith('.snirf'):
                    path += '.snirf'
                if os.path.exists(path):
                    file = h5py.File(path, 'w')
                else:
                    raise FileNotFoundError("No such SNIRF file '" + path + "'. Create a SNIRF file before attempting to save a Group to it.")
                self._cfg.logger.info('Group-level save of %s in %s to new file %s', self.location, self.filename, file)
                self._save(file)
                file.close()
        else:
            if self._h != {}:
                file = self._h.file
            self._cfg.logger.info('Group-level save of %s in %s', self.location, file)
            self._save(file)
            
    @property
    def filename(self):
        """
        Returns None if the wrapper is not associated with a Group on disk        
        """
        if self._h != {}:
            return self._h.file.filename
        else:
            return None

    @property
    def location(self):
        if self._h != {}:
            return self._h.name
        else:
            return self._location
    
    @abstractmethod
    def _save(self, *args):
        """
        args is path or empty
        """
        raise NotImplementedError('_save is an abstract method')
        
    def __repr__(self):
        props = [p for p in dir(self) if ('_' not in p and not callable(getattr(self, p)))]
        out = str(self.__class__.__name__) + ' at ' + str(self.location) + '\n'
        for prop in props:
            attr = getattr(self, prop)
            out += prop + ': '
            if type(attr) is np.ndarray or type(attr) is list:
                if np.size(attr) > 32:
                    out += '<' + str(np.shape(attr)) + ' array of ' + str(attr.dtype) + '>'
                else:
                    out += str(attr)
            else:
                prepr = str(attr)
                if len(prepr) < 64:
                    out += prepr
                else:
                    out += '\n' + prepr
            out += '\n'
        return out[:-1]

    def __getitem__(self, key):
        if self._h != {}:
            if key in self._h:
                return self._h[key]
        else:
            return None

    def __contains__(self, key):
        return key in self._h;


class IndexedGroup(MutableSequence, ABC):
    """
    Represents the "indexed group" which is defined by v1.0 of the SNIRF
    specification as:
        If a data element is an HDF5 group and contains multiple sub-groups,
        it is referred to as an indexed group. Each element of the sub-group
        is uniquely identified by appending a string-formatted index (starting
        from 1, with no preceding zeros) in the name, for example, /.../name1
        denotes the first sub-group of data element name, and /.../name2
        denotes the 2nd element, and so on.
    """
    
    _name: str = ''  # The specified prefix to this indexed group's members, i.e. nirs, data, stim, aux, measurementList
    _element: Group = None  # The type of Group which belongs to this IndexedGroup

    def __init__(self, parent: Group, cfg: SnirfConfig):
        # Because the indexed group is not a true HDF5 group but rather an
        # iterable list of HDF5 groups, it takes a base group or file and
        # searches its keys, appending the appropriate elements to itself
        # in order
        self._parent = parent
        self._cfg = cfg
        self._populate_list()
        self._cfg.logger.info('IndexedGroup %s at %s in %s initalized with %i instances of %s', self.__class__.__name__,
                              self._parent.location, self.filename, len(self._list), self._element)
    
    @property
    def filename(self):
        return self._parent.filename

    def __len__(self): return len(self._list)

    def __getitem__(self, i): return self._list[i]

    def __delitem__(self, i): del self._list[i]
    
    def __setitem__(self, i, item):
        self._check_type(item)
        if not item.location in [e.location for e in self._list]:
            self._list[i] = item
        else:
            raise SnirfFormatError(item.location + ' already an element of ' + self.__class__.__name__)

    def __getattr__(self, name):
        # If user tries to access an element's properties, raise informative exception
        if name in [p for p in dir(self._element) if ('_' not in p and not callable(getattr(self._element, p)))]:
            raise AttributeError(self.__class__.__name__ + ' is an interable list of '
                                + str(len(self)) + ' ' + str(self._element)
                                + ', access these with an index i.e. '
                                + str(self._name) + '[0].' + name
                                )

    def __repr__(self):
        return str('<' + 'iterable of ' + str(len(self._list)) + ' ' + str(self._element) + '>')

    def insert(self, i, item):
        self._check_type(item)
        self._list.insert(i, item)
        self._cfg.logger.info('%i th element inserted into IndexedGroup %s at %s in %s at %i', len(self._list),
                              self.__class__.__name__, self._parent.location, self.filename, i)

    def append(self, item):
        self._check_type(item)
        self._list.append(item)
        self._cfg.logger.info('%i th element appended to IndexedGroup %s at %s in %s', len(self._list),
                              self.__class__.__name__, self._parent.location, self.filename)

    def save(self, *args):
        if len(args) > 0:
            if type(args[0]) is h5py.File:
                self._save(args[0])
                self._cfg.logger.info('IndexedGroup-level save of %s at %s in %s', self.__class__.__name__,
                      self._parent.location, self.filename)
            elif type(args[0]) is str:
                path = args[0]
                if not path.endswith('.snirf'):
                    path += '.snirf'
                if os.path.exists(path):
                    file = h5py.File(path, 'w')
                else:
                    raise FileNotFoundError("No such SNIRF file '" + path + "'. Create a SNIRF file before attempting to save an IndexedGroup to it.")
                self._cfg.logger.info('IndexedGroup-level save of %s at %s in %s to %s', self.__class__.__name__,
                                      self._parent.location, self.filename, file)
                self._save(file)
                file.close()
        else:
            if self._parent._h != {}:
                file = self._parent._h.file
            self._save(file)
            self._cfg.logger.info('IndexedGroup-level save of %s at %s in %s', self.__class__.__name__,
                      self._parent.location, self.filename)

    def appendGroup(self):
        'Adds a group to the end of the list'
        location = self._parent.location + '/' + self._name + str(len(self._list) + 1)
        self._list.append(self._element(location, self._cfg))
        self._cfg.logger.info('%i th %s appended to IndexedGroup %s at %s in %s', len(self._list),
                          self._element, self.__class__.__name__, self._parent.location, self.filename)
    
    def _populate_list(self):
        """
        Add all the appropriate groups in parent to the list
        """
        self._list = list()
        names = self._get_matching_keys()
        for name in names:
            if name in self._parent._h:
                self._list.append(self._element(self._parent[name].id, self._cfg))
    
    def _check_type(self, item):
        if type(item) is not self._element:
            raise TypeError('elements of ' + str(self.__class__.__name__) +
                            ' must be ' + str(self._element) + ', not ' +
                            str(type(item))
                            )
        
    def _order_names(self, h=None):
        '''
        Enforce the format of the names of HDF5 groups within a group or file on disk. i.e. IndexedGroup stim's elements
        will be renamed, in order, /stim1, /stim2, /stim3. This is expensive but can be avoided by save()ing individual groups
        within the IndexedGroup
        '''
        if h is None:
            h = self._parent._h
        if all([len(e.location.split('/' + self._name)[-1]) > 0 for e in self._list]):
            if not [int(e.location.split('/' + self._name)[-1]) for e in self._list] == list(range(1, len(self._list) + 1)):
                self._cfg.logger.info('renaming elements of IndexedGroup ' + self.__class__.__name__ + ' at '
                                      + self._parent.location + ' in ' + self.filename + ' to agree with naming format')
                # if list is not already ordered propertly
                for i, e in enumerate(self._list):
                    # To avoid assignment to an existing name, move all
                    h.move(e.location,
                           '/'.join(e.location.split('/')[:-1]) + '/' + self._name + str(i + 1) + '_tmp')
                    self._cfg.logger.info(e.location, '--->',
                                          '/'.join(e.location.split('/')[:-1]) + '/' + self._name + str(i + 1) + '_tmp')
                for i, e in enumerate(self._list):
                    h.move('/'.join(e.location.split('/')[:-1]) + '/' + self._name + str(i + 1) + '_tmp',
                           '/'.join(e.location.split('/')[:-1]) + '/' + self._name + str(i + 1))
                    self._cfg.logger.info('/'.join(e.location.split('/')[:-1]) + '/' + self._name + str(i + 1) + '_tmp',
                                          '--->', '/'.join(e.location.split('/')[:-1]) + '/' + self._name + str(i + 1))

    def _get_matching_keys(self, h=None):
        '''
        Return sorted list of a group or file's keys which match this IndexedList's _name format
        '''
        if h is None:
            h = self._parent._h
        unordered = []
        indices = []
        for key in h:
            numsplit = key.split(self._name)
            if len(numsplit) > 1 and len(numsplit[1]) > 0:
                if len(numsplit[1]) == len(str(int(numsplit[1]))):
                    unordered.append(key)
                    indices.append(int(numsplit[1]))
            elif key.endswith(self._name):
                unordered.append(key)
                indices.append(0)
        order = np.argsort(indices)
        return [unordered[i] for i in order]
        
    def _save(self, *args):
        if len(args) > 0 and type(args[0]) is h5py.File:
            h = args[0]
        else:
            if self._parent._h != {}:
                h = self._parent._h.file
            else:
                raise ValueError('Cannot save an anonymous ' + self.__class__.__name__ + ' instance')
        names_in_file = self._get_matching_keys(h=h)  # List of all names in the file on disk
        names_to_save = [e.location.split('/')[-1] for e in self._list]  # List of names in the wrapper
        # Remove groups which remain on disk after being removed from the wrapper
        for name in names_in_file:
            if name not in names_to_save:
                del h[self._parent.name + '/' + name]  # Remove the actual data from the hdf5 file.
        for e in self._list:
            e._save(*args)  # Group save functions handle the write to disk
        self._order_names(h=h)  # Enforce order in the group names

