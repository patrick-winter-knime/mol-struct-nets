from numpy import random
import numpy
from util import file_structure, constants, process_pool, misc
import h5py
from steps.preprocessing.shared.tensor2d import tensor_2d_jit_preprocessor
import random


class Tensor2DJitArray():

    def __init__(self, smiles, classes, indices, preprocessed_path, random_seed):
        self._smiles = smiles
        self._classes = classes
        self._indices = indices
        self._pool = process_pool.ProcessPool()
        self._preprocessor = tensor_2d_jit_preprocessor.Tensor2DJitPreprocessor(preprocessed_path)
        self._shape = tuple([len(self._indices)] + list(self._preprocessor.shape))
        self._random_seed = random_seed
        self._iteration = 0

    def shuffle(self):
        random.shuffle(self._indices)
        self._iteration += 1

    def __len__(self):
        return self._shape[0]

    def __getitem__(self, item):
        indices = self._indices[item]
        if len(indices) > 1:
            chunks = misc.chunk(len(indices), self._pool.get_number_threads())
            for chunk in chunks:
                indices_chunk = indices[chunk['start']:chunk['end'] + 1]
                self._pool.submit(self._preprocessor.preprocess, self._smiles[indices_chunk],
                                  self._random_seed + chunk['start'] + self._iteration * len(self))
            results = self._pool.get_results()
            all_results = numpy.zeros([len(indices)] + list(self._preprocessor.shape), dtype='float32')
            offset = 0
            for result in results:
                all_results [offset:offset + len(result)] = result[:]
                offset += len(result)
            return all_results
        else:
            return self._preprocessor.preprocess(self._smiles[indices], self._random_seed + indices[0]
                                                 + self._iteration * len(self))

    @property
    def shape(self):
        return self._shape

    def classes(self, item):
        return self._classes[self._indices[item]]

    def close(self):
        self._pool.close()


def load_array(global_parameters, train=False):
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
    preprocessed_path = global_parameters[constants.GlobalParameters.preprocessed_data]
    random_seed = global_parameters[constants.GlobalParameters.seed]
    return Tensor2DJitArray(smiles, classes, partition, preprocessed_path, random_seed)