import h5py
from rdkit import Chem

from util import data_validation, file_structure, file_util, progressbar, hdf5_util, logger, thread_pool, misc
from steps.preprocessing.shared.tensor2d import tensor_2d_jit_position_list
import numpy
import queue


class Calculate2DSubstructureAtomsJit:

    @staticmethod
    def get_id():
        return 'calculate_2d_substructure_atoms_jit'

    @staticmethod
    def get_name():
        return 'Calculate 2D Substructure Atoms JIT'

    @staticmethod
    def get_parameters():
        parameters = list()
        parameters.append({'id': 'substructures', 'name': 'Substructures', 'type': str, 'default': None,
                           'description': 'Semicolon separated list of substructure to search for. If None then the'
                                          ' substructures of the target generation step are used. Default: Use'
                                          ' generated target'})
        return parameters

    @staticmethod
    def check_prerequisites(global_parameters, local_parameters):
        data_validation.validate_data_set(global_parameters)
        data_validation.validate_target(global_parameters)
        data_validation.validate_preprocessed_jit(global_parameters)

    @staticmethod
    def execute(global_parameters, local_parameters):
        attention_map_path = file_structure.get_cam_file(global_parameters)
        file_existed = file_util.file_exists(attention_map_path)
        file_util.make_folders(attention_map_path)
        attention_map_h5 = h5py.File(attention_map_path, 'a')
        if file_structure.Cam.substructure_atoms in attention_map_h5.keys():
            logger.log('Skipping step: ' + file_structure.Cam.substructure_atoms + ' in ' + attention_map_path
                       + ' already exists')
            attention_map_h5.close()
        else:
            attention_map_h5.close()
            temp_attention_map_path = file_util.get_temporary_file_path('attention_map')
            if file_existed:
                file_util.copy_file(attention_map_path, temp_attention_map_path)
            else:
                file_util.remove_file(attention_map_path)
            attention_map_h5 = h5py.File(temp_attention_map_path, 'a')
            data_h5 = h5py.File(file_structure.get_data_set_file(global_parameters), 'r')
            smiles = data_h5[file_structure.DataSet.smiles][:]
            data_h5.close()
            if local_parameters['substructures'] is not None:
                substructures = local_parameters['substructures']
            else:
                substructures = hdf5_util.get_property(file_structure.get_target_file(global_parameters),
                                                       'substructures')
            substructures = substructures.split(';')
            atom_locations = tensor_2d_jit_position_list.load_list(global_parameters)
            substructure_atoms = hdf5_util.create_dataset(attention_map_h5,
                                                          file_structure.Cam.substructure_atoms,
                                                          (len(smiles), atom_locations.shape[1], atom_locations.shape[2]),
                                                          dtype='uint8')
            for i in range(len(substructures)):
                substructures[i] = Chem.MolFromSmiles(substructures[i], sanitize=False)
            location_queue = queue.Queue(1000)
            with progressbar.ProgressBar(len(smiles)) as progress:
                with thread_pool.ThreadPool(1) as pool:
                    pool.submit(generate_locations, atom_locations, location_queue)
                    write_substructure_atoms(smiles, substructures, location_queue, substructure_atoms, progress)
            attention_map_h5.close()
            file_util.move_file(temp_attention_map_path, attention_map_path)


def write_substructure_atoms(smiles, substructures, location_queue, substructure_atoms, progress):
    for i in range(len(smiles)):
        atom_locations = location_queue.get()
        result = numpy.zeros((substructure_atoms.shape[1], substructure_atoms.shape[2]), dtype='uint8')
        smiles_string = smiles[i].decode('utf-8')
        molecule = Chem.MolFromSmiles(smiles_string, sanitize=False)
        indices = set()
        for substructure in substructures:
            matches = molecule.GetSubstructMatches(substructure)
            for match in matches:
                for index in match:
                    indices.add(index)
        for index in indices:
            x = atom_locations[index][0]
            y = atom_locations[index][1]
            result[x, y] = 1.0
        # TODO add bonds?
        substructure_atoms[i, :] = result[:]
        progress.increment()


def generate_locations(atom_locations, locations_queue):
    chunks = misc.chunk_by_size(len(atom_locations), 1000)
    for chunk in chunks:
        results = atom_locations[chunk['start']:chunk['end']+1]
        for result in results:
            locations_queue.put(result)
