import urllib2
import ntplib
import ftplib
from time import ctime
import datetime
import time
from gpiozero import LED
import os
import csv
import copy

import ArduinoComms

class AQMeshStation():
	def __init__ (self):
		self.MAX_COMMAND_RETRIES = 10
		self.MAX_PARAMETER_RETRIES = 10
		self.MAX_TIMESERVER_RETRIES = 10
		self.MAX_RECONNECT_ATTEMPTS = 10
		
		self.ARDUINO_PORT = '/dev/ttyACM0'
		self.ARDUINO_BAUD = 115200
		self.ARDUINO_TIMEOUT_SECS = 1.0
		
		self.STATION_ID = 0
		self.FTP_SERVER = 'ftpupload.net'
		self.FTP_PORT = 21
		self.FTP_LOGIN = 'epiz_23835097'
		self.FTP_PASSWORD = 'YRyhrbvxTU3bBK'
		self.FTP_ROOT_DIR = '/aqleeds.epizy.com/htdocs/'
		self.SETTINGS_FILE_DIR = self.FTP_ROOT_DIR + 'station-' + str(self.STATION_ID)
		self.SETTINGS_FILE_NAME = 'settings.csv'
		
		self.NTP_TIMESERVER = 'europe.pool.ntp.org'
		self.WEB_CONNECTIVITY_CHECK_URL = 'http://www.google.com'
		
		self.LOCAL_DEFAULT_PATH = './local_store/'
		
		self.FILES_TO_UPLOAD = {'ADC': './ADC_TO_UPLOAD.txt',
								'OPC': './OPC_TO_UPLOAD.txt',
								'BATT': './BATT_TO_UPLOAD.txt'}
		
		self.DEFAULT_DEVICE_PARAMETER_SETTINGS = {'adc_averaging_period': 10, 'opc_averaging_period': 30, 'web_update_period': 2}
		self.DEVICE_PARAMETER_MIN_VALUES = {'adc_averaging_period': 1, 'opc_averaging_period': 5, 'web_update_period': 2}
		self.DEVICE_PARAMETER_MAX_VALUES = {'adc_averaging_period': 120, 'opc_averaging_period': 60, 'web_update_period': 60}
		
		self.RPI_OUTPUT = 17
		self.running_flag = LED(self.RPI_OUTPUT)
		self.running_flag.off()
		time.sleep(1.0)
		
		# Start the serial connection with the arduino.
		comms_success = self.startComms()
		
		# Flag that the RPI is ready to update.
		self.running_flag.on()
		
		# Set the time on the arduino RTC to that returned from the NTP server.
		#~ comms_success, completed = self.setTime()
		
		comms_success, completed, files = self.spoolData()
		print files
		
		if len(files) > 0:
			for current_file in files:
				current_file_name = current_file[2:14]
				current_file_data = current_file[14:]
				adc_data, opc_data, batt_data = self.parseData(current_file_data)
				if len(adc_data) > 0:
					stored_adc_file = self.storeData('ADC', current_file_name, adc_data)
					print self.markForUpload('ADC', stored_adc_file)
				if len(opc_data) > 0:
					stored_opc_file = self.storeData('OPC', current_file_name, opc_data)
					print self.markForUpload('OPC', stored_opc_file)
				if len(batt_data) > 0:
					stored_batt_file = self.storeData('BATT', current_file_name, batt_data)
					print self.markForUpload('BATT', stored_batt_file)
			
			time.sleep(5)
			internet_available = False
			for attempt in range(5):
				internet_available = self.internetOn()
				if internet_available:
					break
			
			if internet_available:
				file_types = ['ADC', 'OPC', 'BATT']
				for file_type in file_types:
					files = self.waitingForUpload(file_type)
					if len(files) > 0:
						destination_dir = self.FTP_ROOT_DIR + 'station-' + str(self.STATION_ID) + '/' + file_type + '_DATA'
						failed_uploads_of_this_type = []
						for current_file in files:
							upload_success = self.uploadData(self.FTP_SERVER, self.FTP_PORT, self.FTP_LOGIN, self.FTP_PASSWORD, destination_dir, current_file)
							if not upload_success:
								failed_uploads_of_this_type.append(current_file)
						os.remove(self.FILES_TO_UPLOAD[file_type])
						for current_file in failed_uploads_of_this_type:
							self.markForUpload(file_type, current_file)
						print failed_uploads_of_this_type
				self.updateDeviceSettings(self.FTP_SERVER, self.FTP_PORT, self.FTP_LOGIN, self.FTP_PASSWORD, self.SETTINGS_FILE_DIR, self.SETTINGS_FILE_NAME)
			
		# Indicate that the RPI is finished updating.
		self.running_flag.off()
		
		# Shut down the RPI. -h forces it to 'halt' and stay off, rather than immediately restarting.
		os.system("sudo shutdown -h now")
		
		# ~~~ Fin ~~~
	
		
	def markForUpload(self, data_type, file_path):
		with open(self.FILES_TO_UPLOAD[data_type], 'a') as output_file:
			output_file.write(file_path + '\r\n')
		return file_path
	
	def waitingForUpload(self, data_type):
		files_to_upload = []
		with open(self.FILES_TO_UPLOAD[data_type], 'r') as input_file:
			files_to_upload = input_file.read().split()
		return files_to_upload
	
	def clearUploadList(self, data_type):
		import os
		os.remove(self.FILES_TO_UPLOAD[data_type])
	
	def updateDeviceSettings(self, ftp_server, ftp_port, ftp_login, ftp_password, destination_dir, settings_file_name):
		ftp = ftplib.FTP()
		
		# Download new settings file from server if it exists.
		new_settings_file_exists = False
		try:
			ftp.set_debuglevel(2)
			ftp.connect(ftp_server, ftp_port)
			ftp.login(ftp_login, ftp_password)
			ftp.cwd(destination_dir)
			with open('./new_' + settings_file_name, 'wb') as f:
				ftp.retrbinary('RETR %s' % settings_file_name, f.write)
			new_settings_file_exists = True
		except:
			# In the event of an exception when obtaining the file via FTP, the with statement
			# will have already created the empty file, so we remove it if necessary.
			if os.path.exists('./new_' + settings_file_name):
				os.remove('./new_' + settings_file_name)
			new_settings_file_exists = False
		
		# If downloaded, check that new settings file contents are valid.
		new_device_parameter_settings = {}
		valid_parameter_settings = True
		if new_settings_file_exists:
			with open('./new_' + settings_file_name, 'rb') as csvfile:
				csv_reader = csv.reader(csvfile, delimiter = ',')
				for row in csv_reader:
					if not row[0].startswith('#'):
						new_device_parameter_settings[row[0]] = row[1]
			for current_key in new_device_parameter_settings.keys():
				correct_data_type = False
				try:
					new_device_parameter_settings[current_key] = int(new_device_parameter_settings[current_key])
					correct_data_type = True
				except:
					correct_data_type = False
				if not (correct_data_type and (current_key in self.DEFAULT_DEVICE_PARAMETER_SETTINGS.keys())):
					valid_parameter_settings = False
		
		# Check if there is an existing local settings file. If it exists, load it's contents. We will assume it
		# the contents are valid, as it will have been checked at creation time.
		local_settings_file_exists = os.path.exists('./' + settings_file_name) and os.path.isfile('./' + settings_file_name)
		local_device_parameter_settings = {}
		if local_settings_file_exists:
			with open('./' + settings_file_name, 'rb') as csvfile:
				csv_reader = csv.reader(csvfile, delimiter = ',')
				for row in csv_reader:
					if not row[0].startswith('#'):
						local_device_parameter_settings[row[0]] = int(row[1])
						
		# We have now downloaded the new settings file (if available), and checked the validity of it's contents. We have
		# also checked if there is an existing local settings file and loaded it's contents. 
		#
		# Now:
		# i)   We have no local file and no new file -> No update.
		# ii)  We have no local file and a new file, but the new file contents are invalid -> Delete new file, no update.
		# iii) We have no local file and a new file -> Rename new file and update.
		# iv)  We have a local file and no new file -> No update.
		# v)   We have a local file and a new file, but the new file contents are invalid -> Delete new file, no update.
		# vi)  We have a local file and a valid new file, but they are the same -> Delete new file, no update.
		# vii) We have a local file and a valid new file that differ -> Rename new file to overwrite old file and update.
		update_settings = False
		if ((not local_settings_file_exists) and (not new_settings_file_exists)):
			# i)   We have no local file and no new file -> No update.
			update_settings = False
		elif ((not local_settings_file_exists) and new_settings_file_exists and (not valid_parameter_settings)):
			# ii)  We have no local file and a new file, but the new file contents are invalid -> Delete new file, no update.
			os.remove('./new_' + settings_file_name)
			update_settings = False
		elif ((not local_settings_file_exists) and new_settings_file_exists and valid_parameter_settings):
			# iii) We have no local file and a new file -> Rename new file and update.
			os.rename('./new_' + settings_file_name, './' + settings_file_name)
			update_settings = True
		elif (local_settings_file_exists and (not new_settings_file_exists)):
			# iv)  We have a local file and no new file -> No update.
			update_settings = False
		elif (local_settings_file_exists and new_settings_file_exists and (not valid_parameter_settings)):
			# v)   We have a local file and a new file, but the new file contents are invalid -> Delete new file, no update.
			os.remove('./new_' + settings_file_name)
			update_settings = False
		elif (local_settings_file_exists and new_settings_file_exists and valid_parameter_settings and (local_device_parameter_settings == new_device_parameter_settings)):
			# vi)  We have a local file and a valid new file, but they are the same -> Delete new file, no update.
			os.remove('./new_' + settings_file_name)
			update_settings = False
		elif (local_settings_file_exists and new_settings_file_exists and valid_parameter_settings and (not local_device_parameter_settings == new_device_parameter_settings)): 
			# vii) We have a local file and a valid new file that differ -> Rename new file to overwrite old file and update.
			os.remove('./' + settings_file_name)
			os.rename('./new_' + settings_file_name, './' + settings_file_name)
			update_settings = True
		
		if update_settings:
			for current_key in new_device_parameter_settings.keys():
				self.setParameter(current_key, new_device_parameter_settings[current_key])
				time.sleep(2.0)
	
	def parseData(self, data_buffer):
		split_data = [entry for entry in data_buffer.split('\r\n') if entry]
		adc_rows = [entry[6:] for entry in split_data if entry.startswith("(ADCS)")]
		adc_data_buffer = '\r\n'.join(adc_rows) + '\r\n'
		opc_rows = [entry[5:] for entry in split_data if entry.startswith("(OPC)")]
		opc_data_buffer = '\r\n'.join(opc_rows) + '\r\n'
		batt_rows = [entry[6:] for entry in split_data if entry.startswith("(BATT)")]
		batt_data_buffer = '\r\n'.join(batt_rows) + '\r\n'
		return adc_data_buffer, opc_data_buffer, batt_data_buffer
		
			
	def uploadData(self, ftp_server, ftp_port, ftp_login, ftp_password, destination_dir, local_file_path):
		import os
		upload_successful = False
		print '-------------------------------- FTP debug info --------------------------------'
		try:
			ftp = ftplib.FTP()
			ftp.set_debuglevel(2)
			ftp.connect(ftp_server, ftp_port)
			ftp.login(ftp_login, ftp_password)
			self.FTPChangeDirectory(ftp, destination_dir)
			file = open(local_file_path, 'rb')
			ftp.storbinary('STOR %s' % os.path.basename(local_file_path), file, 1024)
			file.close()
			print '--------------------------------------------------------------------------------'
			print 'Upload to FTP server completed.'
			print '--------------------------------------------------------------------------------'
			upload_successful = True
		except:
			print 'Unable to upload data to FTP server.'
			print '--------------------------------------------------------------------------------'
			upload_successful = False
		return upload_successful
	
	def FTPChangeDirectory(self, ftp, dir_path):						# We want to try and change into the target directory on the FTP server, and if it doesn't exist - create it.
		dir_sequence = dir_path.split('/')[1:]							# However, it will fail if we try and do it in one pass, so instead we descend down the target directory path,
		path_to_try = ''												# trying to cd into each directory in turn, creating it if we can't.
		for current_dir in dir_sequence:
			path_to_try += '/' + current_dir
			try:
				ftp.cwd(path_to_try)
			except:
				ftp.mkd(path_to_try)
				ftp.cwd(path_to_try)
	
	def storeData(self, data_type, file_name, data):
		import os
		dir_path = self.LOCAL_DEFAULT_PATH + data_type + '/'
		file_path = dir_path + file_name
		directory_exists = os.path.isdir(dir_path)
		if not directory_exists:
			os.mkdir(dir_path)
		with open(file_path, 'a') as output_file:
			output_file.write(data)
		return file_path
	
	def spoolData(self):
		completed = False
		comms_success = False
		command_tries = 0
		outgoing_command = 'TX'
		while ((completed == False) and (command_tries < self.MAX_COMMAND_RETRIES)):
			files = []
			data_buffer = ''
			comms_success, response = self.arduino.Call(outgoing_command, 1)
			if not comms_success:
				return comms_success, completed, []
			print response
			crc_success = response[0][0]
			reply = response[0][1]
			if crc_success == True:
				if reply == 'to':
					command_tries += 1
					outgoing_command = 'TX'
					time.sleep(30.0)
				else:
					param_tries = 0
					if reply.startswith('f}'):
						data_buffer += reply
						outgoing_command = 'AK'
					resend_required = False
					while ((completed == False) and (param_tries < self.MAX_PARAMETER_RETRIES)):
						comms_success, response = self.arduino.Call(outgoing_command, 1)
						if not comms_success:
							return comms_success, completed, []
						print response
						crc_success = response[0][0]
						reply = response[0][1]
						if crc_success == True:
							if reply.startswith('f}'):
								resend_required = False
								files.append(data_buffer)
								data_buffer = reply
								outgoing_command = 'AK'
							elif reply == 'to':
								param_tries = 0
								outgoing_command = 'TX'
								break
							elif reply == 'fl':
								param_tries = 0
								outgoing_command = 'TX'
								break
							elif reply == 'cr':
								if resend_required == True:
									outgoing_command = 'AR'
									param_tries += 1
								else:
									outgoing_command = 'AK'
							elif reply == 'fs':
								outgoing_command = 'CC'
							elif reply == 'cc':
								files.append(data_buffer)
								completed = True
							else:
								data_buffer += reply
								outgoing_command = 'AK'
						else:
							tries += 1
							resend_required = True
							outgoing_command = 'AR'
			else:
				command_tries += 1
				outgoing_command = 'TX'
				time.sleep(30.0)
		return comms_success, completed, files

	def setTime(self):
		completed = False
		comms_success = False
		tries = 0
		while ((completed == False) and (tries < self.MAX_COMMAND_RETRIES)):
			# Connect to a NTP server and query the current time
			got_timestamp, timestamp = self.getNtpTime(self.NTP_TIMESERVER)
			if got_timestamp == False:
				print 'Unable to obtain NTP timestamp.'
				break
			print timestamp
			comms_success, response = self.arduino.Call('ST', 1)
			if not comms_success:
				return comms_success, completed
			print response
			reply = response[0][1]
			crc_success = response[0][0]
			if crc_success == True:
				if reply == 'ak':												# ST command arrived and ack received from arduino.
					time_headers = ['YY', 'MM', 'DD', 'hh', 'mm', 'ss']
					for i, parameter in enumerate(timestamp):
						tries = 0
						while tries < self.MAX_PARAMETER_RETRIES:
							comms_success, response = self.arduino.Call(time_headers[i], 1)
							if not comms_success:
								return comms_success, completed
							print response
							reply = response[0][1]
							crc_success = response[0][0]
							if ((reply == 'ht') and (crc_success == True)):
								comms_success, response = self.arduino.Call(str(parameter), 1)
								if not comms_success:
									return comms_success, completed
								print response
								reply = response[0][1]
								crc_success = response[0][0]
								if crc_success == True:
									if reply == 'ht':
										break
									elif reply == 'to':
										completed = False
										return comms_success, completed
									elif reply == 'fs':
										completed = True
										break
									else:
										tries += 1
								else:
									tries += 1
							else:
								tries += 1
					
				else:
					tries += 1
			else:
				tries += 1
		tries = 0
		while tries < self.MAX_PARAMETER_RETRIES:
			comms_success, response = self.arduino.Call('AK', 1)
			if not comms_success:
				return comms_success, completed
			print response
			reply = response[0][1]
			crc_success = response[0][0]
			if crc_success == True:
				if reply == 'ak':
					break
				else:
					tries += 1
			else:
				tries += 1
		return comms_success, completed
	
	def setParameter(self, parameter, value):
		completed = False
		comms_success = False
		tries = 0
		while ((completed == False) and (tries < self.MAX_COMMAND_RETRIES)):
			comms_success, response = self.arduino.Call('CP', 1)
			if not comms_success:
				return comms_success, completed	
			print response
			reply = response[0][1]
			crc_success = response[0][0]
			if ((crc_success == True) and (reply != 'to')):
				if reply == 'ak':												# CP command arrived and ack received from arduino.
					tries = 0
					parameter_headers = {'adc_averaging_period': 'AP', 'opc_averaging_period': 'OP', 'web_update_period': 'UP'}
					outgoing_command = parameter_headers[parameter]
					while tries < self.MAX_PARAMETER_RETRIES:
						comms_success, response = self.arduino.Call(outgoing_command, 1)
						if not comms_success:
							return comms_success, completed	
						print response						
						reply = response[0][1]
						crc_success = response[0][0]
						if crc_success == True:
							if reply == 'ak':
								if completed == False:
									outgoing_command = str(value)
								else:
									break
							elif reply == 'fs':
								completed = True
								outgoing_command = 'AK'
							elif reply == 'to':
								tries = 0
								break
							else:
								if completed == False:
									outgoing_command = parameter_headers[parameter]
								else:
									outgoing_command = 'AK'
								tries += 1
						elif crc_success == False:
							if completed == False:
								outgoing_command = parameter_headers[parameter]
							else:
								outgoing_command = 'AK'
							tries += 1
				else:
					tries += 1										
			elif ((crc_success == True) and (reply == 'to')):					# Arduino failed to understand command or sent timeout ('to'). Send CP command again.
				tries += 1
			elif crc_success == False:
				tries += 1
		return comms_success, completed
	
	def startComms(self):
		# Start the serial connection with the arduino.
		self.arduino = ArduinoComms.ArduinoComms(self.ARDUINO_BAUD, self.ARDUINO_PORT, self.ARDUINO_TIMEOUT_SECS, self.MAX_RECONNECT_ATTEMPTS)
	
	def internetOn(self):
		print 'Checking for working internet connection...'
		try:
			urllib2.urlopen(self.WEB_CONNECTIVITY_CHECK_URL, timeout = 10.0)
			print 'Connection works!'
			return True
		except:
			print 'No internet connection available.'
			return False
	
	def getNtpTime(self, ntp_timeserver):
		print 'Grabbing time...'
		c = ntplib.NTPClient()
		tries = 0
		completed = False
		while((tries < self.MAX_TIMESERVER_RETRIES) and (completed == False)):
			try:
				response = c.request(ntp_timeserver, version = 3)
				print 'NTP timestamp obtained from ' + ntp_timeserver + ' .'
				completed = True
			except:
				print 'No response received from ' + ntp_timeserver + ' .'
				tries += 1
		
		datetime_string = ctime(response.tx_time)
		datetime_object = datetime.datetime.strptime(datetime_string, '%a %b %d %H:%M:%S %Y')
		# Want to have output in the following format (all ints): YEAR MONTH DAY HRS MINS SECS
		year = datetime_object.year
		month = datetime_object.month
		day = datetime_object.day
		hour = datetime_object.hour
		minute = datetime_object.minute
		second = datetime_object.second
		return completed, [year, month, day, hour, minute, second]
	
if __name__ == '__main__':
	aqmeshstation = AQMeshStation()
	
