from .base_flasher import BaseFlasher
import zipfile
import re
import os
import shutil
import serial
import flask
from flask_babel import gettext
import pyduinocli


class ArduinoFlasher(BaseFlasher):

	def __init__(self, settings, printer, plugin, plugin_manager, identifier):
		BaseFlasher.__init__(self, settings, printer, plugin, plugin_manager, identifier)
		self.__is_ino = False

	def __get_arduino(self):
		path = self._settings.get_arduino_cli_path()
		additional_urls = self._settings.get_arduino_additional_urls()
		if additional_urls:
			additional_urls = additional_urls.splitlines()
		return pyduinocli.Arduino(path, additional_urls=additional_urls)

	@staticmethod
	def __error_to_dict(error):
		return dict(
			error=error.message,
			cause=error.cause,
			stderr=error.stderr
		)

	def check_setup_errors(self):
		no_arduino_path = self._settings.get_arduino_cli_path() is None
		if no_arduino_path:
			return dict(
				error=gettext("No path has been configured, check the plugin settings.")
			)
		try:
			bad_version = re.match(r"(?:0\.5\..+?)\Z", self.__get_arduino().version()["VersionString"]) is None
		except pyduinocli.ArduinoError:
			return dict(
				error=gettext("The configured path does not point to an arduino-cli executable.")
			)
		except KeyError:
			bad_version = True
		if bad_version:
			return dict(
				error=gettext("The arduino-cli version you are using is not supported.")
			)
		return None

	def upload_file(self):
		self._firmware = None
		uploaded_file_path = flask.request.values["firmware_file." + self._settings.get_upload_path_suffix()]
		try:
			with zipfile.ZipFile(uploaded_file_path, "r") as zip_file:
				self.__is_ino = True
				firmware_dir = os.path.join(self._plugin.get_plugin_data_folder(), "firmware")
				sketch_dir = os.path.join(firmware_dir, os.path.splitext(self._settings.get_arduino_sketch_ino())[0])
				if os.path.exists(firmware_dir):
					shutil.rmtree(firmware_dir)
				os.makedirs(sketch_dir)
				zip_file.extractall(sketch_dir)
				for root, dirs, files in os.walk(sketch_dir):
					for f in files:
						if f == self._settings.get_arduino_sketch_ino():
							self._firmware = root
							return dict(
								path=root,
								file=f
							), None
				return None, dict(
					error=gettext("No valid sketch were found in the given file.")
				)
		except zipfile.BadZipfile:
			self.__is_ino = False
			self._firmware = os.path.join(self._plugin.get_plugin_data_folder(), "firmware.hex")
			shutil.copyfile(uploaded_file_path, self._firmware)
			return dict(
				path=self._plugin.get_plugin_data_folder(),
				file="firmware.hex"
			), None

	def core_search(self):
		try:
			arduino = self.__get_arduino()
			arduino.core_update_index()
			result = arduino.core_search(flask.request.values["query"].split(" "))
			return result, None
		except pyduinocli.ArduinoError as e:
			return None, self.__error_to_dict(e)

	def lib_search(self):
		try:
			arduino = self.__get_arduino()
			arduino.core_update_index()
			result = arduino.lib_search(flask.request.values["query"].split(" "))
			return result, None
		except pyduinocli.ArduinoError as e:
			return None, self.__error_to_dict(e)

	def core_install(self):
		try:
			arduino = self.__get_arduino()
			arduino.core_install([flask.request.values["core"]])
			return dict(
				core=flask.request.values["core"]
			), None
		except pyduinocli.ArduinoError as e:
			return None, self.__error_to_dict(e)

	def lib_install(self):
		try:
			arduino = self.__get_arduino()
			arduino.lib_install([flask.request.values["lib"]])
			return dict(
				lib=flask.request.values["lib"]
			), None
		except pyduinocli.ArduinoError as e:
			return None, self.__error_to_dict(e)

	def core_uninstall(self):
		try:
			arduino = self.__get_arduino()
			arduino.core_uninstall([flask.request.values["core"]])
			return dict(
				core=flask.request.values["core"]
			), None
		except pyduinocli.ArduinoError as e:
			return None, self.__error_to_dict(e)

	def lib_uninstall(self):
		try:
			arduino = self.__get_arduino()
			arduino.lib_uninstall([flask.request.values["lib"].replace(" ", "_")])
			return dict(
				lib=flask.request.values["lib"]
			), None
		except pyduinocli.ArduinoError as e:
			return None, self.__error_to_dict(e)

	def board_listall(self):
		try:
			arduino = self.__get_arduino()
			arduino.core_update_index()
			result = arduino.board_listall()
			return result, None
		except pyduinocli.ArduinoError as e:
			return self.__error_to_dict(e)

	def board_details(self):
		try:
			arduino = self.__get_arduino()
			result = arduino.board_details(flask.request.values["fqbn"])
			return result, None
		except pyduinocli.ArduinoError as e:
			return self.__error_to_dict(e)

	def flash(self):
		if self._firmware is None:
			return None, dict(
				error=gettext("You did not upload the firmware or it got reset by the previous flash process.")
			)
		if not self._printer.is_ready():
			return None, dict(
				error=gettext("The printer may not be connected or it may be busy.")
			)
		options = []
		for param in flask.request.values:
			if param != "fqbn":
				options.append("%s=%s" % (param, flask.request.values[param]))
		options = ",".join(options)
		fqbn = flask.request.values["fqbn"]
		if options:
			fqbn = "%s:%s" % (fqbn, options)
		try:
			arduino = self.__get_arduino()
			if self.__is_ino:
				self._plugin_manager.send_plugin_message(self._identifier, dict(
					step=gettext("Compiling"),
					progress=0
				))
				arduino.compile(self._firmware, fqbn=fqbn)
				self._plugin_manager.send_plugin_message(self._identifier, dict(
					step=gettext("Uploading"),
					progress=50
				))
			else:
				self._plugin_manager.send_plugin_message(self._identifier, dict(
					step=gettext("Uploading"),
					progress=0
				))
			transport = self._printer.get_transport()
			if not isinstance(transport, serial.Serial):
				return None, dict(
					error=gettext("The printer is not connected through a Serial port and thus, cannot be flashed.")
				)
			flash_port = transport.port
			_, port, baudrate, profile = self._printer.get_current_connection()
			self._printer.disconnect()
			if self.__is_ino:
				arduino.upload(sketch=self._firmware, fqbn=fqbn, port=flash_port)
			else:
				arduino.upload(fqbn=fqbn, port=flash_port, input=self._firmware)
			self._printer.connect(port, baudrate, profile)
			self._firmware = None
			self._plugin_manager.send_plugin_message(self._identifier, dict(
				step=gettext("Done"),
				progress=100
			))
			return dict(
				message=gettext("Board successfully flashed.")
			), None
		except pyduinocli.ArduinoError as e:
			return None, self.__error_to_dict(e)
