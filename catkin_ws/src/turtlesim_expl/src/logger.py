#!/usr/bin/env python
""" Logging node """

import argparse
import os
import random
import sys
import time

import requests
import rospy

from turtlesim.msg import Pose, Color
from turtlesim_expl.msg import GenValue

# pylint: disable-msg=C0411; (Standard import should be above - I don't consider it "standard")
from pipes.pose_pipe import PosePipe
from pipes.pose_processor import PoseProcessor, CC_STR, POI_STR, TSP_STR


BASE_PATH = os.path.expanduser("~/ros")
STOP_FILE_PATH = os.path.join(BASE_PATH, "STOP")


class Logger(object):
	""" Logger class """

	URL = "http://localhost:5000"

	TURTLE_PATH = "turtle/turtle1/"
	COLOUR_PATH = TURTLE_PATH + "color_sensor"
	POSE_PATH = TURTLE_PATH + "pose"

	_VIN_FIELD = "vin"
	_INTRUSION_FIELD = "intrusion"


	def __init__(self, args):
		""" Ctor """

		self._data = {
			Logger._VIN_FIELD : args.namespace
		}

		self._label = args.label
		self._intrusion = args.intrusion

		self._pose = (0, 0)

		self._last_broadcast = {
			self.log_colour.__name__ : 0,
			self.log_pose.__name__ : 0
		}
		self._last_conn_err = 0

		self._rand_gen = random.Random()

		rospy.init_node("logger", anonymous=True)

		# Subscribe to topics
		for topic in args.gen_topics:
			rospy.Subscriber(topic, GenValue, self.log_generated_data, topic)

		# Each of the three poses should roughly generate as much data as the colour logger.
		rospy.Subscriber(Logger.COLOUR_PATH, Color, self.rate_limit,
			{"method" : self.log_colour, "rate" : 0.7})
		rospy.Subscriber(Logger.POSE_PATH, Pose, self.rate_limit,
			{"method" : self.log_pose, "rate" : 0.1})

		rospy.loginfo("Logger initialised in NS {}".format(args.namespace))
		rospy.loginfo("Options (Label | {}), (Intrusion | {})"
			.format("yes" if args.label else "no", args.intrusion))

		# Block until shut down and check for stop file every ten seconds
		while not rospy.is_shutdown():
			if os.path.lexists(STOP_FILE_PATH):
				rospy.logerr("!!! STOP FILE DETECTED !!! KILLED !!!")
				break

			rospy.sleep(.1)


	def log_generated_data(self, gen_value, generator_name):
		""" Log generated data value. """

		request = self.copy_base_request()
		request["generated"] = gen_value.value
		if self._label:
			request[Logger._INTRUSION_FIELD] = gen_value.intrusion

		self.send_request("data/" + generator_name, request)


	def rate_limit(self, log_data, callback_definition):
		""" Rate limit the given method by rate_in_sec. """

		if any(x not in callback_definition for x in ["method", "rate"]):
			raise ValueError("Invalid callback definition!")

		method = callback_definition["method"]
		rate_in_sec = callback_definition["rate"]

		time_now = time.time()

		# Add a degree of randomness to when exactly the logging will begin
		if self._last_broadcast[method.__name__] == 0:
			self._last_broadcast[method.__name__] = time_now + self._rand_gen.randrange(1, 3)

		# Only broadcast once per rate_in_sec
		if time_now < self._last_broadcast[method.__name__] + rate_in_sec:
			return

		self._last_broadcast[method.__name__] = time_now

		method(log_data)


	def log_colour(self, log_data):
		""" Colour logging """

		# See py_turtlesim.util.Rgb
		legal_colours = [(150, 140, 200), (170, 250, 140), (120, 180, 130), (120, 180, 200)]
		illegal_colours = [(255, 0, 0), (200, 50, 50), (170, 80, 80)]

		this_colour = (log_data.r, log_data.g, log_data.b)

		is_red = False
		if this_colour in legal_colours:
			is_red = False
		elif this_colour in illegal_colours:
			is_red = True
		else:
			raise NotImplementedError("This colour is not implemented: (%s, %s, %s)" % this_colour)

		colour_string = "%s,%s,%s" % this_colour

		pose_x, pose_y = self._pose
		request = self.copy_base_request()
		request = PoseProcessor.add_to_request(request, pose_x, pose_y)
		request["colour"] = colour_string

		if self._label:
			request[Logger._INTRUSION_FIELD] = "red" if is_red else "normal"

		self.send_request("colour", request)


	def log_pose(self, log_data):
		""" Pose logging """

		self._pose = (log_data.x, log_data.y)

		# Each request with 1/3 probability
		pose_pipe = PosePipe.create(
			intrusion=self._intrusion, intrusion_field=Logger._INTRUSION_FIELD,
			cc=1, poi=1, tsp=1)

		request = self.copy_base_request()
		request = PoseProcessor.add_to_request(request, log_data.x, log_data.y)
		request = pose_pipe.process(request, label=self._label)

		processor_name = pose_pipe.get_processor_name()
		endpoint = ""
		if processor_name == CC_STR:
			endpoint = "country-code"
		elif processor_name == POI_STR:
			endpoint = "poi"
		elif processor_name == TSP_STR:
			endpoint = "tsp"
		else:
			raise NotImplementedError("Choice not implemented")

		self.send_request(endpoint, request, path="get")


	def send_request(self, log_method, request, path="log"):
		""" Send request to specified logging endpoint with given data. """

		if self._label:
			if Logger._INTRUSION_FIELD not in request:
				raise KeyError("Missing intrusion key necessary for labelling.")

		try:
			requests.post(Logger.URL + "/" + path + "/" + log_method, request)
		except requests.ConnectionError:
			time_now = time.time()
			# Only print an error every ten seconds
			if time_now > self._last_conn_err + 10:
				rospy.logerr("Can't connect to logging API")
				self._last_conn_err = time_now


	def copy_base_request(self):
		""" Make a value-copy of the base request. """
		return dict(self._data)



if __name__ == "__main__":
	PARSER = argparse.ArgumentParser(prog="logger")

	PARSER.add_argument("namespace", metavar="NS", help="The namespace this logger is seated in")
	PARSER.add_argument("--gen-topics", metavar="TOPIC", nargs="*", default=[], dest="gen_topics")
	PARSER.add_argument("--label", action="store_true", help="Label the data with intrusion type")
	PARSER.add_argument("--intrusion", "-i", choices=PoseProcessor.POSSIBLE_INTRUSION_LEVELS)

	# Pass filtered args to parser (remove remapping arguments and delete program name)
	ARGS = PARSER.parse_args(rospy.myargv(sys.argv)[1:])

	LOGGER = Logger(ARGS)
