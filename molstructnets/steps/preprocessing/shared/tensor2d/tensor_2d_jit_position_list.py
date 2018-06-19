from numpy import random
import numpy
from util import file_structure, constants, process_pool, misc, buffered_queue
import h5py
from steps.preprocessing.shared.tensor2d import tensor_2d_jit_preprocessor
import random


class Tensor2DJitList():

    def __init__(self, smiles, classes, indices, preprocessed_path, random_seed, multi_process=True):
        self._smiles = smiles
        self._classes = classes
        self._indices = indices
        if multi_process:
            self._pool = process_pool.ProcessPool()
        else:
            self._pool = None
        self._preprocessor = tensor_2d_jit_preprocessor.Tensor2DJitPreprocessor(preprocessed_path)
        self._shape = tuple([len(self._indices)] + list(self._preprocessor.shape))
        self._random_seed = random_seed
        self._iteration = 0

    def shuffle(self):
        random.shuffle(self._indices)
        self._iteration += 1

    def set_iteration(self, iteration):
        self._iteration = iteration

    def __len__(self):
        return self._shape[0]

    def __getitem__(self, item):
        indices = self._indices[item]
        single_item = False
        if not hasattr(indices, '__len__'):
            single_item = True
            indices = [indices]
        random_seed = None
        if self._pool is not None and len(indices) > 1:
            all_results = list()
            chunks = misc.chunk(len(indices), self._pool.get_number_threads())
            for chunk in chunks:
                indices_chunk = indices[chunk['start']:chunk['end'] + 1]
                if self._random_seed is not None:
                    random_seed = self._random_seed + chunk['start'] + self._iteration * len(self)
                self._pool.submit(self._preprocessor.atom_locations, self._smiles[indices_chunk], random_seed)
            results = self._pool.get_results()
            for result in results:
                all_results += result
            return all_results
        else:
            if self._random_seed is not None:
                random_seed = self._random_seed + indices[0] + self._iteration * len(self)
            result = self._preprocessor.atom_locations(self._smiles[indices], random_seed)
            if single_item:
                result = result[0]
            return result

    @property
    def shape(self):
        return self._shape

    @property
    def dtype(self):
        return numpy.float32

    def classes(self, item):
        return self._classes[self._indices[item]]

    def close(self):
        if self._pool is not None:
            self._pool.close()


def load_list(global_parameters, train=False, transform=False, multi_process=True):
    smiles_h5 = h5py.File(file_structure.get_data_set_file(global_parameters), 'r')
    smiles = smiles_h5[file_structure.DataSet.smiles][:]
    smiles_h5.close()
    classes_h5 = h5py.File(file_structure.get_target_file(global_parameters), 'r')
    classes = classes_h5[file_structure.Target.classes][:]
    classes_h5.close()
    if train:
        partition_h5 = h5py.File(file_structure.get_partition_file(global_parameters), 'r')
        partition = partition_h5[file_structure.Partitions.train][:]
        partition_h5.close()
    else:
        partition = numpy.arange(len(smiles), dtype='uint32')
    if transform:
        random_seed = global_parameters[constants.GlobalParameters.seed]
    else:
        random_seed = None
    preprocessed_path = global_parameters[constants.GlobalParameters.preprocessed_data]
    return Tensor2DJitList(smiles, classes, partition, preprocessed_path, random_seed, multi_process=multi_process)
