#!/usr/bin/env python
""" Web API """

# pylint: disable-msg=E1101; (X has no Y member - of course they do)

# Monkey-patch
from gevent import monkey
monkey.patch_all()

# pylint: disable-msg=C0411,C0413
import argparse
import random
import time
from bottle import post, get, run, request, BaseResponse

from log_entry import LogEntry
from state_dao import StateDao
from ids.live_ids import LiveIds
from functionality.country_code_mapper import CountryCodeMapper
from functionality.poi_mapper import PoiMapper
from functionality.routing_mapper import RoutingMapper
import util.fmtr


DAO = None
IDS = None

# Configuration
DETECT = True
STORE = True


### API endpoints ###


@post("/log/data/<generator>")
def log_data(generator):
	""" Log endpoint for data generator """
	_log_num(generator)


def _log_num(name):
	""" Log the given number under the given method name. """

	number_log_entry = _create_base_log_entry(request.params.vin)

	number_log_entry.complete(
		app_id=name.upper(),
		log_message=request.params.generated,
		intrusion=request.params.intrusion
	)

	_append_and_detect(number_log_entry)


@post("/log/colour")
def log_colour():
	""" Log the given colour. """

	crd_x = request.params.x
	crd_y = request.params.y

	colour_log_entry = _create_base_log_entry(request.params.vin)

	colour_log_entry.complete(
		app_id="COLOUR",
		log_message=request.params.colour,
		gps_position=_get_position_string(crd_x, crd_y),
		intrusion=request.params.intrusion
	)

	_append_and_detect(colour_log_entry)


@post("/get/country-code")
def get_country_code():
	""" Map coordinates to country code and save to log. """

	crd_x = request.params.x
	crd_y = request.params.y

	app_id = "COUNTRYCODE"
	position = _get_position_string(crd_x, crd_y)

	country_code = CountryCodeMapper.map(crd_x, crd_y)

	cc_log_entry = _create_base_log_entry(request.params.vin)

	cc_log_entry.complete(
		app_id=app_id,
		log_message=str(country_code),
		gps_position=position,
		intrusion=request.params.intrusion
	)

	_append_and_detect(cc_log_entry)


@post("/get/poi")
def get_poi():
	""" Map coordinates to POI of given type and save to log. """

	crd_x = request.params.x
	crd_y = request.params.y
	poi_type = request.params.type

	app_id = "POI"
	position = _get_position_string(crd_x, crd_y)

	poi_result = PoiMapper.map(poi_type, crd_x, crd_y)

	poi_log_entry = _create_base_log_entry(request.params.vin)

	log_message = "{},{}".format(poi_type, poi_result)
	level = LogEntry.LEVEL_DEFAULT

	if poi_result == "Invalid":
		level = LogEntry.LEVEL_ERROR

	poi_log_entry.complete(
		app_id=app_id,
		log_message=log_message,
		gps_position=position,
		level=level,
		intrusion=request.params.intrusion
	)

	_append_and_detect(poi_log_entry)


@post("/get/tsp")
def get_tsp_routing():
	""" Map current and goal coordinates to TSP and save to log. """

	crd_x = request.params.x
	crd_y = request.params.y
	targ_x = request.params.targ_x
	targ_y = request.params.targ_y

	app_id = "TSPROUTING"
	position = _get_position_string(crd_x, crd_y)

	tsp_message = RoutingMapper.map(crd_x, crd_y, targ_x, targ_y)

	tsp_log_entry = _create_base_log_entry(request.params.vin)

	tsp_log_entry.complete(
		app_id=app_id,
		log_message=tsp_message,
		gps_position=position,
		intrusion=request.params.intrusion
	)

	_append_and_detect(tsp_log_entry)



### UTIL zone

@get("/UTIL/log-length")
def get_log_length():
	""" Count the number of log entries and return the number. """

	log_line_count = DAO.count_log_lines()

	message = "The log currently holds {} items.".format(log_line_count)
	if log_line_count == 0:
		message = "Log is empty!"

	return BaseResponse(body=message, status=200)


@post("/UTIL/flush-log")
def flush_log():
	""" Force a log flush in the DAO. """

	DAO.flush_log()

	return BaseResponse(body="Log was successfully flushed.", status=200)



### DANGER zone


@post("/DANGER/cut-log")
def cut_log():
	""" Cut the log off at the common minimum time of all clients. """

	minimum_time = DAO.get_current_min_time()

	print("Minimum time is {}. Now processing - this might take some time...".format(
		time.strftime("%Y-%m-%d, %H:%M", time.localtime(minimum_time))))

	message = DAO.cut_log_io()

	return BaseResponse(body=message, status=200)


@post("/DANGER/reset")
def reset():
	""" Rename the log and clear the state. """

	print("Server is resetting...")

	reset_models = request.params.models == "reset"

	status_msg = ""
	try:
		status_msg = DAO.reset()
	except ValueError as error:
		status_msg = error.message

	status_msg += "\n"
	status_msg += IDS.reset_log()

	status_msg += "\n"
	if reset_models:
		status_msg += IDS.reset_models()
	else:
		status_msg += "IDS model reset was not requested."

	print(status_msg)

	return BaseResponse(body=status_msg, status=200)



### Helper methods ###


def _get_position_string(crd_x, crd_y):
	""" Creates a position string of the format '41.123,40.31312' """
	return "{},{}".format(crd_x, crd_y)


def _create_base_log_entry(vin):
	""" Verifies the given VIN and creates a log entry with the current client time. """

	if vin is None:
		raise ValueError("No VIN given!")

	time_unix = _create_client_time(vin)
	return LogEntry.create_base_entry(vin, time_unix)


def _create_client_time(identifier):
	""" Creates a time for the client. Randomly increments time with 5 % chance. """

	client_time = DAO.get_client_time(identifier)
	time_now = time.time()

	if client_time is None:
		DAO.set_client_time(identifier, time_now)
		return time_now

	time_choice = random.choice([client_time] * 19 + [client_time + random.randint(3600, 57600)])
	DAO.set_client_time(identifier, time_choice)

	return time_choice



### Handling log entries


def _append_and_detect(new_log_entry):
	""" Append the given string plus a newline to the log file and detect possible intrusions. """

	if STORE:
		try:
			DAO.append_to_log(new_log_entry)
		except StateDao.MaximumReachedError:
			exit()
	if DETECT:
		IDS.process(new_log_entry)



######################################
### MAIN FLOW: Starting the server ###
######################################

PARSER = argparse.ArgumentParser()
PARSER.add_argument("--verbose", "-v", action="store_true")
PARSER.add_argument("--dont-detect", "-d", action="store_false", dest="detect")
PARSER.add_argument("--dont-store", "-s", action="store_false", dest="store")
PARSER.add_argument("--flush-frequency", "-f", type=int, metavar="S")
PARSER.add_argument("--max-entries-in-state", "-m", type=int, metavar="N")
PARSER.add_argument("--total-max-entries", "-t", type=int, metavar="N", help="Max. total entries")
ARGS = PARSER.parse_args()

DETECT = ARGS.detect
STORE = ARGS.store

YES_NO = lambda x: "yes" if x else "no"
IT_NOT = lambda x: "{:,}".format(x) if x else "not set"
FLUSH_FREQ_TXT = ("flush frequency: {}"
	.format(util.fmtr.format_time_passed(ARGS.flush_frequency)
	if ARGS.flush_frequency
	else "not set"))
CFG_MSG = ("detect: {} | store: {} | {} | max. entries in state: {} | max. entries total: {}"
	.format(
		YES_NO(ARGS.detect),
		YES_NO(ARGS.store),
		FLUSH_FREQ_TXT,
		IT_NOT(ARGS.max_entries_in_state),
		IT_NOT(ARGS.total_max_entries)
	)
)

if not ARGS.verbose:
	print("Starting server in quiet mode ({})".format(CFG_MSG))
else:
	print("Configuration selected: {}".format(CFG_MSG))

with StateDao(verbose=ARGS.verbose,
	flush_frequency=ARGS.flush_frequency,
	max_entries_in_state=ARGS.max_entries_in_state,
	max_entries_total=ARGS.total_max_entries) as dao:
	if ARGS.verbose:
		print("")

	DAO = dao
	if DETECT:
		IDS = LiveIds(verbose=ARGS.verbose)

	run(server="gevent", host="localhost", port=5000, quiet=(not ARGS.verbose))
