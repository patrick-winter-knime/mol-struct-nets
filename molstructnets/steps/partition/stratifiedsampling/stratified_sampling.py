from util import data_validation, file_structure, misc, file_util, progressbar, logger, constants, hdf5_util
import random
import h5py
import math


class StratifiedSampling:

    @staticmethod
    def get_id():
        return 'stratified_sampling'

    @staticmethod
    def get_name():
        return 'Stratified Sampling'

    @staticmethod
    def get_parameters():
        parameters = list()
        parameters.append({'id': 'train_percentage', 'name': 'Size of training partition (in %)', 'type': int,
                           'description': 'The percentage of the data that will be used for training.'})
        parameters.append({'id': 'oversample', 'name': 'Oversample training partition', 'type': bool,
                           'description': 'If this is set the minority class will be oversampled, so that the class'
                                          ' distribution in the training set is equal.'})
        parameters.append({'id': 'shuffle', 'name': 'Shuffle training partition', 'type': bool,
                           'description': 'If this is set the training data will be shuffled.'})
        return parameters

    @staticmethod
    def check_prerequisites(global_parameters, local_parameters):
        data_validation.validate_data_set(global_parameters)
        data_validation.validate_target(global_parameters)

    @staticmethod
    def get_result_file(global_parameters, local_parameters):
        hash_parameters = misc.copy_dict_from_keys(global_parameters, [constants.GlobalParameters.seed])
        hash_parameters.update(misc.copy_dict_from_keys(local_parameters, ['train_percentage', 'oversample', 'shuffle']))
        file_name = 'stratified_sampling_' + misc.hash_parameters(hash_parameters) + '.h5'
        return file_util.resolve_subpath(file_structure.get_partition_folder(global_parameters), file_name)

    @staticmethod
    def execute(global_parameters, local_parameters):
        partition_path = StratifiedSampling.get_result_file(global_parameters, local_parameters)
        global_parameters[constants.GlobalParameters.partition_data] = partition_path
        if file_util.file_exists(partition_path):
            logger.log('Skipping step: ' + partition_path + ' already exists')
        else:
            random_ = random.Random(global_parameters[constants.GlobalParameters.seed])
            target_h5 = h5py.File(file_structure.get_target_file(global_parameters), 'r')
            classes = target_h5[file_structure.Target.classes]
            temp_partition_path = file_util.get_temporary_file_path('stratified_sampling')
            partition_h5 = h5py.File(temp_partition_path, 'w')
            active_indices = []
            inactive_indices = []
            logger.log('Retrieving active and inactive data')
            with progressbar.ProgressBar(len(classes)) as progress:
                for i in range(len(classes)):
                    if classes[i, 0] > 0.0:
                        active_indices.append(i)
                    else:
                        inactive_indices.append(i)
                    progress.increment()
            logger.log('Found ' + str(len(active_indices)) + ' active indices and ' + str(len(inactive_indices)) +
                       ' inactive data points')
            number_training = round(len(classes) * local_parameters['train_percentage'] * 0.01)
            number_training_active = round(number_training * (len(active_indices) / len(classes)))
            number_training_inactive = number_training - number_training_active
            logger.log('Picking data points for training')
            with progressbar.ProgressBar(number_training) as progress:
                for i in range(number_training_active):
                    del active_indices[random_.randint(0, len(active_indices) - 1)]
                    progress.increment()
                for i in range(number_training_inactive):
                    del inactive_indices[random_.randint(0, len(inactive_indices) - 1)]
                    progress.increment()
            partition_train = partition_h5.create_dataset(file_structure.Partitions.train, (number_training,),
                                                          dtype='I')
            partition_test = partition_h5.create_dataset(file_structure.Partitions.test,
                                                         (len(classes) - number_training,), dtype='I')
            logger.log('Writing partitions')
            with progressbar.ProgressBar(len(classes)) as progress:
                partition_train_index = 0
                partition_test_index = 0
                for i in range(len(classes)):
                    if classes[i, 0] > 0.0:
                        if i in active_indices:
                            partition_test[partition_test_index] = i
                            partition_test_index += 1
                        else:
                            partition_train[partition_train_index] = i
                            partition_train_index += 1
                    else:
                        if i in inactive_indices:
                            partition_test[partition_test_index] = i
                            partition_test_index += 1
                        else:
                            partition_train[partition_train_index] = i
                            partition_train_index += 1
                    progress.increment()
            if local_parameters['oversample']:
                StratifiedSampling.oversample(partition_h5, file_structure.Partitions.train, classes)
                partition_train = partition_h5[file_structure.Partitions.train]
            if local_parameters['shuffle']:
                StratifiedSampling.shuffle(partition_train, random_)
            target_h5.close()
            partition_h5.close()
            hdf5_util.set_property(temp_partition_path, 'train_percentage', local_parameters['train_percentage'])
            hdf5_util.set_property(temp_partition_path, 'oversample', local_parameters['oversample'])
            hdf5_util.set_property(temp_partition_path, 'shuffle', local_parameters['shuffle'])
            file_util.move_file(temp_partition_path, partition_path)

    @staticmethod
    def oversample(partition_h5, data_set_name, classes):
        logger.log('Oversampling data')
        ref = partition_h5[data_set_name]
        class_zero_count = 0
        class_one_count = 0
        for i in range(ref.shape[0]):
            value = classes[ref[i]]
            if value[0] >= value[1]:
                class_zero_count += 1
            else:
                class_one_count += 1
        difference = abs(class_zero_count - class_one_count)
        oversampled = partition_h5.create_dataset(data_set_name + '-oversampled', (ref.shape[0] + difference, ),
                                                  dtype='I')
        left_difference = difference
        if class_zero_count < class_one_count:
            copies_per_instance = int(math.ceil(class_one_count / class_zero_count))
        else:
            copies_per_instance = int(math.ceil(class_zero_count / class_one_count))
        target_i = 0
        with progressbar.ProgressBar(oversampled.shape[0]) as progress:
            for i in range(len(ref)):
                value = classes[ref[i]]
                minority = (class_zero_count < class_one_count and value[0] >= value[1]) or \
                           (class_one_count < class_zero_count and value[1] > value[0])
                copies = 1
                if left_difference > 0 and minority:
                    copies = min(left_difference + 1, copies_per_instance)
                    left_difference -= copies - 1
                for j in range(copies):
                    oversampled[target_i] = ref[i]
                    target_i += 1
                    progress.increment()
        del partition_h5[data_set_name]
        partition_h5[data_set_name] = partition_h5[data_set_name + '-oversampled']
        del partition_h5[data_set_name + '-oversampled']

    @staticmethod
    def shuffle(data_set, random_):
        n = len(data_set)
        logger.log('Shuffling data')
        with progressbar.ProgressBar(n) as progress:
            for i in range(n):
                j = random_.randint(0, n-1)
                tmp = data_set[j]
                data_set[j] = data_set[i]
                data_set[i] = tmp
                progress.increment()
