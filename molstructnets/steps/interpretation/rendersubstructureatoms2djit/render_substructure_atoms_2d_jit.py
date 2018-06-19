import h5py
import numpy
from steps.interpretation.shared import tensor_2d_renderer
from util import data_validation, file_structure, file_util, logger, constants, multi_process_progressbar, process_pool
from steps.preprocessing.shared.tensor2d import tensor_2d_jit_array
import multiprocessing


class RenderSubstructureAtoms2DJit:

    @staticmethod
    def get_id():
        return 'render_substructure_atoms_2d_jit'

    @staticmethod
    def get_name():
        return 'Render Substructure Atoms 2D JIT'

    @staticmethod
    def get_parameters():
        return list()

    @staticmethod
    def check_prerequisites(global_parameters, local_parameters):
        data_validation.validate_preprocessed_jit(global_parameters)
        data_validation.validate_cam(global_parameters)

    @staticmethod
    def execute(global_parameters, local_parameters):
        cam_h5 = h5py.File(file_structure.get_cam_file(global_parameters), 'r')
        preprocessed_h5 = h5py.File(global_parameters[constants.GlobalParameters.preprocessed_data], 'r')
        symbols = preprocessed_h5[file_structure.PreprocessedTensor2DJit.symbols][:]
        preprocessed_h5.close()
        if file_structure.Cam.substructure_atoms in cam_h5.keys():
            active_dir_path = file_util.resolve_subpath(file_structure.get_interpretation_folder(global_parameters),
                                                        'rendered_substructure_atoms')
            file_util.make_folders(active_dir_path, True)
            substructure_atoms = cam_h5[file_structure.Cam.substructure_atoms]
            indices = range(len(substructure_atoms))
            logger.log('Rendering substructure atoms', logger.LogLevel.INFO)
            queue = multiprocessing.Manager().Queue(10)
            with multi_process_progressbar.MultiProcessProgressbar(len(indices), value_buffer=10) as progress:
                with process_pool.ProcessPool(process_pool.default_number_processes) as pool:
                    for i in range(process_pool.default_number_processes):
                        pool.submit(render, global_parameters, symbols, active_dir_path, queue, progress.get_slave())
                    for i in indices:
                        queue.put((i, substructure_atoms[i][:]))
                    for i in range(process_pool.default_number_processes):
                        queue.put(None)
                    pool.wait()
        cam_h5.close()


def render(global_parameters, symbols, output_dir_path, queue, progress):
    preprocessed = tensor_2d_jit_array.load_array(global_parameters, multi_process=False)
    while True:
        next = queue.get()
        if next is None:
            break
        index, data = next
        output_path = file_util.resolve_subpath(output_dir_path, str(index) + '.svgz')
        if not file_util.file_exists(output_path):
            heatmap = generate_heatmap(data)
            tensor_2d_renderer.render(output_path, preprocessed[index], symbols, heatmap=heatmap)
            progress.increment()
    progress.finish()
    preprocessed.close()


def generate_heatmap(substructure_atoms):
    shape = list(substructure_atoms.shape)
    shape.append(3)
    shape = tuple(shape)
    heatmap = numpy.zeros(shape, dtype='uint8')
    assign_color(substructure_atoms, heatmap)
    return heatmap


rgb_black = [0, 0, 0]
rgb_red = [255, 0, 0]


def assign_color(substructure_atoms, heatmap):
    if isinstance(substructure_atoms, numpy.ndarray):
        for i in range(len(substructure_atoms)):
            assign_color(substructure_atoms[i], heatmap[i])
    else:
        if substructure_atoms == 1:
            heatmap[:] = rgb_red[:]
        else:
            heatmap[:] = rgb_black[:]
