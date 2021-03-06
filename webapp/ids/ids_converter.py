#!/usr/bin/env python
""" Converter """

import warnings

import numpy
import sklearn.preprocessing as sk_pre

from log_entry import LogEntry
from ids.ids_entry import IdsEntry
import ids_data
import ids_tools


class IdsConverter(object):
	""" Conversion of LogEntry objects. """

	def __init__(self):
		""" Ctor. """

		self.app_ids = ids_data.get_app_ids()
		ids_tools.verify_md5(self.app_ids, "3a88e92473acb1ad1b56e05a8074c7bd")

		self.level_mapping = ids_tools.enumerate_to_dict(
			ids_data.get_levels(),
			verify_hash="49942f0268aa668e146e533b676f03d0")

		self.poi_type_mapping = ids_tools.enumerate_to_dict(
			ids_data.get_poi_types(),
			verify_hash="f2fba0ed17e382e274f53bbcb142565b")

		self.poi_result_mapping = ids_tools.enumerate_to_dict(
			ids_data.get_poi_results(),
			verify_hash="dd1c18c7188a48a686619fef8007fc64")

		self.label_int_mapping = ids_tools.enumerate_to_dict(
			ids_data.get_labels(),
			verify_hash="88074a13baa6f97fa4801f3b0ec53065")

		## Verifier data ##
		# 1 for a binarised level (only two options)
		base_len = 1
		self._len_key = "len"

		self._vector_constraints = {}
		# 1 value (generated)
		for gen_key in ids_data.get_generators():
			self._vector_constraints[gen_key] = {self._len_key : base_len + 1}
		# 3 values for a split colour, 2 values for the position
		for colr_key in ids_data.get_colours():
			self._vector_constraints[colr_key] = {self._len_key : base_len + 5}
		# Poses all have GPS
		for pose_key in ids_data.get_poses():
			self._vector_constraints[pose_key] = {self._len_key : base_len + 2}

		# CC: One of five
		self._vector_constraints[ids_data.POSE_CC][self._len_key] += 5
		# POI: One of 4 types, one of 7 results
		self._vector_constraints[ids_data.POSE_POI][self._len_key] += 11
		# TSP: x, y, targ_x, targ_y
		self._vector_constraints[ids_data.POSE_TSP][self._len_key] += 4


	def log_entry_to_vector(self, app_id, log_entry, binary=True):
		""" Convert the given log_entry to a classifiable vector. """

		vectors = self.log_entries_to_vectors(app_id, [log_entry])
		return vectors[0]


	def log_entries_to_ids_entries_dict(self, all_log_entries, binary=True):
		""" Convert the given LogEntry objects to a { app_id : IdsEntrys } dict. """

		log_entries_per_app_id = {}

		for log_entry in all_log_entries:
			app_id = ids_tools.log_entry_to_app_id(log_entry)

			if app_id not in log_entries_per_app_id:
				log_entries_per_app_id[app_id] = []

			log_entries_per_app_id[app_id].append(log_entry)

		ids_entries_per_app_id = ids_tools.empty_app_id_to_list_dict(log_entries_per_app_id.keys())

		for app_id in log_entries_per_app_id:
			my_log_entries = log_entries_per_app_id[app_id]
			my_ids_entries = self.log_entries_to_ids_entries(app_id, my_log_entries, binary)
			ids_entries_per_app_id[app_id].extend(my_ids_entries)

		self.check_dict(ids_entries_per_app_id)
		return ids_entries_per_app_id


	def ids_entries_to_dict(self, ids_entries):
		""" Store the given LogEntry objects in a { app_id : [IdsEntry] } dict. """

		ids_entries_per_app_id = {}
		for ids_entry in ids_entries:
			if ids_entry.app_id not in ids_entries_per_app_id:
				ids_entries_per_app_id[ids_entry.app_id] = []

			ids_entries_per_app_id[ids_entry.app_id].append(ids_entry)

		self.check_dict(ids_entries_per_app_id)
		return ids_entries_per_app_id


	def log_entries_to_ids_entries(self, expected_app_id, log_entries, binary):
		""" Convert the given LogEntry objects to IdsEntry objects for this app_id. """

		app_ids = [ids_tools.log_entry_to_app_id(log_entry) for log_entry in log_entries]

		if any([a != expected_app_id for a in app_ids]):
			raise ValueError("Given elements are not all of the expected app type: {}"
				.format(expected_app_id))

		vectors = self.log_entries_to_vectors(expected_app_id, log_entries)
		vclasses = [self.log_entry_to_class(log_entry, binary) for log_entry in log_entries]

		ids_entries = []
		for app_id, vector, vclass in zip(app_ids, vectors, vclasses):
			ids_entry = IdsEntry(app_id, vector, vclass)
			ids_entries.append(ids_entry)

		return ids_entries


	def ids_entries_to_X_y(self, ids_entries, app_id=None):
		""" Convert the given IdsEntry objects to (X, y).
		* app_id : Optionally specify the app_id that all entries should have. """

		# pylint: disable-msg=C0103; (Invalid variable name)
		X = []
		y = []

		for ids_entry in ids_entries:
			if app_id and ids_entry.app_id != app_id:
				raise ValueError("Given IdsEntry has an incorrect app_id!")

			X.append(ids_entry.vector)
			y.append(ids_entry.vclass)

		return (X, y)


	def log_entries_to_train_dict(self, log_entries, printer):
		""" Convert the given log entries to { app_id : (X, y) }. """

		printer.prt("Transforming the log data to trainable vectors...")
		ids_entries_dict = self.log_entries_to_ids_entries_dict(log_entries)

		train_dict = {}
		for app_id, ids_entries in ids_entries_dict.items():
			train_dict[app_id] = self.ids_entries_to_X_y(ids_entries, app_id)

		self.check_dict(train_dict)
		printer.prt("Done.")
		return train_dict


	def check_dict(self, given_dict):
		""" Ensure the given dict conforms to our expectations. Call before returning entry dicts! """

		dict_keys = given_dict.keys()
		if any([app_id not in self.app_ids for app_id in dict_keys]):
			raise ValueError("Invalid dict! A key was not expected: %s" % dict_keys)

		dict_values = given_dict.values()
		if any([not elements for elements in dict_values]):
			raise ValueError("Invalid dict! A list is empty or doesn't exist: %s" % dict_values)


	def log_entries_to_vectors(self, app_id, log_entries):
		"""
		Convert the given LogEntry objects to learnable vectors.
		returns: C-ordered numpy.ndarray (dense) with dtype=float64
		"""

		if not log_entries:
			warnings.warn("[IdsConverter().log_entries_to_vectors()] %s: No log entries!" % app_id)
			return numpy.array([])

		# We have: vin, app_id, level, log_message, gps_position, time_unix, log_id
		assert(len(log_entries[0].data) == 7)

		# Discard log_id (unnecessary) and app_id (it's used for mapping to a classifier)
		# Discard VIN (we don't plan on involving specific VINs in intrusion detection)
		# Discard time_unix (is randomly set)
		levels = []
		log_messages = []
		positions = []

		for log_entry in log_entries:
			data_dict = log_entry.data

			levels.append(data_dict[LogEntry.LEVEL_FIELD])
			log_messages.append(data_dict[LogEntry.LOG_MESSAGE_FIELD])
			positions.append(data_dict[LogEntry.GPS_POSITION_FIELD])

		# Binarisation of levels -> [0, 1]
		enc_levels_array = self.levels_binarise(levels)
		# Conversion (data gens) or one-hot encoding of log messages -> [0, 1, ...]
		enc_log_messages_array = self.encode_log_messages(app_id, log_messages)
		# Convert GPS positions to None or (x, y)
		enc_gps_positions_array = self.encode_positions(positions)

		vectors = []

		for enc_lvl, enc_msg, enc_gps in (
			zip(enc_levels_array, enc_log_messages_array, enc_gps_positions_array)):

			# 1 level int, 1-12 log message floats or ints
			data = list(enc_lvl) + list(enc_msg)
			# 0/2 GPS floats
			if enc_gps is not None:
				data += list(enc_gps)

			ndarray = numpy.array(
				data,
				dtype=numpy.float_,
				order="C")

			self.verify_vector(ndarray, app_id)

			vectors.append(ndarray)

		return vectors


	def log_entry_to_class(self, log_entry, binary):
		""" Map the given LogEntry object to a class to predict. """

		if not log_entry.intrusion:
			raise ValueError("Given LogEntry does not have a set intrusion to convert.")

		its_class = self.label_int_mapping[log_entry.intrusion]

		if binary:
			its_class = self.class_to_binary(its_class)

		return its_class


	def class_means_intruded(self, the_class):
		""" Map the given class to a boolean 'is intruded'. """

		if not isinstance(the_class, int):
			raise TypeError("Expected int. Got: {}".format(type(the_class)))

		# Ensure we still have the state we expect.
		legal_labels = ids_data.get_legal_labels()
		if len(legal_labels) != 1 or self.label_int_mapping[legal_labels[0]] != 0:
			raise ValueError("Expected value has changed!")

		return the_class != 0


	def prediction_means_outlier(self, prediction):
		""" LEGACY """
		return ids_tools.is_outlier(prediction)


	def class_to_binary(self, input_class):
		""" Convert an int class to int binary (-1/1). """

		# Inliers are labeled 1, while outliers are labeled -1.
		assert(self.prediction_means_outlier(-1))

		if self.class_means_intruded(input_class):
			return -1
		else:
			return 1


	def classes_to_binary(self, input_classes):
		""" Convert a list of int classes to int binary (-1/1). """

		output_classes = []
		for input_class in input_classes:
			output_classes.append(self.class_to_binary(input_class))
		return output_classes


	def get_expected_classes(self, app_id):
		""" Return a list of expected classes for the given app_id classifier. """

		labels = None
		verify_hash = None

		if app_id in ids_data.get_generators():
			labels = ids_data.get_labels_gens()
			verify_hash = "3e7c91c61534c25b3eb15d40d0c99a73"
		elif app_id in ids_data.get_colours():
			labels = ids_data.get_labels_colrs()
			verify_hash = "e5dce1652563eb67347003bc2f7f3e70"
		elif app_id == ids_data.POSE_CC:
			labels = ids_data.get_labels_pose_cc()
			verify_hash = "5e550fa679c1e0845320660a3c98bb6f"
		elif app_id == ids_data.POSE_POI:
			labels = ids_data.get_labels_pose_poi()
			verify_hash = "9d60b17b201114a17179334aeea66ab5"
		elif app_id == ids_data.POSE_TSP:
			labels = ids_data.get_labels_pose_tsp()
			verify_hash = "9027b46c491b3c759215fdba37a93d84"
		else:
			raise ValueError("Invalid app_id given: {}".format(app_id))

		ids_tools.verify_md5(labels, verify_hash)

		return [self.label_int_mapping[x] for x in labels]


	### Conversions ###


	def levels_binarise(self, levels):
		"""
		Do a binarisation of the given levels.
		returns: Two-dimensional numpy.ndarray with a 1 element binary encoding per row.
		"""

		# For expected levels, see web_api.log_entry.LogEntry
		expected_levels = ["DEBUG", "ERROR"]
		ids_tools.verify_md5(expected_levels, "7692bbdba09aa7f2c9a15ca0e9a654cd")

		encoded_levels = self.generic_one_hot(expected_levels, levels)
		return encoded_levels


	def encode_log_messages(self, app_id, log_messages):
		"""
		Either just convert the data (data generators) or do a one-hot encoding of the log message.
		returns: Two-dimensional numpy.ndarray with either 1 float value, 4 int values
		or up to 11 binary encoded values per row.
		"""

		# Generators send "{f}"
		if app_id in ids_data.get_generators():
			# Return a list with float values
			return numpy.array([[float(log_message)] for log_message in log_messages])

		# Colour sends "{i},{i},{i}"
		if app_id in ids_data.get_colours():
			colours = [[int(val) for val in msg.split(",")] for msg in log_messages]

			# Returns a list with 3 scaled colour floats in [0,1]
			return self.colours_scale(colours)

		# Country code string like "DE" or "CH"
		if app_id == ids_data.POSE_CC:
			# Returns a list with 5 binary flags
			return self.country_codes_one_hot(log_messages)

		# POI pair "type,result"
		if app_id == ids_data.POSE_POI:
			poi_pairs = [msg.split(",") for msg in log_messages]

			# Returns a list with 11 binary flags
			return self.poi_pairs_one_hot(poi_pairs)

		# Two positions as "{},{},{},{}" (start,end as x,y)
		if app_id == ids_data.POSE_TSP:
			coords_rows = [[float(coord) for coord in msg.split(",")] for msg in log_messages]
			assert(len(coords_rows[0]) == 4)
			for coord in coords_rows[0]:
				assert(coord >= 0 and coord < 500)

			# Return list of 4 scaled coordinate floats in [-1,1]
			return self.positions_scale(coords_rows)

		raise NotImplementedError("App ID {} not implemented".format(app_id))


	def colours_one_hot(self, colours):
		"""
		Do a one-hot encoding of the given colours.
		returns: A two-dimensional numpy.ndarray with a 3+4+5=12 element binary encoding per row.
		"""

		# For expected colours, see py_turtlesim.util.Rgb
		reds = [100, 150, 255]
		greens = [0, 125, 180, 240]
		blues = [0, 100, 120, 210, 250]
		ids_tools.verify_md5(reds + greens + blues, "32b6449030a035c63654c4a11ab15eae")

		colours_array = numpy.array(colours)

		red_encodings = self.generic_one_hot(reds, colours_array[:, 0])
		green_encodings = self.generic_one_hot(greens, colours_array[:, 1])
		blue_encodings = self.generic_one_hot(blues, colours_array[:, 2])

		encodings = numpy.concatenate((red_encodings, green_encodings, blue_encodings), axis=1)
		return encodings


	def colours_scale(self, colours):
		"""
		Scale the colour triplets from [0,255] to [0,1].
		returns: A two-dimensional numpy.ndarray with 3 scaled colours per row.
		"""

		scaled = self.generic_scale(
			values=colours,
			range_min=0, range_max=1,
			min_v=0, max_v=255
		)
		return scaled


	def country_codes_one_hot(self, country_codes):
		"""
		Do a one-hot encoding of the given country codes.
		returns: A two-dimensional numpy.ndarray with a 5 element binary encoding per row.
		"""

		# For expected country codes, see web_api.functionality.country_code_mapper
		expected_cc = ids_data.get_country_codes()
		ids_tools.verify_md5(expected_cc, "b1d9e303bda676c3c6a61dc21e1d07c3")

		encodings = self.generic_one_hot(expected_cc, country_codes)
		return encodings


	def poi_pairs_one_hot(self, poi_pairs):
		"""
		Do a one-hot encoding of the given POI pairs.
		returns: A two-dimensional numpy.ndarray with a 4+7=11 element binary encoding per row.
		"""

		# For expected POI types, see turtlesim_expl.pipes.pose_processor
		expected_types = ["gas station", "nsa hq", "private home", "restaurant"]
		ids_tools.verify_md5(expected_types, "e545240e0a39da6af18c018df5952044")
		# For expected POI results, see web_api.functionality.poi_mapper
		exptected_results = ["Aral", "French", "German", "Italian", "Shell", "Total", "Invalid"]
		ids_tools.verify_md5(exptected_results, "88234d800fbb78a73e0dd99379461e07")

		poi_pairs_array = numpy.array(poi_pairs)

		types_encodings = self.generic_one_hot(expected_types, poi_pairs_array[:, 0])
		results_encodings = self.generic_one_hot(exptected_results, poi_pairs_array[:, 1])

		encodings = numpy.concatenate((types_encodings, results_encodings), axis=1)
		return encodings


	def encode_positions(self, positions):
		"""
		Convert the given "x,y" GPS position strings to (x, y) or None.
		returns: A two-dimensional numpy.ndarray with a result (tuple or None) per row.
		"""

		encoded_positions = [self.position_to_none_or_scaled(gps_pos) for gps_pos in positions]
		return numpy.array(encoded_positions)


	def position_to_none_or_scaled(self, position):
		""" Convert the given GPS position string to (x, y). """

		if not position:
			return None

		# Format: x,y
		split = position.split(",")
		if len(split) != 2:
			raise ValueError("Invalid string")

		# generic_scale() operates on a two-dimensional array - we return one dimension
		scaled = self.positions_scale(positions=[split])
		return scaled[0]


	def positions_scale(self, positions):
		"""
		Scale the position rows from [0,499] to [-1,1].
		returns: A two-dimensional numpy.ndarray scaled positions per row.
		"""

		scaled = self.generic_scale(
			values=positions,
			range_min=-1, range_max=1,
			min_v=0, max_v=499
		)
		return scaled


	def generic_one_hot(self, expected_values, values):
		"""
		Do a one-hot encoding of the given values, which are one of expected_values.
		returns: A two-dimensional numpy.ndarray with one encoding per row.
		"""

		if any([value not in expected_values for value in values]):
			filtered = filter(lambda x: x not in expected_values, values)
			raise ValueError("Given values \"{}\" are invalid! Expected one of: {}"
				.format(filtered, expected_values))

		binariser = sk_pre.LabelBinarizer()
		binariser.fit(expected_values)

		encodings = binariser.transform(values)
		return encodings


	# pylint: disable-msg=C0103; (Snake-case naming)
	def generic_scale(self, values, range_min, range_max, min_v, max_v):
		"""
		Scale the given two-dimensional array from [min_v,max_v] to [range_min,range_max].
		*range_min, range_max: The target range
		*min_v, max_v: The source range
		returns: A two-dimensional numpy.ndarray with scaled values.
		"""

		# pylint: disable-msg=C0103; (Snake-case naming)
		X = numpy.array(values, dtype=numpy.float_)

		if X.ndim != 2:
			raise ValueError("generic_scale() requires a two-dimensional input")

		X_min = numpy.array([float(min_v) for _ in values[0]])
		X_max = numpy.array([float(max_v) for _ in values[0]])

		# Source: http://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.MinMaxScaler.html
		X_std = (X - X_min) / (X_max - X_min)
		X_scaled = X_std * (range_max - range_min) + range_min

		return X_scaled


	### Verification ###


	def verify_vector(self, ndarray, app_id):
		""" Verifies the given ndarray fits the app_id classifier. """

		if not isinstance(ndarray, numpy.ndarray) or ndarray.dtype != numpy.float_:
			raise ValueError("Given array is of invalid type.")

		if app_id not in self.app_ids:
			raise ValueError("Invalid app_id: {}".format(app_id))

		expected_len = self._vector_constraints[app_id][self._len_key]
		if len(ndarray) != expected_len:
			raise ValueError("Given ndarray (app_id: %s) has invalid length. Expected %s; Got: %s (len: %s)"
				% (app_id, expected_len, ndarray, len(ndarray)))
