#!/usr/bin/env python
""" IDS tools """

from __future__ import print_function
import md5
import random
import re

import sklearn.model_selection as sk_mod

from log_entry import LogEntry
import ids_data
from ids_converter import IdsConverter


### Dicts ###


def enumerate_to_dict(sequence, verify_hash):
	""" Enumerate the given sequence and save the items in a dict as item : index pairs. """

	mapping = {}
	for index, item in enumerate(sequence):
		mapping[item] = index

	verify_md5(mapping, verify_hash)
	return mapping


def flip_dict(given_dict, verify_hash):
	""" Flip keys and values in the given dict. Values need to be unique! """

	result = {}
	for key, value in given_dict.items():
		if value in result:
			raise ValueError("Given dict has non-unique values!")
		result[value] = key

	verify_md5(result, verify_hash)
	return result


### MD5 ###


def verify_md5(obj, md5_hex_digest):
	""" Verify that the given object's string representation hashes to the given md5. """

	obj_hash = get_md5_hex(obj)
	if obj_hash != md5_hex_digest:
		raise ValueError("Invalid object given. Received obj with hash: {}.".format(obj_hash))


def get_md5_hex(obj):
	""" Create the md5 hex hash of the given object's string representation. """
	return md5.new(str(obj)).hexdigest()


### LogEntry handling ###


def log_entry_to_app_id(log_entry):
	""" Extract and sanitize the app_id from the given LogEntry object. """

	app_id = log_entry.data[LogEntry.APP_ID_FIELD]
	return _strip_app_id(app_id)


def _strip_app_id(app_id):
	""" Strip the given app_id of its ID. """

	# Match indices in the form of _1
	match = re.search(r"\_\d+", app_id)

	# Remove the matched part
	if match:
		app_id = app_id[:match.start()]

	if app_id not in ids_data.get_app_ids():
		raise ValueError("Invalid app id given!")

	return app_id


### Training, testing, validating ###


def converted_entries_to_train_test(converted_entries, binary=True):
	"""
	Splits the given entries up. All intruded entries go into the test set, with some normal ones.
	returns: (train: [(app_id, vector, class)], test: [(app_id, vector, class)]) """

	if not binary:
		raise NotImplementedError()

	first_entry = converted_entries[0]
	if (len(first_entry) != 3
		or len(first_entry[1]) < 2
		or first_entry[2] not in [1, -1]):
		raise ValueError("Given entries are probably not converted entries! Please verify data: {}"
			.format(first_entry))

	converter = IdsConverter()
	entries_normal = []
	entries_intruded = []
	for entry in converted_entries:
		if converter.prediction_means_outlier(entry[2]):
			entries_intruded.append(entry)
		else:
			entries_normal.append(entry)

	percentage_intruded = (len(entries_intruded) / float(len(entries_normal)))
	test_size = min(percentage_intruded, 0.15)
	train, test = sk_mod.train_test_split(entries_normal, test_size=test_size)

	training_entries = train
	scoring_entries = entries_intruded + test
	random.shuffle(scoring_entries)

	return (training_entries, scoring_entries)


### Generating log entries ###


def generate_log_entries(number):
	""" Generate <number> LogEntry objects. """
	import random

	result = []
	vins = [chr(random.choice(range(65, 91))) + str(x)
		for x in random.sample(range(100000, 900000), int(number))]
	colr_gen = lambda: random.randint(0, 255)
	tsp_gen = lambda: random.randint(0, 499)
	log_msg_gens = [
		(ids_data.get_generators(), lambda: str(float(random.randint(-3, 2)))),
		(ids_data.get_colours(), lambda: "{},{},{}".format(colr_gen(), colr_gen(), colr_gen())),
		(ids_data.POSE_CC, lambda: random.choice(["DE", "AT", "CH", "FR"])),
		(ids_data.POSE_POI,
			(lambda: random.choice(ids_data.get_poi_types()) + ","
			+ random.choice(ids_data.get_poi_results()))),
		(ids_data.POSE_TSP,
			lambda: "{},{},{},{}".format(tsp_gen(), tsp_gen(), tsp_gen(), tsp_gen()))
	]

	for i in range(0, int(number)):
		vin = vins[i]
		app_id = random.choice(ids_data.get_app_ids())
		level = random.choice(ids_data.get_levels())
		gps_position = "{},{}".format(tsp_gen(), tsp_gen())

		log_message = None
		for keys, gen in log_msg_gens:
			if app_id in keys:
				log_message = gen()
		if not log_message:
			raise ValueError("You suck!")

		intrusion = random.choice(ids_data.get_labels())

		result.append(LogEntry(
			vin=vin, app_id=app_id, level=level, gps_position=gps_position,
			log_message=log_message, intrusion=intrusion))

	return result
