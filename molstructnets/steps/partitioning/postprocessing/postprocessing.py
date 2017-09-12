from util import data_validation, file_structure, misc, file_util, logger, constants, hdf5_util
import random
import h5py
from steps.partitioning.shared import partitioning


class Postprocessing:

    @staticmethod
    def get_id():
        return 'postprocessing'

    @staticmethod
    def get_name():
        return 'Postprocessing'

    @staticmethod
    def get_parameters():
        parameters = list()
        parameters.append({'id': 'oversample', 'name': 'Oversample training partitioning', 'type': bool,
                           'description': 'If this is set the minority class will be oversampled, so that the class'
                                          ' distribution in the training set is equal.'})
        parameters.append({'id': 'shuffle', 'name': 'Shuffle training partitioning', 'type': bool,
                           'description': 'If this is set the training data will be shuffled.'})
        return parameters

    @staticmethod
    def check_prerequisites(global_parameters, local_parameters):
        data_validation.validate_data_set(global_parameters)
        data_validation.validate_target(global_parameters)
        data_validation.validate_partition(global_parameters)

    @staticmethod
    def get_result_file(global_parameters, local_parameters):
        hash_parameters = misc.copy_dict_from_keys(global_parameters, [constants.GlobalParameters.seed])
        hash_parameters.update(misc.copy_dict_from_keys(local_parameters, ['oversample', 'shuffle']))
        file_name = file_util.get_filename(global_parameters[constants.GlobalParameters.partition_data], False)\
                    + '_postprocessed_' + misc.hash_parameters(hash_parameters) + '.h5'
        return file_util.resolve_subpath(file_structure.get_partition_folder(global_parameters), file_name)

    @staticmethod
    def execute(global_parameters, local_parameters):
        source_partition_path = global_parameters[constants.GlobalParameters.partition_data]
        partition_path = Postprocessing.get_result_file(global_parameters, local_parameters)
        global_parameters[constants.GlobalParameters.partition_data] = partition_path
        if file_util.file_exists(partition_path):
            logger.log('Skipping step: ' + partition_path + ' already exists')
        else:
            random_ = random.Random(global_parameters[constants.GlobalParameters.seed])
            target_h5 = h5py.File(file_structure.get_target_file(global_parameters), 'r')
            classes = target_h5[file_structure.Target.classes]
            temp_partition_path = file_util.get_temporary_file_path('postprocessing')
            file_util.copy_file(source_partition_path, temp_partition_path)
            partition_h5 = h5py.File(temp_partition_path, 'r+')
            partition_train = partition_h5[file_structure.Partitions.train]
            partition_test = partition_h5[file_structure.Partitions.test]
            train_percentage = (len(partition_train) / (len(partition_train) + len(partition_test))) * 100
            if local_parameters['oversample']:
                partition_train = partitioning.oversample(partition_h5, file_structure.Partitions.train, classes)
            if local_parameters['shuffle']:
                partitioning.shuffle(partition_train, random_)
            target_h5.close()
            partition_h5.close()
            hdf5_util.set_property(temp_partition_path, 'train_percentage', train_percentage)
            hdf5_util.set_property(temp_partition_path, 'oversample', local_parameters['oversample'])
            hdf5_util.set_property(temp_partition_path, 'shuffle', local_parameters['shuffle'])
            file_util.move_file(temp_partition_path, partition_path)