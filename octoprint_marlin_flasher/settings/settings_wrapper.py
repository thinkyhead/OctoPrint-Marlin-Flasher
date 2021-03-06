class SettingsWrapper:

	def __init__(self, settings):
		self.__settings = settings

	def get_max_upload_size(self):
		return self.__settings.get_int(["max_upload_size"])

	def get_platform_type(self):
		return self.__settings.get(["platform_type"])

	def get_upload_path_suffix(self):
		return self.__settings.global_get(["server", "uploads", "pathSuffix"])

	def get_arduino_cli_path(self):
		return self.__settings.get(["arduino", "cli_path"])

	def get_arduino_additional_urls(self):
		return self.__settings.get(["arduino", "additional_urls"])

	def get_arduino_sketch_ino(self):
		return self.__settings.get(["arduino", "sketch_ino"])

	def get_platformio_cli_path(self):
		return self.__settings.get(["platformio", "cli_path"])
