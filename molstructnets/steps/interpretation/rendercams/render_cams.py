import h5py

from steps.interpretation.shared import matrix_2d_renderer, smiles_renderer
from steps.interpretation.shared.kerasviz import cam
from util import data_validation, file_structure, file_util, progressbar, logger, misc, thread_pool, constants


number_threads = thread_pool.default_number_threads


class RenderCams:

    @staticmethod
    def get_id():
        return 'render_cams'

    @staticmethod
    def get_name():
        return 'Render CAMs'

    @staticmethod
    def get_parameters():
        parameters = list()
        parameters.append({'id': 'renderer', 'name': 'Renderer', 'type': str, 'default': 'automatic',
                           'options': ['automatic', 'smiles', '2d'],
                           'description': 'The renderer that should be used. If automatic the smiles renderer is used '
                                          'for 1d data and the 2d renderer is used for 2d data. Default: automatic'})
        return parameters

    @staticmethod
    def check_prerequisites(global_parameters, local_parameters):
        data_validation.validate_data_set(global_parameters)
        data_validation.validate_preprocessed(global_parameters)
        data_validation.validate_cam(global_parameters)

    @staticmethod
    def execute(global_parameters, local_parameters):
        cam_h5 = h5py.File(file_structure.get_cam_file(global_parameters), 'r')
        data_h5 = h5py.File(file_structure.get_data_set_file(global_parameters), 'r')
        smiles = data_h5[file_structure.DataSet.smiles]
        preprocessed_h5 = h5py.File(global_parameters[constants.GlobalParameters.preprocessed_data], 'r')
        preprocessed = preprocessed_h5[file_structure.Preprocessed.preprocessed]
        symbols = preprocessed_h5[file_structure.Preprocessed.index]
        renderer = local_parameters['renderer']
        if renderer == 'automatic':
            if len(global_parameters[constants.GlobalParameters.input_dimensions]) == 2:
                renderer = 'smiles'
            elif len(global_parameters[constants.GlobalParameters.input_dimensions]) == 3:
                renderer = '2d'
            else:
                raise ValueError('Unsupported dimensionality for rendering')
        if file_structure.Cam.cam_active in cam_h5.keys():
            active_dir_path = file_util.resolve_subpath(file_structure.get_interpretation_folder(global_parameters),
                                                        'rendered_cams_active')
            file_util.make_folders(active_dir_path, True)
            cam_active = cam_h5[file_structure.Cam.cam_active]
            if file_structure.Cam.cam_active_indices in cam_h5.keys():
                indices = cam_h5[file_structure.Cam.cam_active_indices]
            else:
                indices = range(len(cam_active))
            logger.log('Rendering active CAMs', logger.LogLevel.INFO)
            chunks = misc.chunk(len(preprocessed), number_threads)
            with progressbar.ProgressBar(len(indices)) as progress:
                with thread_pool.ThreadPool(number_threads) as pool:
                    for chunk in chunks:
                        pool.submit(RenderCams.render, preprocessed, cam_active, indices, smiles,
                                    symbols, active_dir_path, renderer, chunk['start'], chunk['end'], progress)
                    pool.wait()
        if file_structure.Cam.cam_inactive in cam_h5.keys():
            inactive_dir_path = file_util.resolve_subpath(file_structure.get_interpretation_folder(global_parameters),
                                                          'rendered_cams_inactive')
            file_util.make_folders(inactive_dir_path, True)
            cam_inactive = cam_h5[file_structure.Cam.cam_inactive]
            if file_structure.Cam.cam_inactive_indices in cam_h5.keys():
                indices = cam_h5[file_structure.Cam.cam_inactive_indices]
            else:
                indices = range(cam_inactive)
            logger.log('Rendering inactive CAMs', logger.LogLevel.INFO)
            chunks = misc.chunk(len(preprocessed), number_threads)
            with progressbar.ProgressBar(len(indices)) as progress:
                with thread_pool.ThreadPool(number_threads) as pool:
                    for chunk in chunks:
                        pool.submit(RenderCams.render, preprocessed, cam_inactive, indices, smiles,
                                    symbols, inactive_dir_path, renderer, chunk['start'], chunk['end'], progress)
                    pool.wait()
        cam_h5.close()
        preprocessed_h5.close()
        data_h5.close()

    @staticmethod
    def render(preprocessed, data_set, indices, smiles, symbols, output_dir_path, renderer, start, end, progress):
            for i in indices[start:end+1]:
                output_path = file_util.resolve_subpath(output_dir_path, str(i) + '.svgz')
                if not file_util.file_exists(output_path):
                    smiles_string = smiles[i].decode('utf-8')
                    heatmap = cam.array_to_heatmap([data_set[i]])
                    if renderer == 'smiles':
                        smiles_renderer.render(smiles_string, output_path, 5, heatmap)
                    elif renderer == '2d':
                        matrix_2d_renderer.render(output_path, preprocessed[i], symbols, heatmap=heatmap)
                progress.increment()