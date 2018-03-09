#!/usr/bin/env python
""" Dir utils """

import os
import time
import uuid
from enum import Enum


class Dir(object):
	""" Generic directory and path handling. """

	@staticmethod
	def move_file(file_path, target_folder):
		""" Move the given file from /current/path/file_name to target_folder/file_name. """

		file_name = os.path.basename(file_path)
		if not file_name:
			raise ValueError("File path given misses a file name: {}".format(file_path))

		os.rename(file_path, os.path.join(target_folder, file_name))


class LogDir(object):
	""" Log directory and path handling in the IDS. """

	_LOG_DIR = "log"
	_LOG_FILE_PREFIX = "intrusion_"
	_LOG_FILE_SUFFIX = ".log"


	@staticmethod
	def list_log_files():
		""" Return a list of relative paths of all current log files. """
		return _list_files_by_suffix(LogDir.get_log_dir(), LogDir._LOG_FILE_SUFFIX)


	@staticmethod
	def mk_unique_backup_dir():
		"""
		Mkdir a uniquely named backup folder.
		returns: (folder_name, folder_path)
		"""

		folder_name = LogDir._create_unique_folder_name()
		folder_path = LogDir.get_log_path_for(folder_name)
		os.mkdir(folder_path)

		return(folder_name, folder_path)


	@staticmethod
	def create_unique_log_name():
		""" Create a unique log name based on a UUID. """
		return _create_unique_name(lambda: (
			LogDir._LOG_FILE_PREFIX + uuid.uuid4().__str__() + LogDir._LOG_FILE_SUFFIX))


	@staticmethod
	def _create_unique_folder_name():
		""" Create a unique name for a backup folder based on the current time. """
		return _create_unique_name(lambda: (
			"logs_until_" + time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())))


	@staticmethod
	def get_log_dir():
		""" Return the log directory. Makes sure the folder exists. """

		log_dir = _get_cwd(_for=LogDir._LOG_DIR)

		if not os.path.lexists(log_dir):
			os.mkdir(log_dir)

		return log_dir


	@staticmethod
	def get_log_path_for(name):
		""" Build a path from the given file name and the log directory. """
		return os.path.join(LogDir.get_log_dir(), name)



class ModelDir(object):
	""" Model directory and path handling in the IDS. """

	_MODEL_DIR = "models"
	_MODEL_FILE_SUFFIX = ".model"


	@staticmethod
	def has_models(app_id_list):
		"""
		Check the model directory on disk if there are existing models for each given app_id.
		returns: 0 if no models for the given app_id_list are present, 1 if some and 2 if all are present.
		"""
		raise NotImplementedError()


	@staticmethod
	def _list_model_files():
		""" Return a list of relative paths of all current model files. """
		return _list_files_by_suffix(ModelDir.get_model_dir(), ModelDir._MODEL_FILE_SUFFIX)


	@staticmethod
	def get_model_dir():
		""" Return the model directory. """
		return _get_cwd(_for=ModelDir._MODEL_DIR)



### Shared private util methods ###


_IDS_DIR = "ids"


def _list_files_by_suffix(folder, suffix):
	""" Return a list of relative paths of all files in the folder with the given suffix. """

	all_file_paths = [os.path.join(folder, name) for name in os.listdir(folder)]

	if not all_file_paths:
		return []

	result = []
	for file_path in all_file_paths:
		if os.path.isfile(file_path) and file_path.endswith(suffix):
			result.append(file_path)

	return result


def _get_cwd(_for=None):
	"""
	Return the cwd in respect to where the module was loaded.
	: param _for : Optionally the file or folder to be accessed.
	"""

	cwd = "" if os.path.basename(os.getcwd()) == _IDS_DIR else _IDS_DIR
	return os.path.join(cwd, _for) if _for else cwd


def _create_unique_name(name_creator):
	""" Generic name creator method ensuring uniqueness. """

	name = name_creator()
	while os.path.lexists(LogDir.get_log_path_for(name)):
		name = name_creator()

	return name
