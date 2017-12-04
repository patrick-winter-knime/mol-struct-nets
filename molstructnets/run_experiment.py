from util import initialization
from keras import backend
import gc
import time
import argparse
from experiments import experiment
from util import file_structure, logger, file_util, constants
from steps import steps_repository
import h5py
import datetime
import subprocess
import sys


def get_arguments():
    parser = argparse.ArgumentParser(description='Runs an existing experiment')
    parser.add_argument('experiment', type=str, help='Path to the experiment file')
    parser.add_argument('--data_set', type=str, default=None, help='Data set name')
    parser.add_argument('--target', type=str, default=None, help='Target name')
    parser.add_argument('--partition', type=str, default=None, help='Partition name')
    parser.add_argument('--step', type=int, default=None, help='Run the experiment up to the given step')
    return parser.parse_args()


def get_n(global_parameters_):
    n_ = None
    if constants.GlobalParameters.data_set in global_parameters_:
        data_set_path = file_structure.get_data_set_file(global_parameters_)
        if file_util.file_exists(data_set_path):
            data_h5 = h5py.File(data_set_path)
            if file_structure.DataSet.smiles in data_h5.keys():
                n_ = len(data_h5[file_structure.DataSet.smiles])
            data_h5.close()
    return n_


def add_last_commit_hash(script_path, global_parameters):
    commit_hash_path = file_structure.get_commit_hash_file(global_parameters)
    if not file_util.file_exists(commit_hash_path):
        git_repo_path = file_util.get_parent(script_path)
        hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=git_repo_path).decode('utf-8')[:-1]
        with open(commit_hash_path, 'w') as commit_hash_file:
            commit_hash_file.write(hash)


args = get_arguments()
if not file_util.file_exists(args.experiment):
    logger.log('Experiment file ' + args.experiment + ' does not exist.', logger.LogLevel.ERROR)
    exit(1)
start_time = datetime.datetime.now()
logger.log('Starting experiment at ' + str(start_time))
experiment_ = experiment.Experiment(args.experiment)
global_parameters = dict()
global_parameters[constants.GlobalParameters.seed] = initialization.seed
global_parameters[constants.GlobalParameters.root] = file_structure.get_root_from_experiment_file(args.experiment)
global_parameters[constants.GlobalParameters.experiment] = experiment_.get_name()
if args.data_set is not None:
    global_parameters[constants.GlobalParameters.data_set] = file_structure.find_data_set(global_parameters,
                                                                                          args.data_set)
if args.target is not None:
    global_parameters[constants.GlobalParameters.target] = file_structure.find_target(global_parameters, args.target)
if args.partition is not None:
    global_parameters[constants.GlobalParameters.partition_data] = file_structure.find_partition(global_parameters,
                                                                                                 args.partition)
n = get_n(global_parameters)
if n is not None:
    global_parameters[constants.GlobalParameters.n] = n
nr_steps = experiment_.number_steps()
if args.step is not None:
    nr_steps = args.step + 1
for i in range(nr_steps):
    step_config = experiment_.get_step(i)
    type_name = steps_repository.instance.get_step_name(step_config['type'])
    step = steps_repository.instance.get_step_implementation(step_config['type'], step_config['id'])
    logger.log('=' * 100)
    logger.log('Starting step: ' + type_name + ': ' + step.get_name())
    parameters = {}
    implementation_parameters = step.get_parameters()
    for parameter in implementation_parameters:
        if 'default' in parameter:
            parameters[parameter['id']] = parameter['default']
    if 'parameters' in step_config:
        for parameter in step_config['parameters']:
            parameters[parameter] = step_config['parameters'][parameter]
    step.check_prerequisites(global_parameters, parameters)
    step.execute(global_parameters, parameters)
    logger.log('Finished step: ' + type_name + ': ' + step.get_name())
    backend.clear_session()
logger.log('=' * 100)
add_last_commit_hash(sys.argv[0], global_parameters)
end_time = datetime.datetime.now()
logger.log('Finished execution of experiment successfully at ' + str(end_time))
logger.log('Duration of experiment: ' + str(end_time - start_time))
gc.collect()
time.sleep(1)
