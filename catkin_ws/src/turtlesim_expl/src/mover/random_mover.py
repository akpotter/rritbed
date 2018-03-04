#!/usr/bin/env python
"""
Random move strategy
Possible arguments:
-pi     : Use 3.14... as seed
-pi1000 : use 314... as seed
[seed]  : use given value (must be valid float or int) as seed
"""

import argparse
import random
import sys
import time

import rospy

import move_helper
from move_strategy import MoveStrategy
from turtle_control import TurtleControl
from turtlesim.msg import Color, Pose


class RandomMoveStrategy(MoveStrategy):
	""" Random move strategy based on random.random """

	RETURN_CHOICE = "return"
	STAY_CHOICE = "stay"
	DONT_MOVE_CHOICE = "dont-move"

	_POSE_PATH = "turtle1/pose"
	_COLOUR_PATH = "turtle1/color_sensor"

	_rand_gen = random.Random()

	_last_pose_field = "last_pose"
	_last_colour_field = "last_colour"
	_data_field = "data"
	_last_update_field = "last_update"
	_illegal_since_field = "illegal_since"

	_update_rate_in_sec = 0.01

	_turtle_state = {
		_last_pose_field: {
			_data_field: None,
			_last_update_field: 0
		},
		_last_colour_field: {
			_data_field: None,
			_last_update_field: 0
		},
		_illegal_since_field: None
	}

	_illegal_colour = Color(r=255, g=0, b=0)

	_speedup = False


	def __init__(self, args):
		""" Ctor """

		MoveStrategy.__init__(self)

		if args.seed is not None:
			rospy.loginfo("Using seed %s", args.seed)
			self._rand_gen.seed(args.seed)
		else:
			rospy.loginfo("No seed specified")

		self._speedup = args.speedup
		if self._speedup:
			rospy.loginfo("Speedup activated")

		# Set get_next implementation based on intelligence selected
		if args.intelligence is None:
			rospy.loginfo("No intelligence mode specified")
			self.get_next = self._get_next_impl
		elif args.intelligence in [RandomMoveStrategy.RETURN_CHOICE, RandomMoveStrategy.STAY_CHOICE]:
			impl_choices = {
				RandomMoveStrategy.RETURN_CHOICE: self._turn_around_impl,
				RandomMoveStrategy.STAY_CHOICE: self._stay_impl
			}
			# All intelligence modes need the last pose and colour
			rospy.loginfo("Intelligence mode \"%s\" specified", args.intelligence)
			rospy.Subscriber(self._POSE_PATH, Pose, self._save_pose)
			rospy.Subscriber(self._COLOUR_PATH, Color, self._save_colour)
			# Select implementation based on specified intelligence
			self.get_next = impl_choices[args.intelligence]
		elif args.intelligence == RandomMoveStrategy.DONT_MOVE_CHOICE:
			rospy.loginfo("\"Don't move\" mode specified")
			self.get_next = self._dont_move_impl
		else:
			raise NotImplementedError("Intelligence mode %s not implemented", args.intelligence)


	# pylint: disable-msg=E0202; (An attribute hides this method)
	def get_next(self):
		raise NotImplementedError()


	def _get_next_impl(self):
		""" Move robot randomly. """

		vel_msg = move_helper.get_zero_twist()

		linear_choices = [
			0,
			self._jmp_and_rndint(-5, 5),
			self._jmp_and_rndint(-7, 7),
			self._jmp_and_rndint(-10, 10)
		]

		if self._speedup:
			linear_choices = [
				0,
				self._jmp_and_rndint(-20, -10),
				self._jmp_and_rndint(10, 20),
				self._jmp_and_rndint(-100, -30),
				self._jmp_and_rndint(30, 100)
			]

		angular_z_choices = [
			0,
			self._jmp_and_rndint(-1, 1),
			self._jmp_and_rndint(-3, 3),
			self._jmp_and_rndint(-5, 5)
		]

		vel_msg.linear.x = self._rand_gen.choice(linear_choices)
		self._rand_gen.jumpahead(7)
		vel_msg.linear.y = self._rand_gen.choice(linear_choices)
		self._rand_gen.jumpahead(7)
		vel_msg.angular.z = self._rand_gen.choice(angular_z_choices)

		return vel_msg


	def _turn_around_impl(self):
		""" Alternative to get_next with basic intelligence:
		Turn robot around when hitting illegal colour. """

		# No need to react - generate normal next step
		if self._get_last_colour() != self._illegal_colour:
			self._turtle_state[self._illegal_since_field] = None
			return self._get_next_impl()

		# We hit an illegal area

		# Initialise "illegal since" field
		if self._turtle_state[self._illegal_since_field] is None:
			self._turtle_state[self._illegal_since_field] = time.time()

		# Make sure we didn't spawn in the illegal area
		if (self._get_last_pose().linear_velocity == 0
			and self._get_last_pose().angular_velocity == 0):
			return self._get_next_impl()

		# Generate reverse of current pose
		rospy.logwarn("Reversing and escalating current pose - illegal area hit")
		pose = self._get_last_pose()
		reversed_pose_twist = move_helper.reverse_pose(pose)

		# Make sure we escalate speed the longer we are in the illegal zone
		if self._turtle_state[self._illegal_since_field] is not None:
			time_since_illegal = self._turtle_state[self._illegal_since_field]
			if reversed_pose_twist.linear.x < 0:
				reversed_pose_twist.linear.x -= time_since_illegal
			else:
				reversed_pose_twist.linear.x += time_since_illegal

		return reversed_pose_twist


	def _stay_impl(self):
		""" Alternative to get_next with compromised intelligence:
		Stop moving as soon as the illegal colour is hit. """

		# Normal steps
		if self._get_last_colour() != self._illegal_colour:
			return self._get_next_impl()

		return move_helper.get_zero_twist()


	def _dont_move_impl(self):
		""" Alternative to get_next that never moves. """
		return move_helper.get_zero_twist()


	def _jmp_and_rndint(self, start, stop, jmp=79):
		""" Jumpahead and return a random integer in the specified range [start, stop]. """
		self._rand_gen.jumpahead(jmp)
		return self._rand_gen.randint(start, stop)


	# Event handlers


	def _save_pose(self, pose):
		self._set_last_pose(pose)


	def _save_colour(self, colour):
		self._set_last_colour(colour)


	# Getters & setters


	def _get_last_pose(self):
		return self._turtle_state[self._last_pose_field][self._data_field]


	def _set_last_pose(self, pose):
		self._set_field(self._last_pose_field, pose, Pose)


	def _get_last_colour(self):
		return self._turtle_state[self._last_colour_field][self._data_field]


	def _set_last_colour(self, colour):
		self._set_field(self._last_colour_field, colour, Color)


	def _set_field(self, field, data, data_class):
		assert(issubclass(data.__class__, data_class))

		time_now = time.time()
		if time_now < self._update_rate_in_sec + self._turtle_state[field][self._last_update_field]:
			return

		self._turtle_state[field][self._data_field] = data
		self._turtle_state[field][self._last_update_field] = time_now


if __name__ == "__main__":
	try:
		PARSER = argparse.ArgumentParser(
			prog="random_mover", description="Randomly move a turtlesim around")

		GROUP = PARSER.add_mutually_exclusive_group()
		GROUP.add_argument("--seed", "-s", metavar="seed", type=float,
							help="Specify seed for the random generator")
		GROUP.add_argument("-pi", action="store_const", dest="seed", const=3.1415926535897,
							help="Use pi as seed")
		GROUP.add_argument("-pi1000", action="store_const", dest="seed", const=31415926535897.0,
							help="Use pi*10B as seed")

		INTELLIGENCE_CHOICES = [
			RandomMoveStrategy.RETURN_CHOICE,
			RandomMoveStrategy.STAY_CHOICE,
			RandomMoveStrategy.DONT_MOVE_CHOICE
		]
		PARSER.add_argument("--intelligence", "-i", metavar="intelligence_mode",
							choices=INTELLIGENCE_CHOICES, help="Specify intelligence mode")

		PARSER.add_argument("--speedup", "-f", action="store_true", help="Increase speed")

		# Pass filtered args to parser (remove remapping arguments and delete program name)
		ARGS = PARSER.parse_args(rospy.myargv(sys.argv)[1:])

		T_CONTROL = TurtleControl(RandomMoveStrategy, ARGS, 2)
		rospy.loginfo("Starting random walker")
		T_CONTROL.run()
	except rospy.ROSInterruptException:
		pass
